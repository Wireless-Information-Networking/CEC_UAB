"""Energy mix calculation controller for PV system revenue simulation."""

from flask import Blueprint, request, jsonify
from app.models.ENTSOE_models import *
from app.models.pvlib_model import *
import logging

mix_bp = Blueprint('mix', __name__)

@mix_bp.route('/sell', methods=['POST'])
def sell():
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
    if 'latitude' not in data or 'longitude' not in data or 'altitude' not in data or 'timezone' not in data:
        return jsonify({"error": "Invalid input. Please provide latitude, longitude, altitude, and timezone."}), 400
    
    try:
        latitude = float(data['latitude'])
        longitude = float(data['longitude'])
        altitude = float(data['altitude']) 
        surface = float(data['surface'])
        efficiency = float(data['efficiency'])
        tz = data['timezone']
        country = data['country']
        fee = data['fee'] 
        fixed_value = data['fixed_price']

        price_array = get_price_array(country, fee, fixed_value)
        power_array = get_PV_gen(latitude, longitude, altitude, surface, efficiency, tz)

        power_array = [round(value/1000, 5) for value in power_array]

        euros_by_hours = sell_by_hours(price_array, power_array)

        return jsonify({"sell": euros_by_hours})
    
    except ValueError:
        return jsonify({"error": "Something went wrong. Try again later."}), 500
