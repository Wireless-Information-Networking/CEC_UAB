#!/usr/bin/env python3
"""
venus_log_to_excel.py

Description:
1. Connects to Venus OS (IP: 158.109.75.3).
2. LOGS every 1 second.
3. Calculates Hourly Energy (kWh) for Inverter (Consumption) and Solar (Prosumption).
4. Auto-resets kWh counter at the start of every new hour.

Target Data:
- Inverter Power (W) -> Calculates Consumption (kWh)
- Solar Power (W)    -> Calculates Prosumption (kWh)
"""

import paho.mqtt.client as mqtt
import json
import time
import threading
import sys
import csv
import os
from datetime import datetime

# === Configuration ===
TARGET_IP = '158.109.75.3'
CSV_FILENAME = 'victron_energy_hourly.csv'  # Changed filename to reflect energy data
LOG_INTERVAL = 1.0  # Sampling interval in seconds (Requested: 1s)

# === DATA SOURCE MAPPING ===
KEY_INVERTER_W = 'inverter_289_Ac_Out_L1_S'
KEY_SOLAR_W = 'solarcharger_288_Yield_Power'

# List of keys to fetch from MQTT
TARGET_COLUMNS = [
    KEY_INVERTER_W,
    KEY_SOLAR_W
]
# =====================

# Global variables
portal_id = None
devices_data = {}
current_hour = None
energy_consumption_kwh = 0.0
energy_prosumption_kwh = 0.0
last_sample_time = None


def on_connect(client, userdata, flags, rc):
    """Callback when connected to MQTT Broker"""
    if rc == 0:
        print(f"[MQTT] Connected to {TARGET_IP}!")
        client.subscribe("N/#")
    else:
        print(f"[MQTT] Connection failed, code: {rc}")


def on_message(client, userdata, msg):
    """Callback when message received"""
    global portal_id

    topic_parts = msg.topic.split('/')
    if len(topic_parts) < 5: return

    # 1. Auto-detect Portal ID
    current_id = topic_parts[1]
    if portal_id is None:
        portal_id = current_id
        print(f"[System] Portal ID found: {portal_id}")
        start_keep_alive(client, portal_id)

    if current_id != portal_id: return

    # 2. Parse basic info
    service_type = topic_parts[2]
    device_instance = topic_parts[3]
    device_key = f"{service_type}/{device_instance}"

    # Filter devices
    if device_key != 'inverter/289' and device_key != 'solarcharger/288':
        return

    # 3. Store data
    path = "/".join(topic_parts[4:])

    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        if 'value' in payload:
            if device_key not in devices_data: devices_data[device_key] = {}
            devices_data[device_key][path] = payload['value']
    except:
        pass


def keep_alive_worker(client, pid):
    topic = f"R/{pid}/system/0/Serial"
    while True:
        try:
            client.publish(topic, payload="")
        except:
            pass
        time.sleep(50)


def start_keep_alive(client, pid):
    t = threading.Thread(target=keep_alive_worker, args=(client, pid), daemon=True)
    t.start()


def flatten_data(data_dict):
    """Converts nested dict to flat format"""
    flat = {}
    for dev_key, metrics in data_dict.items():
        clean_dev_key = dev_key.replace('/', '_')
        for path, value in metrics.items():
            clean_path = path.replace('/', '_')
            full_key = f"{clean_dev_key}_{clean_path}"
            flat[full_key] = value
    return flat


def logger_loop():
    global current_hour, energy_consumption_kwh, energy_prosumption_kwh, last_sample_time

    print(f"Waiting 3 seconds to sync data...")
    time.sleep(3)

    # Initialize timing
    current_hour = datetime.now().hour
    last_sample_time = time.time()

    print(f"=== Logging started: {CSV_FILENAME} ===")
    print(f"Interval: {LOG_INTERVAL}s | Mode: Hourly kWh Calculation")

    # Define Headers
    headers = [
        'Timestamp',
        'Inverter_Power_W',  # Instantaneous
        'Solar_Power_W',  # Instantaneous
        'Consumption_kWh_Hourly',  # Calculated Accumulator
        'Prosumption_kWh_Hourly'  # Calculated Accumulator
    ]

    # Initialize CSV
    try:
        with open(CSV_FILENAME, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
    except PermissionError:
        print("Error: Close the Excel file!")
        return

    while True:
        try:
            # Precise sleep to maintain 1s interval
            time.sleep(LOG_INTERVAL)

            # 1. Time Logic
            now = datetime.now()
            now_ts = time.time()

            # Calculate time difference since last sample (usually ~1.0s)
            # using actual delta ensures accuracy even if loop lags
            time_delta_sec = now_ts - last_sample_time
            last_sample_time = now_ts

            # 2. Check for Hour Change (Reset Logic)
            if now.hour != current_hour:
                print(f"\n>>> New Hour Detected ({now.hour}:00)! Resetting kWh counters.\n")
                current_hour = now.hour
                energy_consumption_kwh = 0.0
                energy_prosumption_kwh = 0.0

            # 3. Get Instantaneous Power (W)
            flat_data = flatten_data(devices_data)

            # Get values, default to 0.0 if missing
            inv_w = float(flat_data.get(KEY_INVERTER_W, 0.0) or 0.0)
            solar_w = float(flat_data.get(KEY_SOLAR_W, 0.0) or 0.0)

            # 4. Calculate Energy (kWh) integration
            # Energy (kWh) = Power (W) * Time (hours) / 1000
            # Time (hours) = time_delta_sec / 3600

            # Avoid negative power values if any (unlikely for load/solar but good safety)
            inv_w = max(0.0, inv_w)
            solar_w = max(0.0, solar_w)

            kWh_increment_inv = (inv_w * time_delta_sec) / 3600000.0
            kWh_increment_solar = (solar_w * time_delta_sec) / 3600000.0

            energy_consumption_kwh += kWh_increment_inv
            energy_prosumption_kwh += kWh_increment_solar

            # 5. Write Row
            timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')

            row = [
                timestamp_str,
                f"{inv_w:.2f}",
                f"{solar_w:.2f}",
                f"{energy_consumption_kwh:.6f}",  # High precision for 1s intervals
                f"{energy_prosumption_kwh:.6f}"
            ]

            with open(CSV_FILENAME, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(row)

            # Print status every 5 seconds or so to avoid spamming console
            if int(now_ts) % 5 == 0:
                print(
                    f"[{timestamp_str}] Inv: {inv_w}W | Sol: {solar_w}W | Cons: {energy_consumption_kwh:.5f} kWh | Pros: {energy_prosumption_kwh:.5f} kWh")

        except PermissionError:
            print("Permission Denied: Please close Excel file.")
        except Exception as e:
            print(f"Error: {e}")


def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to {TARGET_IP}...")
    try:
        client.connect(TARGET_IP, 1883, 60)
        client.loop_start()
        logger_loop()
    except KeyboardInterrupt:
        client.loop_stop()
        sys.exit(0)
    except Exception as e:
        print(f"Connection Error: {e}")


if __name__ == '__main__':
    main()