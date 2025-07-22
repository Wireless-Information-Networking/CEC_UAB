import json
import requests
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import time as tempo

# Load the JSON data
file_path = 'battery_history.json'
with open(file_path, 'r') as file:
    data = json.load(file)

# Extract readings
readings = data.get("readings", [])
if not readings:
    print("No readings found in the dataset.")
    exit()

# Get tomorrow's date as the starting point
start_date = datetime.today() + timedelta(days=1)

# Configuration
user_email = "jhondoe@uab.cat"
url_consumption = 'https://sirienergy.uab.cat/add_consumption'
url_production = 'https://sirienergy.uab.cat/add_production'

# Loop through 30 days
for day in range(15):
    current_date = start_date + timedelta(days=day)
    date_str = current_date.strftime("%Y-%m-%d")
    print(f"\nProcessing date: {date_str}")
    
    # Parse timestamps and filter the first 24 hours of original data
    timestamps = [datetime.fromisoformat(entry["timestamp"]) for entry in readings]
    original_start_time = timestamps[0]
    original_end_time = original_start_time + timedelta(hours=24)
    
    # Filter data within the 24-hour period from original dataset
    filtered_readings = [entry for entry in readings 
                        if original_start_time <= datetime.fromisoformat(entry["timestamp"]) <= original_end_time]
    
    # Get the hourly data
    rounded_times = [datetime.fromisoformat(entry["timestamp"]).replace(
        minute=0, second=0, microsecond=0) for entry in filtered_readings]
    total_productions = [entry["solar_prod"] for entry in filtered_readings]
    total_consumptions = [entry["total_consumpt"] for entry in filtered_readings]
    
    # Upload each hour's data
    for time, production, consumption in zip(rounded_times, total_productions, total_consumptions):
        hour_str = time.strftime("%H:00")
        
        # Upload consumption
        consumption_data = {
            "user_email": user_email,
            "date": date_str,
            "hour": hour_str,
            "value": consumption
        }
        consumption_response = requests.post(url_consumption, json=consumption_data)
        print(f"Consumption upload response at {date_str} {hour_str}: {consumption_response.text}")
        
        # Upload production
        production_data = {
            "user_email": user_email,
            "date": date_str,
            "hour": hour_str,
            "value": production
        }
        production_response = requests.post(url_production, json=production_data)
        print(f"Production upload response at {date_str} {hour_str}: {production_response.text}")
        
        # Add a small delay to avoid overwhelming the server
        tempo.sleep(0.5)