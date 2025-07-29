import time
from datetime import datetime, timedelta, timezone
import random
import matplotlib.pyplot as plt
import json
import os

# Personal modules
from climateEnviroment import temperature_humidty_airquality as getTempHomemade

# Constant for energy used to heat one liter of water (kWh per liter)
ENERGY_PER_LITER_HOT_WATER = 0.0322   # Assuming a temperature difference of about 30°C
BASELINE_ELECTRICITY_KWH_PER_5MIN = 0.007  # Baseline electricity usage in kWh for 5 minutes (includes refrigerator, wifi, router, standby devices, etc.)

# Global flags
update_each_seconds = 300  # 5 minutes = 300s
actions_in_minutes = True  # Action durations provided in minutes, converted to seconds

def create_json_reg(house_name: str, FILEPATH, typeOfSimulation, start_date=None, end_date=None):
    # Ensure the directory exists
    os.makedirs(os.path.dirname(FILEPATH), exist_ok=True)
    
    if not os.path.exists(FILEPATH):
        data = {
            "house_name": house_name,
            "total_energy_used": 0,
            "total_water_used": 0,
            "total_time": 0,
            "type_of_simulation": typeOfSimulation,
            "start_date": start_date,
            "end_date": end_date,
            "actions": []
        }
        with open(FILEPATH, "w") as file:
            json.dump(data, file, indent=4)
        print("File created with initial structure. House name: ", house_name)
    else:
        print("File already exists.")

def add_action_to_json(NPCtime, action="NAN", device_used="NAN", energy_used=0, water_used=0, duration=0, npc_name="Unknown", FILEPATH="results/user_data.json", print_message=True):
    with open(FILEPATH, "r") as file:
        data = json.load(file)
    
    formatted_time = NPCtime.isoformat()  # e.g., "2021-01-01T00:05:00+01:00"
    
    new_action = {
        "timestamp": formatted_time,
        "npc": npc_name,
        "action": action,
        "device_used": device_used,
        "energy_used": energy_used,
        "water_used": water_used,
        "duration": duration
    }
    
    data["actions"].append(new_action)
    data["total_energy_used"] += energy_used
    data["total_water_used"] += water_used
    data["total_time"] += duration
    
    with open(FILEPATH, "w") as file:
        json.dump(data, file, indent=4)
    
    timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S')
    if print_message:
        print(f"[{timestamp}] \033[93mAdded action to JSON\033[0m")

class House:
    def __init__(self, config_data, temperature=20, humidity=50, month=1, year=2025):
        # Basic parameters
        self.name = config_data["basic_parameters"]["name"]
        self.number_of_people = config_data["basic_parameters"]["number_of_people"]
        self.rooms = {
            "rooms": config_data["basic_parameters"]["rooms"],
            "bathrooms": config_data["basic_parameters"]["bathrooms"],
            "kitchen": config_data["basic_parameters"]["kitchen"],
            "living_room": config_data["basic_parameters"]["living_room"],
            "dining_room": config_data["basic_parameters"]["dining_room"],
            "garage": config_data["basic_parameters"]["garage"],
            "garden": config_data["basic_parameters"]["garden"]
        }
        
        self.temperature = temperature
        self.humidity = humidity
        self.month = month
        self.year = year
        self.volume = config_data["house"]["volume_cubic_meters"]
        
        # Solar system
        self.solar_system = {
            "panel_efficiency": config_data["solar_panels"]["panel_eff"],
            "number_of_panels": config_data["solar_panels"]["number_of_panels"],
            "panel_size": config_data["solar_panels"]["size_of_panels_m2"]
        }
        
        # Battery system
        self.battery = {
            "capacity": config_data["battery"]["capacity_ah"],
            "voltage": config_data["battery"]["voltage"],
            "state_of_charge": config_data["battery"]["initial_state_of_charge_percent"],
            "charging_efficiency": config_data["battery"]["charging_efficiency"],
            "discharging_efficiency": config_data["battery"]["discharging_efficiency"],
            "energy_loss": config_data["battery"]["energy_loss_conversion"],
            "degrading_ratio": config_data["battery"]["degrading_ratio"]
        }
        
        # Water heating
        self.water_heating = {
            "method": config_data["water_heating"]["selected_method"],
            "available_options": config_data["water_heating"]["options"]
        }
        
        # Emission factors
        self.emission_factors = {
            "solar_panel": {
                "min": config_data["emission_factors"]["solar_panel_emission_factor_kgCO2_per_kWh"]["min"],
                "max": config_data["emission_factors"]["solar_panel_emission_factor_kgCO2_per_kWh"]["max"]
            },
            "cold_water": config_data["emission_factors"]["cold_water_emission_factor_kgCO2_per_L"],
            "hot_water": config_data["emission_factors"]["hot_water_emission_factor_kgCO2_per_L"]
        }
        
        # Devices
        self.water_devices = config_data["water_devices"]
        self.electricity_devices = config_data["electricity_devices"]
        
        self.device_electricity_usage = {}
        for device in self.electricity_devices:
            key = f"{device['room']}_{device['device']}"
            self.device_electricity_usage[key] = 0
        
        self.total_electricity_used_kwh = 0
        self.total_water_used_liters = 0
        
        # Device state tracking with flow type
        self.device_states = {}
        for device in self.water_devices + self.electricity_devices:
            key = f"{device['room']}_{device['device']}"
            flow_type = "per_use" if "flow_rate_liters_per_use" in device else "per_minute" if "flow_rate_liters_per_minute" in device else None
            self.device_states[key] = {
                "type": "water" if device in self.water_devices else "electricity",
                "info": device,
                "in_use": False,
                "used_by": None,
                "flow_type": flow_type
            }
        
        # Daily usage tracking
        self.daily_device_usage = {key: 0 for key in self.device_states}
        self.last_reset = None
        self.time = None  # Updated during simulation

    def reset_daily_usage(self, current_time):
        """Reset daily usage counts at the start of a new day."""
        if self.last_reset is None or current_time.date() != self.last_reset.date():
            self.daily_device_usage = {key: 0 for key in self.device_states}
            self.last_reset = current_time

    def can_use_device(self, device_name, room_name):
        """Check if a device can be used based on max_uses_per_day and availability."""
        key = f"{room_name}_{device_name}"
        if key not in self.device_states:
            return False
        if self.device_states[key]["in_use"]:
            return False
        max_uses = self.device_states[key]["info"].get("max_uses_per_day", float("inf"))
        return self.daily_device_usage[key] < max_uses

    def log_device_usage(self, device_name, room_name):
        """Increment the usage count for a device."""
        key = f"{room_name}_{device_name}"
        self.daily_device_usage[key] += 1

    def is_device_available(self, device_name, room_name):
        """Check if a device is available (not in use)."""
        key = f"{room_name}_{device_name}"
        if key in self.device_states:
            return not self.device_states[key]["in_use"]
        return False

    def get_total_rooms(self):
        return sum(self.rooms.values())

    def get_solar_capacity(self):
        return self.solar_system["number_of_panels"] * self.solar_system["panel_size"]

    def get_battery_capacity_kwh(self):
        return (self.battery["capacity"] * self.battery["voltage"]) / 1000

    def get_device_by_name(self, device_name):
        for device in self.water_devices:
            if device["device"].lower() == device_name.lower():
                return {"type": "water", "device": device}
        for device in self.electricity_devices:
            if device["device"].lower() == device_name.lower():
                return {"type": "electricity", "device": device}
        return None

    def has_device_in_room(self, device_name, room_name):
        for device in self.water_devices + self.electricity_devices:
            if (device["device"].lower() == device_name.lower() and 
                device.get("room", "").lower() == room_name.lower()):
                return True
        return False

class Action:
    def __init__(self, name, duration, location, required_device=None, need_changes=None, next_action=None, allowed_age_groups=None):
        self.name = name
        self.location = location
        self.required_device = required_device
        self.need_changes = need_changes or {}
        self.next_action = next_action
        self.allowed_age_groups = allowed_age_groups or ["child", "teenager", "adult", "elderly"]
        # Duration is now expected in seconds
        self.duration = duration

class NPC:
    def __init__(self, name, out_of_home_periods, house, age_group, sleep_start, sleep_end, simulation_type="fast_forward"):
        self.name = name
        self.age_group = age_group
        self.out_of_home_periods = out_of_home_periods
        self.sleep_start = datetime.strptime(sleep_start, "%H:%M").time()
        self.sleep_end = datetime.strptime(sleep_end, "%H:%M").time()
        self.house = house
        self.current_room = "Living Room"
        self.state = "Idle"
        self.action_start_time = None
        self.current_action = None
        self.action_end_time = None
        self.action_chain = []
        self.needs = {
            "hunger": random.randint(0, 100),
            "energy": random.randint(0, 100),
            "hygiene": random.randint(0, 100),
            "fun": random.randint(0, 100),
            "temperature": 22
        }
        if simulation_type == "realtime":
            self.time = datetime.now(timezone.utc)
        else:
            self.time = datetime.now()
        self.last_toilet_time = self.time
        self.actions = {}
        self._setup_actions()
    
    @property
    def is_awake(self):
        return self.state != "Sleeping"
    
    def is_sleep_time(self, dt):
        sleep_start_time = self.sleep_start
        sleep_end_time = self.sleep_end
        dt_time = dt.time()
        
        if sleep_start_time < sleep_end_time:
            # Sleep period within the same day (e.g., 22:00 to 06:00)
            return sleep_start_time <= dt_time < sleep_end_time
        else:
            # Sleep period crosses midnight (e.g., 23:00 to 08:00)
            return dt_time >= sleep_start_time or dt_time < sleep_end_time



    def _setup_actions(self):
        """Setup actions with durations from config."""
        self.actions = {
            "cook": Action(
                name="cook",
                duration=self._get_duration_from_config("stove", "electricity"),
                location="Kitchen",
                required_device="stove",
                need_changes={"hunger": 0, "energy": -20, "hygiene": -25, "fun": 15},
                allowed_age_groups=["adult", "elderly"]
            ),
            "eat": Action(
                name="eat",
                duration=20 * 60,  # 20 minutes in seconds
                location="Dining Room",
                need_changes={"hunger": -70, "energy": 20, "hygiene": -20, "fun": 20},
                allowed_age_groups=["child", "teenager", "adult", "elderly"]
            ),
            "use_dishwasher": Action(
                name="use_dishwasher",
                duration=self._get_duration_from_config("dishwasher", "electricity"),
                location="Kitchen",
                required_device="dishwasher",
                need_changes={"hunger": 0, "energy": -5, "hygiene": 7, "fun": -10},
                allowed_age_groups=["adult", "elderly"]
            ),
            "wash_hands": Action(
                name="wash_hands",
                duration=self._get_duration_from_config("sink", "water"),
                location="Bathroom",
                required_device="sink",
                need_changes={"hunger": 0, "energy": -2, "hygiene": 30, "fun": 0},
                allowed_age_groups=["child", "teenager", "adult", "elderly"]
            ),
            "brush_teeth": Action(
                name="brush_teeth",
                duration=5 * 60,  # 5 minutes in seconds
                location="Bathroom",
                required_device="sink",
                need_changes={"hunger": 0, "energy": -5, "hygiene": 35, "fun": 0},
                allowed_age_groups=["child", "teenager", "adult", "elderly"]
            ),
            "nap_sleep": Action(
                name="nap_sleep",
                duration=30 * 60,  # 30 minutes in seconds
                location="Bedroom",
                need_changes={"hunger": 20, "energy": 80, "hygiene": -15, "fun": 5},
                allowed_age_groups=["child", "teenager", "adult", "elderly"]
            ),
            "shower": Action(
                name="shower",
                duration=self._get_duration_from_config("shower", "water"),
                location="Bathroom",
                required_device="shower",
                need_changes={"hunger": 0, "energy": 5, "hygiene": 55, "fun": 0},
                allowed_age_groups=["child", "teenager", "adult", "elderly"]
            ),
            "watch_tv": Action(
                name="watch_tv",
                duration=self._get_duration_from_config("tv", "electricity"),
                location="Living Room",
                required_device="tv",
                need_changes={"hunger": 15, "energy": 5, "hygiene": -5, "fun": 35},
                allowed_age_groups=["child", "teenager", "adult", "elderly"]
            ),
            "play_games": Action(
                name="play_games",
                duration=self._get_duration_from_config("gaming_console", "electricity"),
                location="Living Room",
                required_device="gaming_console",
                need_changes={"hunger": 20, "energy": -20, "hygiene": -15, "fun": 30},
                allowed_age_groups=["child", "teenager", "adult", "elderly"]
            ),
            "go_for_walk": Action(
                name="go_for_walk",
                duration=20 * 60,  # 20 minutes in seconds
                location="Outside",
                need_changes={"hunger": 35, "energy": -30, "hygiene": -15, "fun": 25},
                allowed_age_groups=["child", "teenager", "adult", "elderly"]
            ),
            "use_toilet": Action(
                name="use_toilet",
                duration=3 * 60,  # 3 minutes in seconds
                location="Bathroom",
                required_device="toilet",
                need_changes={"hunger": 0, "energy": -1, "hygiene": 5, "fun": 0},
                allowed_age_groups=["child", "teenager", "adult", "elderly"]
            ),
            "call_friend": Action(
                name="call_friend",
                duration=5 * 60,  # 5 minutes in seconds
                location="Living Room",
                need_changes={"hunger": 5, "energy": -5, "hygiene": 0, "fun": 10},
                allowed_age_groups=["child", "teenager", "adult", "elderly"]
            ),
            "read_book": Action(
                name="read_book",
                duration=15 * 60,  # 15 minutes in seconds
                location="Bedroom",
                need_changes={"hunger": 10, "energy": -5, "hygiene": 0, "fun": 20},
                allowed_age_groups=["child", "teenager", "adult", "elderly"]
            ),
            "go_shopping": Action(
                name="go_shopping",
                duration=25 * 60,  # 25 minutes in seconds
                location="Outside",
                need_changes={"hunger": 5, "energy": -5, "hygiene": 0, "fun": 10},
                allowed_age_groups=["adult", "elderly", "teenager"]
            ),
            "go_for_jog": Action(
                name="go_for_jog",
                duration=20 * 60,  # 20 minutes in seconds
                location="Outside",
                need_changes={"hunger": 25, "energy": -20, "hygiene": -15, "fun": 25},
                allowed_age_groups=["adult", "teenager"]
            ),
            "go_to_gym": Action(
                name="go_to_gym",
                duration=30 * 60,  # 30 minutes in seconds
                location="Outside",
                need_changes={"hunger": 30, "energy": -35, "hygiene": -20, "fun": 30},
                allowed_age_groups=["adult", "teenager"]
            ),
            "clean_house": Action(
                name="clean_house",
                duration=self._get_duration_from_config("vacuum_cleaner", "electricity"),
                location="Living Room",
                required_device="vacuum_cleaner",
                need_changes={"hunger": 20, "energy": -20, "hygiene": 20, "fun": -20},
                allowed_age_groups=["adult", "elderly"]
            ),
            "study": Action(
                name="study",
                duration=self._get_duration_from_config("computer", "electricity"),
                location="Bedroom",
                required_device="computer",
                need_changes={"hunger": 15, "energy": -25, "hygiene": -10, "fun": -15},
                allowed_age_groups=["teenager", "adult", "elderly"]
            ),
            "overthink": Action(
                name="overthink",
                duration=10 * 60,  # 10 minutes in seconds
                location="Bedroom",
                need_changes={"hunger": 5, "energy": -10, "hygiene": 0, "fun": -10},
                allowed_age_groups=["adult", "elderly"]
            ),
            
        }
        
        # Setup action chains
        self.actions["cook"].next_action = "eat"
        self.actions["eat"].next_action = "use_dishwasher"
        self.actions["use_dishwasher"].next_action = "wash_hands"
        self.actions["wash_hands"].next_action = "brush_teeth"
        self.actions["go_for_jog"].next_action = "shower"
        self.actions["go_to_gym"].next_action = "shower"

    def _get_duration_from_config(self, device_name, device_type):
        """Get random duration in seconds from config based on device type."""
        device_info = self.house.get_device_by_name(device_name)
        if device_info and "typical_duration" in device_info["device"]:
            min_duration, max_duration = device_info["device"]["typical_duration"]
            # All durations are now assumed to be in minutes for consistency
            duration_minutes = random.uniform(min_duration, max_duration)
            duration_seconds = duration_minutes * 60
            return int(duration_seconds)
        return 300  # Default 5 minutes in seconds if not found

    def update_needs(self):
        """Update needs based on time and house conditions."""
        self.needs["hunger"] = min(100, self.needs["hunger"] + 0.5)
        self.needs["energy"] = max(0, self.needs["energy"] - 0.3)
        self.needs["hygiene"] = max(0, self.needs["hygiene"] - 0.7)
        self.needs["fun"] = max(0, self.needs["fun"] - 0.4)
        
        temp_diff = abs(int(self.house.temperature) - int(self.needs["temperature"]))
        if temp_diff > 5:
            self.needs["energy"] = max(0, self.needs["energy"] - int(temp_diff / 5))
            self.needs["fun"] = max(0, self.needs["fun"] - int(temp_diff / 5))
        
        if (self.time - self.last_toilet_time).seconds >= 7200 and self.actions["use_toilet"] not in self.action_chain:
            self.action_chain.append(self.actions["use_toilet"])
            self.last_toilet_time = self.time

    def is_out_of_home(self):
        current_day = self.time.strftime("%A")
        for period in self.out_of_home_periods:
            if "days" not in period or current_day in period["days"]:
                start_dt = datetime.strptime(f"{self.time.date()} {period['start']}", "%Y-%m-%d %H:%M").replace(tzinfo=self.time.tzinfo)
                end_dt = datetime.strptime(f"{self.time.date()} {period['end']}", "%Y-%m-%d %H:%M").replace(tzinfo=self.time.tzinfo)
                if end_dt < start_dt:
                    end_dt += timedelta(days=1)
                if start_dt <= self.time <= end_dt:
                    return True, period["reason"]
        return False, None

    def decide_next_action(self):
        if self.is_out_of_home()[0]:
            reason = self.is_out_of_home()[1]
            return "out_of_home", reason
        
        if self.action_chain:
            return self.action_chain.pop(0)
        
        if self.needs["energy"] < 20:
            return self.actions["nap_sleep"]
        
        if self.needs["hunger"] > 60:
            self.action_chain = []
            current = self.actions["cook"]
            while current:
                self.action_chain.append(current)
                current = self.actions[current.next_action] if current.next_action else None
            return self.action_chain.pop(0)
        
        if self.needs["hygiene"] < 60:
            return self.actions["shower"]
        
        if self.needs["fun"] < 30:
            return random.choice([self.actions["watch_tv"], self.actions["play_games"]])
        
        if self.needs["energy"] > 80:
            return random.choice([self.actions["go_for_jog"], self.actions["go_to_gym"]])
        
        if self.needs["fun"] > 70:
            return random.choice([self.actions["clean_house"], self.actions["study"], self.actions["overthink"]])
        
        return random.choice([self.actions["call_friend"], self.actions["read_book"], self.actions["go_shopping"]])

    def perform_action(self, action):
        if self.age_group not in action.allowed_age_groups:
            self.activity = f"{self.name} cannot perform {action.name} because it is not allowed for their age group."
            return

        if action.required_device and not self.house.can_use_device(action.required_device, action.location):
            self.activity = f"{self.name} cannot perform {action.name} because {action.required_device} in {action.location} is either in use or has reached daily limit."
            return

        if action.required_device and not self.house.has_device_in_room(action.required_device, action.location):
            self.activity = f"{self.name} cannot perform {action.name} because {action.required_device} is not in {action.location}."
            return

        self.current_room = action.location
        self.state = "Performing Action"
        self.current_action = action
        self.action_start_time = self.time
        self.action_end_time = self.time + timedelta(seconds=action.duration)
        self.activity = f"{self.name} started {action.name} in {self.current_room} (will take {action.duration / 60} minutes)."

        if action.required_device:
            key = f"{action.location}_{action.required_device}"
            self.house.device_states[key]["in_use"] = True
            self.house.device_states[key]["used_by"] = self.name
            self.house.log_device_usage(action.required_device, action.location)

    def finish_action(self):
        if self.current_action and self.state == "Performing Action":
            # Update needs
            for need, change in self.current_action.need_changes.items():
                new_value = self.needs[need] + change
                self.needs[need] = max(0, min(100, new_value))
            
            # Calculate total resource usage for logging
            energy_kwh = 0
            water_used_liters = 0
            
            if self.current_action.required_device:
                device_info = self.house.get_device_by_name(self.current_action.required_device)
                if device_info:
                    device_type = device_info["type"]
                    device = device_info["device"]
                    key = f"{self.current_room}_{self.current_action.required_device}"
                    flow_type = self.house.device_states[key].get("flow_type")
                    
                    if device_type == "electricity":
                        power_watts = device.get("power_watts", 0)
                        energy_kwh = (power_watts * (self.current_action.duration / 3600)) / 1000
                    
                    elif device_type == "water":
                        if flow_type == "per_use":
                            water_used_liters = device.get("flow_rate_liters_per_use", 0)
                            self.house.total_water_used_liters += water_used_liters
                        elif flow_type == "per_minute":
                            flow_rate_lpm = device.get("flow_rate_liters_per_minute", 0)
                            water_used_liters = flow_rate_lpm * (self.current_action.duration / 60)
                            if device["device"] in ["shower", "sink"] and self.house.water_heating["method"] == "electricity":
                                heating_energy = water_used_liters * ENERGY_PER_LITER_HOT_WATER
                                energy_kwh += heating_energy
                    
                    # Release device
                    self.house.device_states[key]["in_use"] = False
                    self.house.device_states[key]["used_by"] = None
            
            # Log action with total resource usage
            add_action_to_json(
                NPCtime=self.time,
                action=self.current_action.name,
                device_used=self.current_action.required_device or "NAN",
                energy_used=energy_kwh,
                water_used=water_used_liters,
                duration=self.current_action.duration,
                npc_name=self.name,
                FILEPATH="results/user_data.json",
                print_message=False
            )
            
            # Reset state and check sleep time
            self.current_action = None
            self.action_end_time = None
            self.state = "Idle"
            self.activity = f"{self.name} finished the action in {self.current_room}."
            if self.is_sleep_time(self.time):
                self.state = "Sleeping"
                self.activity = f"{self.name} went to sleep after finishing the action."
            else:
                next_action = self.decide_next_action()
                if next_action and not isinstance(next_action, tuple):
                    self.perform_action(next_action)

    def decide_and_act(self):
        self.update_needs()
        
        # Check if out of home first to avoid redundant calls
        out_of_home_status = self.is_out_of_home()
        if out_of_home_status[0]:
            self.activity = f"{self.name} is out of home because of {out_of_home_status[1]}."
            add_action_to_json(
                NPCtime=self.time,
                action=out_of_home_status[1],
                device_used="NAN",
                energy_used=0,
                water_used=0,
                duration=0,
                npc_name=self.name,
                FILEPATH="results/user_data.json",
                print_message=False
            )
            return
        
        if self.state == "Performing Action":
            if self.time >= self.action_end_time:
                self.finish_action()
            else:
                self.activity = f"{self.name} is still performing {self.current_action.name}."
        elif self.state == "Sleeping":
            if not self.is_sleep_time(self.time):
                self.state = "Idle"
                self.activity = f"{self.name} woke up."
                next_action = self.decide_next_action()
                if next_action and not isinstance(next_action, tuple):
                    self.perform_action(next_action)
            else:
                self.activity = f"{self.name} is sleeping."
                add_action_to_json(
                    NPCtime=self.time,
                    action="sleep",
                    device_used="NAN",
                    energy_used=0,
                    water_used=0,
                    duration=300,  # 5 minutes, matching simulation interval
                    npc_name=self.name,
                    FILEPATH="results/user_data.json",
                    print_message=False
                )
        elif self.state == "Idle":
            if self.is_sleep_time(self.time):
                self.state = "Sleeping"
                self.activity = f"{self.name} went to sleep."
            else:
                next_action = self.decide_next_action()
                if next_action:
                    if isinstance(next_action, tuple) and next_action[0] == "out_of_home":
                        # This case should not happen anymore since we check at the beginning
                        self.activity = f"{self.name} is out of home because of {next_action[1]}."
                        add_action_to_json(
                            NPCtime=self.time,
                            action=next_action[1],
                            device_used="NAN",
                            energy_used=0,
                            water_used=0,
                            duration=0,
                            npc_name=self.name,
                            FILEPATH="results/user_data.json",
                            print_message=False
                        )
                    else:
                        self.perform_action(next_action)
                else:
                    self.activity = f"{self.name} is idle."
                
    

    def display_stats(self):
        hunger_status = "Very Hungry" if self.needs["hunger"] > 70 else "Hungry" if self.needs["hunger"] > 50 else "Not Hungry"
        energy_status = "Exhausted" if self.needs["energy"] < 20 else "Tired" if self.needs["energy"] < 50 else "Energetic"
        hygiene_status = "Dirty" if self.needs["hygiene"] < 30 else "Clean"
        fun_status = "Bored" if self.needs["fun"] < 30 else "Having Fun"
        return (f"\033[94mStats: Hunger={self.needs['hunger']} ({hunger_status}) | "
                f"Energy={self.needs['energy']} ({energy_status}) | "
                f"Hygiene={self.needs['hygiene']} ({hygiene_status}) | "
                f"Fun={self.needs['fun']} ({fun_status})\033[0m")

def run_simulation(config_data, output_path="results/user_data.json", update_interval=300, actions_in_minutes_flag=True, start_date=None, end_date=None):
    global update_each_seconds, actions_in_minutes
    update_each_seconds = update_interval
    actions_in_minutes = actions_in_minutes_flag
    
    type_of_simulation = config_data['basic_parameters']['type_of_simulation']["type"]
    config_start_date = config_data['basic_parameters']['type_of_simulation'].get("start_date")
    config_end_date = config_data['basic_parameters']['type_of_simulation'].get("end_date")
    
    sim_start_date = start_date if start_date else config_start_date
    sim_end_date = end_date if end_date else config_end_date

    temp, humidi = getTempHomemade.get_temp_hum()
    now = datetime.now()
    house = House(config_data, temperature=temp, humidity=humidi, month=now.month, year=now.year)

    create_json_reg(house_name=config_data["basic_parameters"]["name"], FILEPATH=output_path, typeOfSimulation=type_of_simulation,
                    start_date=sim_start_date if type_of_simulation == "fast_forward" else None,
                    end_date=sim_end_date if type_of_simulation == "fast_forward" else None)

    npcs = [NPC(name=npc["name"], out_of_home_periods=npc.get("out_of_home_periods", []), house=house, age_group=npc["age_group"], sleep_start=npc["sleep_start"], sleep_end=npc["sleep_end"],  simulation_type="fast_forward") 
            for npc in config_data['basic_parameters']['npc']]

    print("-" * 50)
    print(f"Simulation started for {config_data['basic_parameters']['name']}. Press Ctrl+C to stop.")
    print(f"Type of simulation: {type_of_simulation}")
    print(f"Initial temperature: {house.temperature}°C, Humidity: {house.humidity}%")
    print(f"Updates every {update_interval} seconds.")
    print(f"Actions in minutes: {actions_in_minutes_flag}")
    print("-" * 50)
    for npc in npcs:
        print(f"\033[94mName of NPC: {npc.name}\033[0m")
        print(f"\033[94mAge group: {npc.age_group}\033[0m")
    print("-" * 50)

    try:
        simulation_time = datetime.strptime(sim_start_date + " 00:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=1)))
        end_time = datetime.strptime(sim_end_date + " 00:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=1)))
        print(f"Simulating from {simulation_time.isoformat()} to {end_time.isoformat()}")

        electricity_consumption = {}
        water_consumption = {}
        device_usage = {}

        for npc in npcs:
            npc.time = simulation_time
            npc.last_toilet_time = simulation_time

        while simulation_time < end_time:
            interval_start = simulation_time
            house.time = interval_start  # Update house time
            house.reset_daily_usage(interval_start)  # Reset daily usage if new day
            timestamp = simulation_time.isoformat()
            
            interval_electricity = 0
            interval_water = 0
            interval_devices = {"electricity": {}, "water": {}}

            # Baseline electricity consumption
            interval_electricity += BASELINE_ELECTRICITY_KWH_PER_5MIN
            interval_devices["electricity"]["always_on"] = interval_devices["electricity"].get("always_on", 0) + BASELINE_ELECTRICITY_KWH_PER_5MIN

            for npc in npcs:
                npc.time = interval_start
                npc.decide_and_act()
                if npc.state == "Performing Action":
                    start_time = max(npc.action_start_time, interval_start)
                    action_end_in_interval = min(simulation_time + timedelta(minutes=5), npc.action_end_time)
                    active_time_seconds = (action_end_in_interval - start_time).total_seconds() if action_end_in_interval > start_time else 0

                    if active_time_seconds > 0 and npc.current_action.required_device:
                        device_info = house.get_device_by_name(npc.current_action.required_device)
                        if device_info:
                            device_type = device_info["type"]
                            device = device_info["device"]
                            device_key = f"{npc.current_room}_{npc.current_action.required_device}"

                            if device_type == "electricity":
                                power_watts = device.get("power_watts", 0)
                                energy_kwh = (power_watts * (active_time_seconds / 3600)) / 1000
                                interval_electricity += energy_kwh
                                interval_devices["electricity"][device_key] = interval_devices["electricity"].get(device_key, 0) + energy_kwh
                                house.total_electricity_used_kwh += energy_kwh

                            elif device_type == "water" and house.device_states[device_key].get("flow_type") == "per_minute":
                                flow_rate_lpm = device.get("flow_rate_liters_per_minute", 0)
                                water_used_liters = flow_rate_lpm * (active_time_seconds / 60)
                                interval_water += water_used_liters
                                interval_devices["water"][device_key] = interval_devices["water"].get(device_key, 0) + water_used_liters
                                house.total_water_used_liters += water_used_liters
                                if device["device"] in ["shower", "sink"] and house.water_heating["method"] == "electricity":
                                    heating_energy = water_used_liters * ENERGY_PER_LITER_HOT_WATER
                                    interval_electricity += heating_energy
                                    house.total_electricity_used_kwh += heating_energy

            electricity_consumption[timestamp] = interval_electricity
            water_consumption[timestamp] = interval_water
            device_usage[timestamp] = interval_devices
            
            simulation_time += timedelta(minutes=5)

        print("-" * 50)
        print("Simulation completed.")
        print(f"Total electricity used: {house.total_electricity_used_kwh:.2f} kWh")
        print(f"Total water used: {house.total_water_used_liters:.2f} liters")

        return electricity_consumption, water_consumption, device_usage

    except KeyboardInterrupt:
        print("Simulation stopped by user.")
        print(f"Total electricity used: {house.total_electricity_used_kwh:.2f} kWh")
        print(f"Total water used: {house.total_water_used_liters:.2f} liters")

def run_simulation_realtime(config_data, output_path="results/user_data.json"):
    temp, humidi = getTempHomemade.get_temp_hum()
    now = datetime.now()
    house = House(config_data, temperature=temp, humidity=humidi, month=now.month, year=now.year)

    create_json_reg(house_name=config_data["basic_parameters"]["name"], 
                    FILEPATH=output_path, 
                    typeOfSimulation="realtime", 
                    start_date=None, 
                    end_date=None)
    
    npcs = [NPC(name=npc["name"], 
                out_of_home_periods=npc.get("out_of_home_periods", []), 
                house=house, 
                age_group=npc["age_group"], 
                simulation_type="realtime") 
            for npc in config_data['basic_parameters']['npc']]

    house.total_electricity_used_kwh = BASELINE_ELECTRICITY_KWH_PER_5MIN
    house.total_water_used_liters = 0.0
    device_usage = {"electricity": {"always_on": BASELINE_ELECTRICITY_KWH_PER_5MIN}, "water": {}}

    for npc in npcs:
        npc.time = datetime.now(timezone.utc)
        npc.decide_and_act()
        print(f"[{npc.time.isoformat()}] {npc.name}: {npc.activity}")
        print(npc.display_stats())

        if npc.state == "Performing Action" and npc.current_action and npc.current_action.required_device:
            device_info = house.get_device_by_name(npc.current_action.required_device)
            if device_info:
                device_type = device_info["type"]
                device_key = f"{npc.current_room}_{npc.current_action.required_device}"
                flow_type = house.device_states[device_key].get("flow_type")

                if device_type == "electricity":
                    power_watts = device_info["device"].get("power_watts", 0)
                    energy_kwh = (power_watts * (npc.current_action.duration / 3600)) / 1000
                    device_usage["electricity"][device_key] = device_usage["electricity"].get(device_key, 0) + energy_kwh
                    house.total_electricity_used_kwh += energy_kwh

                elif device_type == "water":
                    if flow_type == "per_minute":
                        flow_rate_lpm = device_info["device"].get("flow_rate_liters_per_minute", 0)
                        water_used_liters = flow_rate_lpm * (npc.current_action.duration / 60)
                        device_usage["water"][device_key] = device_usage["water"].get(device_key, 0) + water_used_liters
                        house.total_water_used_liters += water_used_liters
                    elif flow_type == "per_use":
                        water_used_liters = device_info["device"].get("flow_rate_liters_per_use", 0)
                        house.total_water_used_liters += water_used_liters

    print(f"Total electricity used: {house.total_electricity_used_kwh:.2f} kWh")
    print(f"Total water used: {house.total_water_used_liters:.2f} liters")
    return house.total_electricity_used_kwh, house.total_water_used_liters, device_usage

if __name__ == "__main__":
    pass