
import os
import logging
import time
import threading
import json
import re
import hashlib
import redis
import csv
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import paho.mqtt.client as mqtt

# ================= Configuration =================
MQTT_BROKER = '158.109.75.3'
MQTT_PORT = 1883

TARGET_EMAIL = "example@uab.cat" 

# Topic
TOPIC_CONSUMPTION = "inverter/289/Ac/Out/L1/S" 
TOPIC_PRODUCTION = "solarcharger/288/Yield/Power"

SAMPLING_INTERVAL = 30        
REPORT_INTERVAL_MINUTES = 15  
DATA_TIMEOUT = 900

CSV_DIR = "csv_data"

app = Flask(__name__)

# --- Redis Model ---
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def is_valid_email(email):
    email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(email_regex, email) is not None

class RedisModel:
    def __init__(self):
        self.client = redis.StrictRedis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=os.getenv("REDIS_PORT", 6379),
            decode_responses=True,
        )

    def create_user(self, user_name, user_email, user_password):
        key = f"user:{user_email}"
        user_document = {
            "user_name": user_name,
            "user_email": user_email,
            "user_password": hash_password(user_password),
            "user_consumption": {},
            "user_production": {},
            "user_battery": {},
            "user_yield": {}
        }
        self.client.execute_command("JSON.SET", key, ".", json.dumps(user_document))
        return {"message": f"User '{user_name}' created."}

    def _initialize_json_path(self, key, path):
        try:
            existing_data = self.client.execute_command("JSON.GET", key, path)
            if existing_data is None or existing_data == "[]":
                self.client.execute_command("JSON.SET", key, path, "{}")
        except redis.RedisError:
            pass 

    def add_data(self, user_email, date, hour, value, data_type):
        key = f"user:{user_email}"
        base_path = f"$.{data_type}"
        self._initialize_json_path(key, base_path)
        date_path = f"{base_path}.{date}"
        self._initialize_json_path(key, date_path)

        try:
            hour_path = f"{date_path}.{hour}"
            increment = self.client.execute_command("JSON.NUMINCRBY", key, hour_path, value)
            if increment is None or increment == "[]":
                self.client.execute_command("JSON.SET", key, hour_path, value)
        except redis.RedisError as e:
            print(f"Redis Error: {e}")
            raise ValueError(f"Failed to update {data_type}")

        return {"message": "Data added"}

    def add_consumption(self, user_email, date, hour, value):
        return self.add_data(user_email, date, hour, value, "user_consumption")

    def add_production(self, user_email, date, hour, value):
        return self.add_data(user_email, date, hour, value, "user_production")

    def add_battery_status(self, user_email, date, hour, voltage, current, power):
        key = f"user:{user_email}"
        base_path = "$.user_battery"
        self._initialize_json_path(key, base_path)
        date_path = f"{base_path}.{date}"
        self._initialize_json_path(key, date_path)
        
        try:
            hour_path = f"{date_path}.{hour}"
            status_data = {"voltage": voltage, "current": current, "power": power}
            self.client.execute_command("JSON.SET", key, hour_path, json.dumps(status_data))
        except redis.RedisError as e:
            print(f"Redis Error: {e}")
            raise ValueError("Failed to update battery status")

    def add_yield_status(self, user_email, date, hour, yield_today, yield_yesterday):
        key = f"user:{user_email}"
        base_path = "$.user_yield"
        self._initialize_json_path(key, base_path)
        date_path = f"{base_path}.{date}"
        self._initialize_json_path(key, date_path)
        
        try:
            hour_path = f"{date_path}.{hour}"
            status_data = {"yield_today": yield_today, "yield_yesterday": yield_yesterday}
            self.client.execute_command("JSON.SET", key, hour_path, json.dumps(status_data))
        except redis.RedisError as e:
            print(f"Redis Error: {e}")
            raise ValueError("Failed to update yield status")
            
    def get_battery_history(self, user_email, date):
        key = f"user:{user_email}"
        path = f"$.user_battery.{date}"
        try:
            data = self.client.execute_command("JSON.GET", key, path)
            if data and data != "[]":
                parsed_data = json.loads(data)
                return parsed_data[0] if isinstance(parsed_data, list) else parsed_data
            return {}
        except redis.RedisError:
            return {}
    

redis_model = RedisModel()

# --- MQTT Logic ---

current_power = {
    "consumption": 0.0,
    "production": 0.0
}

current_battery = {
    "voltage": 0.0,
    "current": 0.0,
    "power": 0.0
}

current_yield = {
    "today": 0.0,
    "yesterday": 0.0
}

last_update_time = {
    "consumption": time.time(),
    "production": time.time()
}

energy_buffer = {
    "consumption": 0.0,
    "production": 0.0,
    "last_saved_minute": -1 
}

ghost_energy = {
    "consumption": 0.0,
    "production": 0.0
}

battery_accumulator = {
    "voltage_sum": 0.0,
    "power_sum": 0.0,
    "count": 0
}

web_display_snapshot = {
    "battery": {
        "voltage": 0.0,
        "power": 0.0
    },
    "yield": {
        "today": 0.0,
        "yesterday": 0.0
    }
}

portal_id = None


def save_hourly_csv(date_str, hour_str, cons_val, prod_val, batt_v, batt_i, batt_p, yield_today, yield_yesterday):

    try:
        year = date_str.split("-")[0]
        
        if not os.path.exists(CSV_DIR):
            os.makedirs(CSV_DIR)
            
        filename = os.path.join(CSV_DIR, f"hourly_energy_{year}.csv")
        file_exists = os.path.isfile(filename)
        
        with open(filename, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            if not file_exists:
                writer.writerow(["Date", "Hour", "Consumption_Wh", "Production_Wh", "Battery_V", "Battery_A", "Battery_Power_W", "Yield_Today", "Yield_Yesterday", "Timestamp"])
                print(f"   -> [CSV] Created new file: {filename}", flush=True)
            
            writer.writerow([
                date_str, 
                hour_str, 
                f"{cons_val:.4f}", 
                f"{prod_val:.4f}",
                f"{batt_v:.2f}",
                f"{batt_i:.2f}",
                f"{batt_p:.2f}",
                f"{yield_today:.2f}",
                f"{yield_yesterday:.2f}",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])
            
        print(f"   -> [CSV] Record saved to {filename}", flush=True)
    except Exception as e:
        print(f"   -> [CSV Error] Could not save to file: {e}", flush=True)

def keep_alive_worker(client, pid):
    topic = f"R/{pid}/system/0/Serial"
    print(f"[Keep-Alive] Started for Portal ID: {pid}. Sending heartbeat to {topic}", flush=True)
    while True:
        try:
            client.publish(topic, payload="")
        except Exception as e:
            print(f"[Keep-Alive] Error: {e}", flush=True)
        time.sleep(50) 

def start_keep_alive(client, pid):
    t = threading.Thread(target=keep_alive_worker, args=(client, pid), daemon=True)
    t.start()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[MQTT] Connected! Subscribing to N/# ...", flush=True)
        client.subscribe("N/#")
    else:
        print(f"[MQTT] Connection failed code: {rc}", flush=True)

def on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"?? [MQTT] Unexpected disconnection (RC={rc}). Auto-reconnect enabled.", flush=True)
    else:
        print(f"[MQTT] Disconnected cleanly.", flush=True)

def on_message(client, userdata, msg):
    global current_power, current_battery, current_yield, last_update_time, portal_id
    topic = msg.topic
    
    topic_parts = topic.split('/')
    if len(topic_parts) > 1 and portal_id is None:
        possible_id = topic_parts[1]
        if len(possible_id) > 5:
            portal_id = possible_id
            print(f"[System] Found Portal ID: {portal_id}", flush=True)
            start_keep_alive(client, portal_id)

    is_consumption = TOPIC_CONSUMPTION in topic
    is_production = TOPIC_PRODUCTION in topic
    is_battery = "system/0/Dc/Battery" in topic
    is_yield_today = "History/Daily/0/Yield" in topic
    is_yield_yesterday = "History/Daily/1/Yield" in topic

    if not (is_consumption or is_production or is_battery or is_yield_today or is_yield_yesterday):
        return

    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        if 'value' not in payload: 
            return
        
        raw_val = payload['value']
        
        if raw_val is None:
            val = 0.0
        else:
            try:
                val = float(raw_val)
            except (ValueError, TypeError):
                return 
        
        current_time = time.time()

        if is_consumption:
            current_power["consumption"] = val
            last_update_time["consumption"] = current_time
            
        elif is_production:
            current_power["production"] = val
            last_update_time["production"] = current_time
            
        elif is_battery:
            if "Voltage" in topic:
                current_battery["voltage"] = val
            elif "Current" in topic:
                current_battery["current"] = val
            elif "Power" in topic:
                current_battery["power"] = val
                
        elif is_yield_today:
            current_yield["today"] = val
            
        elif is_yield_yesterday:
            current_yield["yesterday"] = val
            
    except Exception as e:
        print(f"[MQTT Error] {e} in topic {msg.topic}", flush=True)

def background_energy_calculator():
    global energy_buffer, current_power, current_battery, current_yield, last_update_time, ghost_energy
    global battery_accumulator, web_display_snapshot
    
    print("[Background] Calculator Started.", flush=True)

    while True:
        try:
            time.sleep(SAMPLING_INTERVAL)

            time_factor = SAMPLING_INTERVAL / 3600.0
            current_ts = time.time()
            
            staleness_cons = current_ts - last_update_time["consumption"]
            
            if staleness_cons > DATA_TIMEOUT:
                if ghost_energy["consumption"] > 0:
                    energy_buffer["consumption"] -= ghost_energy["consumption"]
                    if energy_buffer["consumption"] < 0: energy_buffer["consumption"] = 0.0
                    ghost_energy["consumption"] = 0.0
                
                p_cons = 0.0
            else:
                p_cons = current_power["consumption"]
                inc = p_cons * time_factor
                
                if staleness_cons < (SAMPLING_INTERVAL + 5):
                    ghost_energy["consumption"] = 0.0
                else:
                    ghost_energy["consumption"] += inc

                energy_buffer["consumption"] += inc

            staleness_prod = current_ts - last_update_time["production"]
            
            if staleness_prod > DATA_TIMEOUT:
                if ghost_energy["production"] > 0:
                    energy_buffer["production"] -= ghost_energy["production"]
                    if energy_buffer["production"] < 0: energy_buffer["production"] = 0.0
                    ghost_energy["production"] = 0.0
                
                p_prod = 0.0
            else:
                p_prod = current_power["production"]
                inc = p_prod * time_factor
                
                if staleness_prod < (SAMPLING_INTERVAL + 5):
                    ghost_energy["production"] = 0.0
                else:
                    ghost_energy["production"] += inc

                energy_buffer["production"] += inc

            battery_accumulator["voltage_sum"] += current_battery["voltage"]
            battery_accumulator["power_sum"] += current_battery["power"]
            battery_accumulator["count"] += 1

            now = datetime.now()
            current_minute = now.minute
            is_report_time = (current_minute % REPORT_INTERVAL_MINUTES == 0)
            
            if is_report_time and (current_minute != energy_buffer["last_saved_minute"]):
                
                if battery_accumulator["count"] > 0:
                    avg_v = battery_accumulator["voltage_sum"] / battery_accumulator["count"]
                    avg_p = battery_accumulator["power_sum"] / battery_accumulator["count"]
                else:
                    avg_v = current_battery["voltage"]
                    avg_p = current_battery["power"]
                    
                web_display_snapshot["battery"]["voltage"] = round(avg_v, 2)
                web_display_snapshot["battery"]["power"] = round(avg_p, 2)
                web_display_snapshot["yield"]["today"] = current_yield["today"]
                web_display_snapshot["yield"]["yesterday"] = current_yield["yesterday"]
                
                battery_accumulator["voltage_sum"] = 0.0
                battery_accumulator["power_sum"] = 0.0
                battery_accumulator["count"] = 0

                target_date = now
                if current_minute == 0:
                    target_date = now - timedelta(minutes=1)
                
                current_date_str = target_date.strftime("%Y-%m-%d")
                current_hour_str = target_date.strftime("%H:00") 
                
                cons_val = energy_buffer["consumption"]
                if cons_val >= 0: 
                    try:
                        redis_model.add_consumption(TARGET_EMAIL, current_date_str, current_hour_str, cons_val)
                    except Exception as e:
                        pass
                
                prod_val = energy_buffer["production"]
                if prod_val >= 0:
                    try:
                        redis_model.add_production(TARGET_EMAIL, current_date_str, current_hour_str, prod_val)
                    except Exception as e:
                        pass

                batt_v = current_battery["voltage"]
                batt_i = current_battery["current"]
                batt_p = current_battery["power"]
                try:
                    redis_model.add_battery_status(TARGET_EMAIL, current_date_str, current_hour_str, batt_v, batt_i, batt_p)
                except Exception as e:
                    pass
                    
                y_today = current_yield["today"]
                y_yesterday = current_yield["yesterday"]
                try:
                    redis_model.add_yield_status(TARGET_EMAIL, current_date_str, current_hour_str, y_today, y_yesterday)
                except Exception as e:
                    pass
                
                if cons_val > 0 or prod_val > 0 or batt_v > 0 or y_today > 0:
                    save_hourly_csv(current_date_str, current_hour_str, cons_val, prod_val, batt_v, batt_i, batt_p, y_today, y_yesterday)

                energy_buffer["consumption"] = 0.0
                energy_buffer["production"] = 0.0
                energy_buffer["last_saved_minute"] = current_minute

        except Exception as e:
            time.sleep(5)
            
            
def start_mqtt_thread():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
    except Exception as e:
        print(f"Could not connect to MQTT Broker: {e}")
        return

    calc_thread = threading.Thread(target=background_energy_calculator)
    calc_thread.daemon = True 
    calc_thread.start()

# --- Routes ---
@app.route("/users/create_user", methods=["POST"])
def create_user():
    try:
        data = request.get_json()
        user_email = data.get("user_email")
        user_name = data.get("user_name")
        user_password = data.get("user_password")
    except Exception as error:
        return jsonify({"error": f"Invalid input: {str(error)}"}), 400
    if not all([user_email, user_name, user_password]):
        return jsonify({"error": "Missing required fields"}), 400
    if not is_valid_email(user_email):
        return jsonify({"error": "Invalid email format"}), 400
    try:
        response = redis_model.create_user(user_name, user_email, user_password)
        return jsonify(response), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500
        
@app.route("/users/energy_data", methods=["GET"])
def get_energy_data():
    global web_display_snapshot, current_yield
    
    payload = {
        "battery": web_display_snapshot["battery"],
        "yield": {
            "today": current_yield["today"],
            "yesterday": current_yield["yesterday"]
        }
    }
    
    return jsonify(payload), 200

@app.route("/users/get_battery_day", methods=["POST"])
def get_battery_day():
    try:
        data = request.get_json()
        user_email = data.get("email")
        target_date = datetime.now().strftime("%Y-%m-%d")
        
        if not user_email:
            return jsonify({"error": "Missing email parameter"}), 400
            
        battery_history = redis_model.get_battery_history(user_email, target_date)
        return jsonify({"hourly": battery_history}), 200
        
    except Exception as error:
        return jsonify({"error": str(error)}), 500

if __name__ == '__main__':
    start_mqtt_thread()
    app.run(debug=False, use_reloader=False, host='0.0.0.0', port=5007)
