import os
import logging
import time
import threading
import json
import re
import hashlib
import redis
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import paho.mqtt.client as mqtt

# ================= Configuration =================
MQTT_BROKER = '158.109.75.3'   #the IP from the victron raspberry
MQTT_PORT = 1883

TARGET_EMAIL = "example@uab.cat"  #already register this e-mail


TOPIC_CONSUMPTION = "inverter/289/Ac/Out/L1/S" 
TOPIC_PRODUCTION = "solarcharger/288/Yield/Power"


SAMPLING_INTERVAL = 30  #every 30s will read the datas one time
REPORT_INTERVAL_MINUTES = 15  #every 15 minutes will restore the datas
# =================================================

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

redis_model = RedisModel()

# --- MQTT Logic ---

current_power = {
    "consumption": 0.0,
    "production": 0.0
}

energy_buffer = {
    "consumption": 0.0,
    "production": 0.0,
    "last_saved_minute": -1 
}

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[MQTT] Connected! Sampling {SAMPLING_INTERVAL}s, Reporting {REPORT_INTERVAL_MINUTES}m...", flush=True)
        client.subscribe("N/#")
    else:
        print(f"[MQTT] Connection failed code: {rc}", flush=True)

def on_message(client, userdata, msg):
    global current_power
    topic = msg.topic
    
    if TOPIC_CONSUMPTION not in topic and TOPIC_PRODUCTION not in topic:
        return

    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        
        if 'value' not in payload: return
        
        raw_val = payload['value']
        
        if raw_val is None:
            val = 0.0
        else:
            val = float(raw_val)
        
        if TOPIC_CONSUMPTION in topic:
            current_power["consumption"] = val
        elif TOPIC_PRODUCTION in topic:
            current_power["production"] = val
            
    except Exception as e:
        print(f"[MQTT Error] {e}", flush=True)

def background_energy_calculator():
    global energy_buffer, current_power
    
    print(f"[Background] Calculator Started. Reporting every {REPORT_INTERVAL_MINUTES}m", flush=True)

    while True:
        time.sleep(SAMPLING_INTERVAL)

        time_factor = SAMPLING_INTERVAL / 3600.0
        
        inc_cons = current_power["consumption"] * time_factor
        inc_prod = current_power["production"] * time_factor
        
        energy_buffer["consumption"] += inc_cons
        energy_buffer["production"] += inc_prod
        
        now = datetime.now()
        current_minute = now.minute
        
        is_report_time = (current_minute % REPORT_INTERVAL_MINUTES == 0)
        
        if is_report_time and (current_minute != energy_buffer["last_saved_minute"]):
            
            target_date = now
            if current_minute == 0:
                target_date = now - timedelta(minutes=1)
            
            current_date_str = target_date.strftime("%Y-%m-%d")
            current_hour_str = target_date.strftime("%H:00") 
            
            print(f"\n[Auto-Save {now.strftime('%H:%M')}] Flushing to Key: {current_hour_str}...", flush=True)
            print(f" -> Buffer Status: Cons={energy_buffer['consumption']:.4f} Wh, Prod={energy_buffer['production']:.4f} Wh", flush=True)
            
            # --- Consumption ---
            cons_val = energy_buffer["consumption"]
            if cons_val >= 0: 
                try:
                    redis_model.add_consumption(TARGET_EMAIL, current_date_str, current_hour_str, cons_val)
                    print(f"   -> [SAVED] Consumption: {cons_val:.4f} Wh", flush=True)
                except Exception as e:
                    print(f"   -> Error saving cons: {e}", flush=True)
            
            # --- Production ---
            prod_val = energy_buffer["production"]
            if prod_val >= 0:
                try:
                    redis_model.add_production(TARGET_EMAIL, current_date_str, current_hour_str, prod_val)
                    print(f"   -> [SAVED] Production: {prod_val:.4f} Wh", flush=True)
                except Exception as e:
                    print(f"   -> Error saving prod: {e}", flush=True)
            
            energy_buffer["consumption"] = 0.0
            energy_buffer["production"] = 0.0
            energy_buffer["last_saved_minute"] = current_minute

def start_mqtt_thread():
    client = mqtt.Client()
    client.on_connect = on_connect
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

# --- Routes  ---
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

@app.route("/users/add_consumption", methods=["POST"])
def add_consumption():
    try:
        data = request.get_json()
        user_email = data.get("user_email")
        date = data.get("date")
        hour = data.get("hour")
        value = data.get("value")
    except Exception as error:
        return jsonify({"error": f"Invalid input: {str(error)}"}), 400
    if not is_valid_email(user_email):
        return jsonify({"error": "Invalid email format"}), 400
    try:
        value = float(value)
    except ValueError:
        return jsonify({"error": "Value must be a number"}), 400
    try:
        response = redis_model.add_consumption(user_email, date, hour, value)
        return jsonify(response), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500

@app.route("/users/add_production", methods=["POST"])
def add_production():
    try:
        data = request.get_json()
        user_email = data.get("user_email")
        date = data.get("date")
        hour = data.get("hour")
        value = data.get("value")
    except Exception as error:
        return jsonify({"error": f"Invalid input: {str(error)}"}), 400
    if not is_valid_email(user_email):
        return jsonify({"error": "Invalid email format"}), 400
    try:
        value = float(value)
    except ValueError:
        return jsonify({"error": "Value must be a number"}), 400
    try:
        response = redis_model.add_production(user_email, date, hour, value)
        return jsonify(response), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500

if __name__ == '__main__':
    start_mqtt_thread()
    app.run(debug=False, use_reloader=False, host='0.0.0.0', port=5007)
