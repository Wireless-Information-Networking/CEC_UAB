import os
import logging

from flask import Flask, request, jsonify

from datetime import datetime, timedelta
from typing import List, Dict, Union, Optional
import requests
import xmltodict
import csv
import json
import pandas as pd
import pvlib

app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG)

ENTSO_E_API_KEY = os.getenv('ENTSO_E_API_KEY')

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
    
    logging.error(f"data json: {data_json}")

    if response.status_code == 200:

        time_series_list = data_json["Publication_MarketDocument"].get(
            "TimeSeries", [])
        points = []

        if isinstance(time_series_list, list):
            for time_series in time_series_list:
                if time_series["Period"]["resolution"] == "PT15M":
                    points = time_series["Period"]["Point"]
                    break
        elif time_series_list["Period"]["resolution"] == "PT15M":
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
        A price array of length 96, or None if an error occurs.
    """
    if price_type == "FIXED":
        return [fixed_value] * 96
    elif price_type == "MARKET":
        prices_dict = get_day_ahead_prices(country_name)
        if prices_dict is None:
            return None
        return [round(value / 1000, 5) for value in
                entsoe_to_array(prices_dict)]
    else:
        logging.error("Invalid price type: %s", price_type)
        return None

def get_PV_gen(
    latitude: float,
    longitude: float,
    altitude: float,
    surface: float,
    efficiency: float,
    tz: str,
) -> list[float]:
    """Calculates photovoltaic (PV) power generation for a location and system.

    Args:
        latitude: Latitude of the location in degrees.
        longitude: Longitude of the location in degrees.
        altitude: Altitude of the location in meters.
        surface: Surface area of PV panels in square meters.
        efficiency: PV panel efficiency percentage (0-100).
        tz: Timezone of the location (e.g., 'Europe/Berlin').

    Returns:
        List of hourly PV power generation values in watts for September 21,
        2024.
    """
    location = pvlib.location.Location(
        latitude=latitude,
        longitude=longitude,
        tz=tz,
        altitude=altitude
    )

    times = pd.date_range(
        start=datetime(2024, 9, 21, 0),
        end=datetime(2024, 9, 21, 23, 59),
        freq='15min',
        tz=tz
    )

    clearsky = location.get_clearsky(times, model='ineichen')
    ghi = clearsky['ghi'].tolist()

    conversion_factor = (efficiency / 100) * surface
    return [irradiance * conversion_factor for irradiance in ghi]

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

@app.route("/selling_prices", methods=["POST"])
def selling_prices():
    """Calculates potential revenue from PV system energy sales.

    Args:
        JSON payload containing:
            latitude (float): System location latitude
            longitude (float): System location longitude
            altitude (float): System altitude in meters
            timezone (str): Timezone identifier
            surface (float): Panel surface area in m²
            efficiency (float): Panel efficiency percentage
            country (str): Country code for pricing
            fee (str): Pricing model type
            fixed_price (float): Fixed price value if applicable

    Returns:
        JSON response with hourly revenue values or error message:
        - 400 for missing/invalid parameters
        - 500 for calculation errors
        - 200 with revenue data on success
    """
    data = request.json
    if ("latitude" not in data or
        "longitude" not in data or
        "altitude" not in data or
        "timezone" not in data):
        return jsonify({
            "error": """Invalid input. Please provide
                    latitude, longitude, altitude, and timezone."""
        }), 400

    try:
        latitude = float(data["latitude"])
        longitude = float(data["longitude"])
        altitude = float(data["altitude"])
        surface = float(data["surface"])
        efficiency = float(data["efficiency"])
        tz = data["timezone"]
        country = data["country"]
        fee = data["fee"]
        fixed_value = float(data["fixed_price"])

        price_array = get_price_array(country, fee, fixed_value)
        power_array = get_PV_gen(latitude, longitude, altitude, surface,
                                 efficiency, tz)

        logging.error(price_array, power_array)

        power_array = [round(value / 1000, 5) for value in power_array]

        euros_by_hours = sell_by_hours(price_array, power_array)

        return jsonify({"sell": euros_by_hours}), 200

    except ValueError as error:
        logging.error(f"ValueError: {error}")
        return jsonify({"error": "Something went wrong. Try again later."}), 500
    except Exception as error:
        logging.error(f"Exception: {error}")
        return jsonify({"error": str(error)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5006)
