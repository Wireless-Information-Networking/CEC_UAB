"""Flask controller blueprint for ENTSO-E data integration."""

from flask import Blueprint, jsonify, request

from app.models.ENTSOE_models import (
    get_day_ahead_prices,
    get_actual_generation_by_type,
    load_co2_by_type,
    get_co2_from_dict,
)

entsoe_bp = Blueprint('entsoe', __name__)


@entsoe_bp.route('/day_ahead_prices', methods=['POST'])
def day_ahead_prices():
    """Retrieves day-ahead electricity prices for a specified country.

    Returns:
        JSON response with prices data or error message:
        - 400 if country parameter is missing
        - 500 if API request fails
        - 200 with prices data on success
    """
    data = request.get_json()
    if 'country' not in data:
        return jsonify({'error': 'Missing required parameter: country'}), 400

    try:
        prices = get_day_ahead_prices(data['country'])
        if 'error' in prices:
            return jsonify(prices), 500
        return jsonify({'data': prices}), 200
    except Exception as error:
        return jsonify({'error': str(error)}), 500


@entsoe_bp.route('/actual_gen_type', methods=['POST'])
def actual_generation_by_type():
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
        if 'error' in generation:
            return jsonify(generation), 500

        co2_dict = load_co2_by_type()
        co2 = get_co2_from_dict(generation, co2_dict)

        return jsonify({
            'data': generation,
            'co2': co2
        }), 200
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    except Exception as error:
        return jsonify({'error': str(error)}), 500
