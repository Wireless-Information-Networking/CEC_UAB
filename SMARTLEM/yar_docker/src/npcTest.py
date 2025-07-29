import json
from colorama import Fore, Style
import matplotlib.pyplot as plt
from datetime import datetime

# Rango esperado de consumo energético real (hogar de 3 personas en España)
# Fuente: IDAE y REE (~9–10 kWh/día x 7 días)
EXPECTED_ENERGY_MIN = 63.0  # kWh en 7 días (~9 kWh/día)
EXPECTED_ENERGY_MAX = 70.0  # kWh en 7 días (~10 kWh/día)
SIMULATION_DAYS = 7

def analyze_simulation(file_path, simulation_days=SIMULATION_DAYS):
    with open(file_path, 'r') as f:
        data = json.load(f)

    if 'total_energy_used' not in data:
        raise ValueError("Missing 'total_energy_used' key in JSON.")

    total_energy = data['total_energy_used']

    daily_energy = total_energy / simulation_days

    energy_within_range = EXPECTED_ENERGY_MIN <= total_energy <= EXPECTED_ENERGY_MAX

    expected_energy_midpoint = (EXPECTED_ENERGY_MIN + EXPECTED_ENERGY_MAX) / 2

    energy_accuracy = (1 - abs(total_energy - expected_energy_midpoint) / expected_energy_midpoint) * 100

    energy_color = (
        Fore.GREEN if energy_within_range else
        Fore.YELLOW if EXPECTED_ENERGY_MIN * 0.9 <= total_energy <= EXPECTED_ENERGY_MAX * 1.1 else
        Fore.RED
    )

    print(f"Total energy used: {energy_color}{total_energy} kWh{Style.RESET_ALL}")
    print(f"Average daily energy: {energy_color}{daily_energy:.2f} kWh/day{Style.RESET_ALL}")

    print("\nComparison with real-life averages:")
    print(f"Energy usage {energy_color}{'is within' if energy_within_range else 'is outside'}{Style.RESET_ALL} expected range ({EXPECTED_ENERGY_MIN}-{EXPECTED_ENERGY_MAX} kWh).")

    print("\nAccuracy assessment:")
    print(f"Energy accuracy: {energy_color}{energy_accuracy:.2f}%{Style.RESET_ALL}")

def plot_npc_awake_times(file_path):
    with open(file_path, "r") as f:
        data = json.load(f)
        if "actions" not in data:
            raise ValueError("Missing 'actions' key in JSON.")
        
        for npc in set(action["npc"] for action in data["actions"]):
            times = [datetime.fromisoformat(action["timestamp"]) for action in data["actions"] if action["npc"] == npc]
            awake = [0 if action["action"] == "sleep" else 1 for action in data["actions"] if action["npc"] == npc]
            plt.plot(times, awake, label=npc)
        plt.xlabel("Time")
        plt.ylabel("Awake (1) / Sleep (0)")
        plt.title("NPC Awake/Sleep States Over Time")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.show()

if __name__ == "__main__":
    file_path = "results/user_data.json"  # Simulation for 7 days
    analyze_simulation(file_path)
    plot_npc_awake_times(file_path)
