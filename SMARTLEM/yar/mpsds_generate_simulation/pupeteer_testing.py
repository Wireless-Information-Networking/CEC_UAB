import json
from datetime import datetime
import matplotlib.pyplot as plt

# Load the simulation output data
output_file = "john_doe's_smart_house_output.json"
with open(output_file, "r") as f:
    data = json.load(f)

# Function to parse timestamp and extract time
def get_time_from_timestamp(ts):
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))  # Handle UTC if present
    return dt.time()

# Define everyone's out-of-home period (09:00 to 14:00)
start_out = datetime.strptime("09:00", "%H:%M").time()
end_out = datetime.strptime("14:00", "%H:%M").time()

# Initialize accumulators
total_electricity_kwh = 0
total_water_liters = 0
out_period_electricity_kwh = 0
out_period_water_liters = 0

# Device usage tracking
device_usage_counts = {
    "Bathroom_shower": {"count": 0, "was_on": False, "max": 1},
    "Bathroom_toilet": {"count": 0, "was_on": False, "max": 6},
    "Kitchen_stove": {"count": 0, "was_on": False, "max": 3},
    "Living Room_tv": {"count": 0, "was_on": False, "max": 2}
}

# Time series data for plotting
timestamps = []
solar_production = []
battery_charge = []

# Process each timestamp entry
for entry in data:
    ts = entry["timestamp"]
    time = get_time_from_timestamp(ts)
    energy_sensors = entry["energy_management_sensors"]
    water_sensors = entry["water_management_sensors"]
    electricity_devices = energy_sensors["energy_efficiency"]["device_consumption"]
    water_devices = water_sensors["device_consumption"]
    water_usage = water_sensors["usage_tracking"]

    # Calculate electricity consumption (kW to kWh for 5-minute intervals)
    electricity_kw = sum(float(v) for v in electricity_devices.values())
    electricity_kwh = electricity_kw * (5 / 60)  # 5 minutes = 1/12 hour
    total_electricity_kwh += electricity_kwh

    # Accumulate water usage
    total_water_liters += float(water_usage)

    # Check out-of-home period
    in_out_period = start_out <= time < end_out
    if in_out_period:
        out_period_electricity_kwh += electricity_kwh
        out_period_water_liters += water_usage

    # Count device uses
    for device, info in device_usage_counts.items():
        consumption = float(water_devices.get(device, 0) if "Bathroom" in device else electricity_devices.get(device, 0))
        if consumption > 0 and not info["was_on"]:
            info["count"] += 1
            info["was_on"] = True
        elif consumption == 0:
            info["was_on"] = False

    # Collect data for plotting
    timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
    solar_production.append(float(energy_sensors["solar_power"]["production"]))
    battery_charge.append(float(energy_sensors["battery"]["charge_level"]))

# ANSI escape codes for colors
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Analysis and validation
print("### Simulation Analysis Results ###\n")

# Total consumption
print("**Total Consumption:**")
print(f"- Electricity: {total_electricity_kwh:.2f} kWh")
print(f"- Water: {total_water_liters:.2f} liters")
typical_elec_range = (10, 30)  # kWh/day for a family of three
typical_water_range = (300, 600)  # liters/day for three people
elec_within_range = typical_elec_range[0] <= total_electricity_kwh <= typical_elec_range[1]
water_within_range = typical_water_range[0] <= total_water_liters <= typical_water_range[1]
print(f"- Electricity within typical range ({typical_elec_range[0]}-{typical_elec_range[1]} kWh)? "
      f"{Colors.OKGREEN if elec_within_range else Colors.FAIL}{'Yes' if elec_within_range else 'No'}{Colors.ENDC}")
print(f"- Water within typical range ({typical_water_range[0]}-{typical_water_range[1]} liters)? "
      f"{Colors.OKGREEN if water_within_range else Colors.FAIL}{'Yes' if water_within_range else 'No'}{Colors.ENDC}\n")

# Out-of-home period (09:00-14:00, 5 hours)
print("**Out-of-Home Period (09:00-14:00):**")
print(f"- Electricity: {out_period_electricity_kwh:.2f} kWh")
print(f"- Water: {out_period_water_liters:.2f} liters")
refrigerator_kwh = 0.15 * 5  # 150W * 5 hours
expected_elec = abs(out_period_electricity_kwh - refrigerator_kwh) < 0.1
expected_water = out_period_water_liters == 0
print(f"- Expected electricity (refrigerator only, ~{refrigerator_kwh:.2f} kWh)? "
      f"{Colors.OKGREEN if expected_elec else Colors.FAIL}{'Yes' if expected_elec else 'No'}{Colors.ENDC}")
print(f"- Water usage expected to be 0? "
      f"{Colors.OKGREEN if expected_water else Colors.FAIL}{'Yes' if expected_water else 'No'}{Colors.ENDC}\n")

# Device usage
print("**Device Usage Counts:**")
for device, info in device_usage_counts.items():
    exceeds = info["count"] > info["max"]
    print(f"- {device}: {info['count']} uses (Max: {info['max']}) - "
          f"{Colors.FAIL if exceeds else Colors.OKGREEN}{'Exceeds limit' if exceeds else 'Within limit'}{Colors.ENDC}")
print(f"Note: Shower max_uses_per_day=1 may be per device; expect ~3 uses for 3 people.\n")

# Plotting
plt.figure(figsize=(12, 8))

# Solar production
plt.subplot(2, 1, 1)
plt.plot(timestamps, solar_production, label="Solar Production (kW)")
plt.xlabel("Time")
plt.ylabel("Power (kW)")
plt.title("Solar Production Over Time")
plt.legend()
plt.grid(True)

# Battery charge
plt.subplot(2, 1, 2)
plt.plot(timestamps, battery_charge, label="Battery Charge (kWh)", color="orange")
plt.xlabel("Time")
plt.ylabel("Charge (kWh)")
plt.title("Battery Charge Level Over Time")
plt.legend()
plt.grid(True)

plt.tight_layout()
plt.show()