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
MQTT_BROKER = '158.109.75.3'
MQTT_PORT = 1883

TARGET_EMAIL = "example@uab.cat" 

# Topic
TOPIC_CONSUMPTION = "inverter/289/Ac/Out/L1/S" 
TOPIC_PRODUCTION = "solarcharger/288/Yield/Power"

SAMPLING_INTERVAL = 30       
REPORT_INTERVAL_MINUTES = 15 
DATA_TIMEOUT = 900
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

portal_id = None

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
    global current_power, last_update_time, portal_id
    topic = msg.topic
    
    topic_parts = topic.split('/')
    if len(topic_parts) > 1 and portal_id is None:
        possible_id = topic_parts[1]
        if len(possible_id) > 5:
            portal_id = possible_id
            print(f"?? [System] Found Portal ID: {portal_id}", flush=True)
            start_keep_alive(client, portal_id)

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
        
        current_time = time.time()

        if TOPIC_CONSUMPTION in topic:
            current_power["consumption"] = val
            last_update_time["consumption"] = current_time
            
        elif TOPIC_PRODUCTION in topic:
            current_power["production"] = val
            last_update_time["production"] = current_time
            
    except Exception as e:
        print(f"[MQTT Error] {e}", flush=True)

def background_energy_calculator():
    global energy_buffer, current_power, last_update_time, ghost_energy
    
    print(f"[Background] Calculator Started.", flush=True)

    while True:
        try:
            time.sleep(SAMPLING_INTERVAL)

            time_factor = SAMPLING_INTERVAL / 3600.0
            current_ts = time.time()
            
            # --- Consumption ---
            staleness_cons = current_ts - last_update_time["consumption"]
            
            if staleness_cons > DATA_TIMEOUT:
                if ghost_energy["consumption"] > 0:
                    print(f"?? [Rollback] Cons idle for {int(staleness_cons)}s. Removing {ghost_energy['consumption']:.4f} Wh ghost data.", flush=True)
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

            # --- Production ---
            staleness_prod = current_ts - last_update_time["production"]
            
            if staleness_prod > DATA_TIMEOUT:
                if ghost_energy["production"] > 0:
                    print(f"?? [Rollback] Prod idle for {int(staleness_prod)}s. Removing {ghost_energy['production']:.4f} Wh ghost data.", flush=True)
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

            print(f"[Tick 30s] Cons={p_cons}W, Prod={p_prod}W | Buffer Cons={energy_buffer['consumption']:.4f}Wh", flush=True)

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
                
                # Save Consumption
                cons_val = energy_buffer["consumption"]
                if cons_val >= 0: 
                    try:
                        redis_model.add_consumption(TARGET_EMAIL, current_date_str, current_hour_str, cons_val)
                        print(f"   -> [SAVED] Consumption: {cons_val:.4f} Wh", flush=True)
                    except Exception as e:
                        print(f"   -> Error saving cons: {e}", flush=True)
                
                # Save Production
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

        except Exception as e:
            print(f"?? [Critical Error] Background thread crashed: {e}", flush=True)
            print("   -> Restarting loop in 5 seconds...", flush=True)
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

if __name__ == '__main__':
    start_mqtt_thread()
    app.run(debug=False, use_reloader=False, host='0.0.0.0', port=5007)
