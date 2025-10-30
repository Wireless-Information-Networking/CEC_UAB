import os
import logging

from flask import Flask, request, jsonify

from typing import Dict, Optional
from datetime import datetime, timedelta
import csv
import requests
import json
import xmltodict

app = Flask(__name__)

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


def load_entsoe_gentype_names() -> Dict[str, str]:
    """Loads generation type names from a CSV file for ENTSO-E API queries.

    Returns:
        Dict[str, str]: A dictionary mapping ENTSO-E generation type keys to
            their names.
    """
    base_dir = os.path.dirname(__file__)
    file_path = os.path.abspath(
        os.path.join(base_dir, "common_files/entsoe/entsoe_gentype_names.csv")
    )

    entsoe_gentype_names: Dict[str, str] = {}
    with open(file_path, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            entsoe_gentype_names[row["key"]] = row["name"]
    return entsoe_gentype_names


def get_actual_generation_by_type(country_name: str
                                  ) -> Optional[Dict[str, int]]:
    """Retrieves actual electricity generation data by type for a given country.

    Args:
        country_name: The name of the country for which to retrieve generation
            data.

    Returns:
        A dictionary mapping generation types to their values, or None on error.
    """
    endpoint = "https://web-api.tp.entsoe.eu/api"
    current_datetime = datetime.utcnow()
    yesterday_datetime = current_datetime - timedelta(days=1)
    current_formatted = current_datetime.strftime("%Y%m%d") + "2200"
    yesterday_formatted = yesterday_datetime.strftime("%Y%m%d") + "2200"
    

    entsoe_country_keys = load_entsoe_country_keys()
    #logging.error(f"Available countries are: {list(entsoe_country_keys.keys())}")
    if country_name not in entsoe_country_keys:
        logging.error("Key for country %s not found", country_name)
        return None

    country_key = entsoe_country_keys[country_name]
    params = {
        "securityToken": ENTSO_E_API_KEY,
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
    time_series_list = data_json.get("GL_MarketDocument", {}).get(
        "TimeSeries", [])
    last_up_time = yesterday_datetime
    date_format = "%Y-%m-%dT%H:%MZ"

    if time_series_list:
        if not isinstance(time_series_list, list):
            time_series_list = [time_series_list]
        
        for time_series in time_series_list:
            # Normalize Period
            period = time_series["Period"]
            if isinstance(period, list):
                period = period[-1]  # Use last period
            
            update_time_str = period["timeInterval"]["end"]
            update_time = datetime.strptime(update_time_str, date_format)
            if update_time > last_up_time:
                last_up_time = update_time


        last_up_time_str = last_up_time.strftime(date_format)
        entsoe_gentype_names = load_entsoe_gentype_names()

        for time_series in time_series_list:
            # ADD THESE 3 LINES:
            period = time_series["Period"]
            if isinstance(period, list):
                period = period[-1]
            
            # CHANGE THIS LINE:
            if last_up_time_str == period["timeInterval"]["end"]:  # Changed from time_series["Period"]
            
                psr_type = time_series["MktPSRType"]["psrType"]
        
                # Skip unknown generation types
                if psr_type not in entsoe_gentype_names:
                    logging.warning(f"Unknown psrType: {psr_type} - skipping")
                    continue
            
                gentype = entsoe_gentype_names[psr_type]
                
                # Normalize Point to always be a list
                points = period["Point"]  # CHANGED from time_series["Period"]["Point"]
                if not isinstance(points, list):
                    points = [points]

                if "inBiddingZone_Domain.mRID" in time_series:
                    # Get the last point's quantity
                    gens[gentype] = int(float(points[-1]["quantity"])) #hello
                else:
                    gens[gentype] = gens.get(gentype, 0)

        gens = {key: value for key, value in gens.items() if value != 0}
    else:
        logging.info("No valid time series data found.")
        
    logging.info(f"Returning generation data for {country_name}: {gens}")


    return gens


def load_co2_by_type(file_path: str = "entsoe/co2.csv"
                     ) -> Dict[str, float]:
    """Loads CO2 emission factors by generation type from a CSV file.

    Args:
        file_path: The path to the CSV file. Defaults to 
            "entsoe_tables/co2.csv".

    Returns:
        A dictionary mapping energy types to their CO2 emission 
        factors (gCO2eq/Wh).
    """
    base_dir = os.path.dirname(__file__)
    file_path = os.path.abspath(
        os.path.join(base_dir, "common_files/entsoe/co2.csv")
    )

    co2_by_gentype = {}
    with open(file_path, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            co2_by_gentype[row["Energy Type"]] = float(row["gCO2eq/Wh"])
    return co2_by_gentype


def get_co2_from_dict(
    power_dict: Dict[str, int], co2_dict: Dict[str, float]
) -> float:
    """Calculates total CO2 emissions based on power generation and emission 
    factors.

    Args:
        power_dict: A dictionary mapping generation types to power values.
        co2_dict: A dictionary mapping generation types to CO2 emission factors.

    Returns:
        The total CO2 emissions in gCO2eq.
    """
    return sum(value * co2_dict.get(key, 0.0) for key, value in
               power_dict.items())

        
@app.route('/entsoe_gentype', methods=['POST'])
def entsoe_gentype():
    """Retrieves actual generation mix and CO2 emissions for a country.
    
    Returns:
        JSON response with generation data and CO2 emissions:
        - 400 if country parameter is missing
        - 500 if API request or calculation fails
        - 200 with data on success
    
    """
    data = request.get_json()
    if 'country' not in data:
        return jsonify({'error': 'Missing required parameter: country'}), 400

    try:
        generation = get_actual_generation_by_type(data['country'])
        
        # Check for None before using the result
        if generation is None:
            return jsonify({'error': 'Failed to retrieve generation data'}), 500

        co2_dict = load_co2_by_type()
        logging.info(f"CO2 dict loaded successfully for {data['country']}")  # ADD THIS
        
        co2 = get_co2_from_dict(generation, co2_dict)
        logging.info(f"CO2 calculated: {co2}")  # ADD THIS

        return jsonify({
            'data': generation,
            'co2': co2
        }), 200
    except ValueError as error:
      logging.error(f"ValueError occurred: {error}", exc_info=True)  # ADD exc_info=True
      return jsonify({'error': str(error)}), 400

    except Exception as error:
        logging.exception("Unexpected error in entsoe_gentype")
        return jsonify({'error': str(error)}), 500



if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5004)
