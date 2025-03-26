"""ENTSO-E API interaction module for energy data retrieval."""

import csv
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
from app.aux.aux_modules.logging_helper import log_message
import requests
import xmltodict

from app.config import Config

MODULE_TYPE = "model"
MODULE_NAME = "ENTSOE"
MODULE_DEBUG = 1

def load_entsoe_country_keys() -> Dict[str, str]:
    """Loads country keys from a CSV file for ENTSO-E API queries.

    Returns:
        Dict[str, str]: A dictionary mapping country names to their respective ENTSO-E keys.
    """
    base_dir = os.path.dirname(__file__)
    file_path = os.path.abspath(
        os.path.join(base_dir, "../aux/entsoe_tables/entsoe_country_keys.csv")
    )

    entsoe_country_keys: Dict[str, str] = {}
    with open(file_path, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            entsoe_country_keys[row["country"]] = row["key"]
    return entsoe_country_keys


def load_entsoe_gentype_names() -> Dict[str, str]:
    """Loads generation type names from a CSV file for ENTSO-E API queries.

    Returns:
        Dict[str, str]: A dictionary mapping ENTSO-E generation type keys to their names.
    """
    base_dir = os.path.dirname(__file__)
    file_path = os.path.abspath(
        os.path.join(base_dir, "../aux/entsoe_tables/entsoe_gentype_names.csv")
    )

    entsoe_gentype_names: Dict[str, str] = {}
    with open(file_path, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            entsoe_gentype_names[row["key"]] = row["name"]
    return entsoe_gentype_names


def get_day_ahead_prices(
    country_name: str,
) -> Optional[List[Dict[str, Union[str, float]]]]:
    """Retrieves day-ahead electricity prices for a specified country.

    Args:
        country_name: The name of the country for which to retrieve prices.

    Returns:
        A list of price points for the day-ahead market, or None if the request fails.
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
        "securityToken": Config.ENTSO_E_API_KEY,
        "documentType": "A44",
        "in_Domain": country_key,
        "out_Domain": country_key,
        "periodStart": yesterday_formatted,
        "periodEnd": current_formatted,
    }
    if Config.DEBUG and MODULE_DEBUG and 1:
        log_message("debug", MODULE_TYPE, MODULE_NAME, "get_day_ahead_prices", f"Entsoe request: {params}")

    response = requests.get(endpoint, params=params, timeout=30)
    data_xml = response.text
    data_dict = xmltodict.parse(data_xml)
    data_json = json.loads(json.dumps(data_dict))
    if Config.DEBUG and MODULE_DEBUG and 1:
        log_message("debug", MODULE_TYPE, MODULE_NAME, "get_day_ahead_prices", f"Entsoe response json: {data_json}")

    if response.status_code == 200:
        time_series_list = data_json["Publication_MarketDocument"].get("TimeSeries", [])
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
        A structured array of prices, with missing values filled using the previous value.
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

    return result  # type: ignore (Safe since previous_value will be set)


def get_price_array(
    country_name: str, price_type: str, fixed_value: float = 0.0
) -> Optional[List[float]]:
    """Generates a price array based on the specified type (fixed or market prices).

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
        return [round(value / 1000, 5) for value in entsoe_to_array(prices_dict)]
    else:
        logging.error("Invalid price type: %s", price_type)
        return None


def load_co2_by_type(file_path: str = "entsoe_tables/CO2.csv") -> Dict[str, float]:
    """Loads CO2 emission factors by generation type from a CSV file.

    Args:
        file_path: The path to the CSV file. Defaults to "entsoe_tables/CO2.csv".

    Returns:
        A dictionary mapping energy types to their CO2 emission factors (gCO2eq/Wh).
    """
    base_dir = os.path.dirname(__file__)
    file_path = os.path.abspath(
        os.path.join(base_dir, "../aux/entsoe_tables/CO2.csv")
    )

    co2_by_gentype = {}
    with open(file_path, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            co2_by_gentype[row["Energy Type"]] = float(row["gCO2eq/Wh"])
    return co2_by_gentype


def get_actual_generation_by_type(country_name: str) -> Optional[Dict[str, int]]:
    """Retrieves actual electricity generation data by type for a given country.

    Args:
        country_name: The name of the country for which to retrieve generation data.

    Returns:
        A dictionary mapping generation types to their values, or None on error.
    """
    endpoint = "https://web-api.tp.entsoe.eu/api"
    current_datetime = datetime.utcnow()
    yesterday_datetime = current_datetime - timedelta(days=1)
    current_formatted = current_datetime.strftime("%Y%m%d") + "2200"
    yesterday_formatted = yesterday_datetime.strftime("%Y%m%d") + "2200"

    entsoe_country_keys = load_entsoe_country_keys()
    if country_name not in entsoe_country_keys:
        logging.error("Key for country %s not found", country_name)
        return None

    country_key = entsoe_country_keys[country_name]
    params = {
        "securityToken": Config.ENTSO_E_API_KEY,
        "documentType": "A75",
        "processType": "A16",
        "in_Domain": country_key,
        "periodStart": yesterday_formatted,
        "periodEnd": current_formatted,
    }

    response = requests.get(endpoint, params=params, timeout=30)
    if response.status_code != 200:
        logging.error(
            "Failed to retrieve data. Status code: %s, Response: %s",
            response.status_code,
            response.text,
        )
        return None

    try:
        data_json = json.loads(json.dumps(xmltodict.parse(response.text)))
    except Exception as e:
        logging.error("Failed to parse response XML: %s", str(e))
        return None

    gens = {}
    time_series_list = data_json.get("GL_MarketDocument", {}).get("TimeSeries", [])
    last_up_time = yesterday_datetime
    date_format = "%Y-%m-%dT%H:%MZ"

    if time_series_list:
        for time_series in time_series_list:
            update_time_str = time_series["Period"]["timeInterval"]["end"]
            update_time = datetime.strptime(update_time_str, date_format)
            if update_time > last_up_time:
                last_up_time = update_time

        last_up_time_str = last_up_time.strftime(date_format)
        entsoe_gentype_names = load_entsoe_gentype_names()

        for time_series in time_series_list:
            if last_up_time_str == time_series["Period"]["timeInterval"]["end"]:
                gentype = entsoe_gentype_names[time_series["MktPSRType"]["psrType"]]
                if "inBiddingZone_Domain.mRID" in time_series:
                    gens[gentype] = int(time_series["Period"]["Point"][-1]["quantity"])
                else:
                    gens[gentype] = gens.get(gentype, 0)

        gens = {key: value for key, value in gens.items() if value != 0}
    else:
        logging.info("No valid time series data found.")

    return gens


def get_co2_from_dict(
    power_dict: Dict[str, int], co2_dict: Dict[str, float]
) -> float:
    """Calculates total CO2 emissions based on power generation and emission factors.

    Args:
        power_dict: A dictionary mapping generation types to power values.
        co2_dict: A dictionary mapping generation types to CO2 emission factors.

    Returns:
        The total CO2 emissions in gCO2eq.
    """
    return sum(value * co2_dict.get(key, 0.0) for key, value in power_dict.items())


def sell_by_hours(
    price_array: List[float], gen_array: List[float]
) -> Optional[List[float]]:
    """Calculates revenue from selling electricity.

    Args:
        price_array: A list of prices per hour.
        gen_array: A list of generation values per hour.

    Returns:
        A list of revenue values per hour, or None if arrays have different lengths.
    """
    if len(price_array) != len(gen_array):
        logging.error("Arrays must have the same length. Got %s vs %s",
                      len(price_array), len(gen_array))
        return None

    return [p * g for p, g in zip(price_array, gen_array)]