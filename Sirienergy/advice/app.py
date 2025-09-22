import os
import logging

from flask import Flask, request, jsonify, render_template

import redis
import json
from datetime import datetime, timedelta
import hashlib
from typing import List, Dict, Union, Optional
import csv
import requests
import xmltodict

app = Flask(__name__, template_folder='templates')

ENTSO_E_API_KEY = os.getenv('ENTSO_E_API_KEY')

def hash_password(password: str) -> str:
    """Hashes a password using SHA-256.

    Args:
        password: The password to hash.

    Returns:
        The hashed password as a hexadecimal string.
    """
    return hashlib.sha256(password.encode()).hexdigest()

class RedisModel:
    """A model for managing user data in Redis."""

    def __init__(self):
        """Initializes the RedisModel with a Redis connection."""
        self.client = redis.StrictRedis(
            host=os.getenv("REDIS_HOST"),
            port=os.getenv("REDIS_PORT"),
            decode_responses=True,
        )

    def create_user(self,
                    user_name: str,
                    user_email: str,
                    user_password: str) -> dict:
        """Creates a new user in Redis.

        Args:
            user_name: The user's name.
            user_email: The user's email (used as a unique key).
            user_password: The user's password (hashed before storing).

        Returns:
            A dictionary confirming the user creation.
        """
        key = f"user:{user_email}"
        user_document = {
            "user_name": user_name,
            "user_email": user_email,
            "user_password": hash_password(user_password),
            "user_consumption": {},
            "user_production": {},
        }
        self.client.execute_command("JSON.SET", key, ".",
                                    json.dumps(user_document))
        return {
            "message": f"""User '{user_name}' with email 
            {user_email} has been created."""
        }

    def _initialize_json_path(self, key: str, path: str) -> None:
        """Ensures that a JSON path exists in Redis, initializing 
        it if necessary.

        Args:
            key: The Redis key.
            path: The JSON path to initialize.
        """
        try:
            existing_data = self.client.execute_command("JSON.GET", key, path)
            if existing_data is None or existing_data == "[]":
                self.client.execute_command("JSON.SET", key, path, "{}")
        except redis.RedisError as error:
            raise ValueError(f"Failed to initialize path {path}: {error}")

    def add_data(
        self,
        user_email: str,
        date: str,
        hour: str,
        value: float,
        data_type: str,
    ) -> dict:
        """Adds a consumption or production record for a user.

        Args:
            user_email: The user's email (used as a unique key).
            date: The date of the record.
            hour: The hour of the record.
            value: The value to be added.
            data_type: Either "user_consumption" or "user_production".

        Returns:
            A dictionary confirming the record addition.
        """
        if data_type not in {"user_consumption", "user_production"}:
            raise ValueError(
                """Invalid data type. Must be 'user_consumption'
                or 'user_production'."""
            )

        key = f"user:{user_email}"
        base_path = f"$.{data_type}"
        self._initialize_json_path(key, base_path)
        date_path = f"{base_path}.{date}"
        self._initialize_json_path(key, date_path)

        try:
            hour_path = f"{date_path}.{hour}"
            increment = self.client.execute_command(
                "JSON.NUMINCRBY", key, hour_path, value
            )
            if increment is None or increment == "[]":
                self.client.execute_command("JSON.SET", key, hour_path, value)
        except redis.RedisError as error:
            raise ValueError(f"Failed to update {data_type} value: {error}")

        return {
            "message": f"""{data_type.replace('_', ' ').capitalize()} 
            of {value} added for {date} at {hour}."""
        }

    def get_user(self, user_email: str) -> dict:
        """Retrieves user data from Redis.

        Args:
            user_email: The user's email (used as a unique key).

        Returns:
            A dictionary with the user data or None if not found.
        """
        key = f"user:{user_email}"
        json_data = self.client.execute_command("JSON.GET", key)
        return json.loads(json_data) if json_data else None

    def get_data_day(self, user_email: str, date: str, data_type: str) -> dict:
        """Retrieves consumption or production records for a user on a date.

        Args:
            user_email: The user's email (used as a unique key).
            date: The date of the record.
            data_type: Either "user_consumption" or "user_production".

        Returns:
            A dictionary with the data for the specified date or an empty
            structure if no data exists.
        """
        if data_type not in {"user_consumption", "user_production"}:
            raise ValueError(
                """Invalid data type. Must be 'user_consumption'
                  or 'user_production'."""
            )

        key = f"user:{user_email}"
        date_path = f"$.{data_type}.{date}"
        try:
            existing_data = self.client.execute_command("JSON.GET", key,
                                                        date_path)
            data_json = json.loads(existing_data) if existing_data else {}
            return data_json
        except redis.RedisError as error:
            raise ValueError(f"""Failed to retrieve {data_type} for {date}:
                              {error}""")

    def add_consumption(
        self, user_email: str, date: str, hour: str, value: float
    ) -> dict:
        """Adds a consumption record for a user."""
        return self.add_data(user_email, date, hour, value, "user_consumption")

    def add_production(
        self, user_email: str, date: str, hour: str, value: float
    ) -> dict:
        """Adds a production record for a user."""
        return self.add_data(user_email, date, hour, value, "user_production")

    def get_production_day(self, user_email: str, date: str) -> dict:
        """Retrieves production records for a user on a date."""
        return self.get_data_day(user_email, date, "user_production")

    def get_consumption_day(self, user_email: str, date: str) -> dict:
        """Retrieves consumption records for a user on a date."""
        return self.get_data_day(user_email, date, "user_consumption")

redis_model = RedisModel()

def complete_and_order_hours(data, default_value=0):
    """Completes and orders hourly data with default values for missing hours.
    
    Args:
        data (dict): Dictionary of hour-value pairs to complete.
        default_value (int, optional): Default value for missing hours. 
          Defaults to 0.
    
    Returns:
        dict: Ordered dictionary with all 24 hours in "HH:00" format.
    """
    all_hours = [datetime(2000, 1, 1, h).strftime("%H:00") for h in range(24)]
    completed_data = {hour: data.get(hour, default_value) for hour in all_hours}
    return dict(sorted(completed_data.items()))

def get_surplus_aux(user_email):
    """Calculates hourly energy surplus for a user.
    
    Args:
        user_email (str): Email of the user to calculate surplus for.
    
    Returns:
        dict: Dictionary of hourly surplus values (production - consumption).
    """
    current_date = datetime.now().strftime("%Y-%m-%d")
    consumption = redis_model.get_consumption_day(user_email, current_date)[0]
    production = redis_model.get_production_day(user_email, current_date)[0]

    ordered_consumption = complete_and_order_hours(consumption)
    ordered_production = complete_and_order_hours(production)

    return {
        hour: ordered_production[hour] - ordered_consumption[hour]
        for hour in ordered_consumption
    }

def hour_value_to_list(surplus):
    surplus_list = []
    for value in surplus.values():
        surplus_list.append(value)
    return surplus_list

def load_entsoe_country_keys() -> Dict[str, str]:
    """Loads country keys from a CSV file for ENTSO-E API queries.

    Returns:
        Dict[str, str]: A dictionary mapping country names to their respective 
            ENTSO-E keys.
    """
    base_dir = os.path.dirname(__file__)
    file_path = os.path.abspath(
        os.path.join(base_dir, "common_files/entsoe/entsoe_country_keys.csv")
    )

    entsoe_country_keys: Dict[str, str] = {}
    with open(file_path, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            entsoe_country_keys[row["country"]] = row["key"]
    return entsoe_country_keys


def get_day_ahead_prices(
    country_name: str,
) -> Optional[List[Dict[str, Union[str, float]]]]:
    """Retrieves day-ahead electricity prices for a specified country.

    Args:
        country_name: The name of the country for which to retrieve prices.

    Returns:
        A list of price points for the day-ahead market, or None if the request
        fails.
    """

    endpoint = "https://web-api.tp.entsoe.eu/api"
    current_datetime = datetime.now()
    yesterday_datetime = current_datetime - timedelta(days=1)
    current_formatted = current_datetime.strftime("%Y%m%d") + "2200"
    yesterday_formatted = yesterday_datetime.strftime("%Y%m%d") + "2200"

    entsoe_country_keys = load_entsoe_country_keys()
    if country_name not in entsoe_country_keys:
        logging.error("Key for country %s not found", country_name)
        return None

    country_key = entsoe_country_keys[country_name]
    params = {
        "securityToken": ENTSO_E_API_KEY,
        "documentType": "A44",
        "in_Domain": country_key,
        "out_Domain": country_key,
        "periodStart": yesterday_formatted,
        "periodEnd": current_formatted,
    }

    response = requests.get(endpoint, params=params, timeout=30)
    data_xml = response.text
    data_dict = xmltodict.parse(data_xml)
    data_json = json.loads(json.dumps(data_dict))

    if response.status_code == 200:

        time_series_list = data_json["Publication_MarketDocument"].get(
            "TimeSeries", [])
        points = []

        if isinstance(time_series_list, list):
            for time_series in time_series_list:
                if time_series["Period"]["resolution"] == "PT60M":
                    points = time_series["Period"]["Point"]
                    break
        elif time_series_list["Period"]["resolution"] == "PT60M":
            points = time_series_list["Period"]["Point"]
        else:
            logging.info("Incorrect format: %s", time_series_list)

        return points
    else:
        logging.error(
            "Failed to retrieve data. Status code: %s, Response: %s",
            response.status_code,
            data_json,
        )
        return None

def entsoe_to_array(data: List[Dict[str, str]]) -> List[float]:
    """Converts ENTSO-E time series data into a structured array of prices.

    Args:
        data: A list of dictionaries containing ENTSO-E time series data.

    Returns:
        A structured array of prices, with missing values filled using the 
        previous value.
    """
    max_position = max(int(item["position"]) for item in data)
    result: List[Optional[float]] = [None] * max_position
    previous_value: Optional[float] = None

    for item in data:
        position = int(item["position"]) - 1
        price = float(item["price.amount"])

        if previous_value is not None and position > 0:
            for i in range(position):
                if result[i] is None:
                    result[i] = previous_value

        result[position] = price
        previous_value = price

    for i in range(len(result)):
        if result[i] is None:
            result[i] = previous_value

    return result 

def get_price_array(
    country_name: str, price_type: str, fixed_value: float = 0.0
) -> Optional[List[float]]:
    """Generates a price array based on the specified type (fixed or market 
    prices).

    Args:
        country_name: The name of the country for which to retrieve prices.
        price_type: The type of price array to generate ("FIXED" or "MARKET").
        fixed_value: The fixed price value if type is "FIXED". Defaults to 0.0.

    Returns:
        A price array of length 24, or None if an error occurs.
    """
    if price_type == "FIXED":
        return [fixed_value] * 24
    elif price_type == "MARKET":
        prices_dict = get_day_ahead_prices(country_name)
        if prices_dict is None:
            return None
        return [round(value / 1000, 5) for value in
                entsoe_to_array(prices_dict)]
    else:
        logging.error("Invalid price type: %s", price_type)
        return None

def sell_by_hours(
    price_array: List[float], gen_array: List[float]
) -> Optional[List[float]]:
    """Calculates revenue from selling electricity.

    Args:
        price_array: A list of prices per hour.
        gen_array: A list of generation values per hour.

    Returns:
        A list of revenue values per hour, or None if arrays have different 
        lengths.
    """
    if len(price_array) != len(gen_array):
        logging.error("Arrays must have the same length. Got %s vs %s",
                      len(price_array), len(gen_array))
        return None

    return [p * g for p, g in zip(price_array, gen_array)]


def get_money_advice(
    user_email: str, country: str, fee: str, fixed_value: int,
    has_battery: bool, battery_capacity_kwh: int
) -> str:
    try:
        existing_data = redis_model.get_user(user_email)

        if existing_data is None:
            return "error", "User is not registered"
        else:
            surplus = get_surplus_aux(user_email)
            surplus = hour_value_to_list(surplus)

    except ValueError as e:
        return "error", e

    # Get price array
    price_list = get_price_array(country, fee, fixed_value)

    rent = sell_by_hours(price_list, surplus)

    profit = sum(rent)

    if profit > 0:
        return (
            "Sell to the grid",
            """You will achieve greater profitability if you sell the energy
            "produced during the day instead of storing it in the batteries."""
        )
    else:
        if has_battery:
            if (battery_capacity_kwh - sum(surplus)) > 0:
                return (
                    "Charge batteries",
                    """You will not achieve greater profitability if you sell 
                    the energy produced during the day so better store it 
                    for later"""
                )
            else:
                return (
                    "Charge batteries",
                    f"""You have a surplus of energy, you can fully charge your 
                    batteries and consume the
                    {round(sum(surplus) - battery_capacity_kwh, 2)}
                    kWh you will have left."""
                )
        else:
            return (
                "Consume more",
                """You have a surplus of energy, consume more in daytime to 
                avoid wasting it. If you have chores to do, do them now."""
            )


def get_co2_advice(
    user_email: str,
    has_battery: bool, battery_capacity_kwh: int
) -> str:
    try:
        existing_data = redis_model.get_user(user_email)

        if existing_data is None:
            return "error", "User is not registered"
        else:
            surplus = get_surplus_aux(user_email)
            surplus = hour_value_to_list(surplus)
    except ValueError as e:
        return "error", e

    balance = sum(surplus)
    if balance > 0:
        if has_battery:
            if (battery_capacity_kwh - sum(surplus)) > 0:
                return (
                    "Charge batteries",
                    """The last hours are when the dirtiest energy is used.
                    Use your batteries to generate less CO2."""
                )
            else:
                return (
                    "Charge batteries",
                    f"""You have a surplus of energy, you can fully charge your
                    batteries and consume the
                    {round(sum(surplus) - battery_capacity_kwh, 2)}
                    kWh you will have left."""
                )
        else:
            return (
                "Daytime consumption",
                """You will generate less CO2 if you consume more energy 
                during the day."""
            )
    else:
        return (
            "Limit use",
            """Your production will not cover your consumption, reduce your
            consumption to not get energy from the grid."""
        )


@app.route("/advice", methods=["POST"])
def get_advice():
    # Get necessary data
    try:
        data = request.json
        user_email = data["email"]
        country = data["country"]
        fee = data["fee"]
        fixed_value = data["fixed_price"]
        has_battery = data["has_battery"]
        battery_capacity_kwh = float(data["battery_capacity"])

    except KeyError as e:
        return jsonify({"error": f"Missing key: {str(e)}"}), 400

    money_advice, money_message = get_money_advice(
        user_email=user_email, country=country, fee=fee,
        fixed_value=fixed_value, has_battery=has_battery,
        battery_capacity_kwh=battery_capacity_kwh
    )
    co2_advice, co2_message = get_co2_advice(
        user_email=user_email, has_battery=has_battery,
        battery_capacity_kwh=battery_capacity_kwh
    )

    if money_advice == "error":
        html_content = render_template("error_card.html",
                                       error_message=money_message)
    elif co2_advice == "error":
        html_content = render_template("error_card.html",
                                       error_message=co2_message)
    else:
        html_content = render_template(
            "advice_flip_card.html", money_advice=money_advice,
            co2_advice=co2_advice, money_message=money_message,
            co2_message=co2_message
        )

    return html_content


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5009)