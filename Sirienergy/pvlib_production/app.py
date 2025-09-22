import logging

from flask import Flask, request, jsonify

import pandas as pd
import pvlib
from datetime import datetime

app = Flask(__name__)

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
        freq='1h',
        tz=tz
    )

    clearsky = location.get_clearsky(times, model='ineichen')
    ghi = clearsky['ghi'].tolist()

    conversion_factor = (efficiency / 100) * surface
    return [irradiance * conversion_factor for irradiance in ghi]

@app.route("/pvlib_production", methods=["POST"])
def pvlib_production():
    """Calculates photovoltaic power generation for given coordinates.

    Args:
        JSON payload containing:
            latitude (float): Location latitude in degrees
            longitude (float): Location longitude in degrees
            altitude (float): Altitude in meters
            timezone (str): Timezone identifier (e.g. 'Europe/Berlin')
            surface (float): Panel surface area in m²
            efficiency (float): Panel efficiency percentage (0-100)

    Returns:
        JSON response with power values or error message:
        - 400 for missing/invalid parameters
        - 500 for calculation errors
        - 200 with power data on success
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
        # Convert inputs to the correct types
        latitude = float(data["latitude"])
        longitude = float(data["longitude"])
        altitude = float(data["altitude"])
        surface = float(data["surface"])
        efficiency = float(data["efficiency"])
        tz = data["timezone"]  # Timezone as a string

        power_array = get_PV_gen(latitude, longitude, altitude, surface,
                                 efficiency, tz)

        # Return GHI as an array
        return jsonify({"power": power_array}), 200

    except ValueError as error:
        logging.error(f"ValueError: {error}")
        return jsonify({"error": "Something went wrong. Try again later."}), 500
    except Exception as error:
        logging.error(f"Exception: {error}")
        return jsonify({"error": str(error)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5005)