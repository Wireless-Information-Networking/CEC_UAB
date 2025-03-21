"""Flask controller blueprint for Redis-based user energy management."""

import os
import re
import sys
from datetime import datetime

from flask import Blueprint, jsonify, request
from app.models.CEC_model import RedisModel

redis_bp = Blueprint('redis', __name__)
redis_model = RedisModel()


def complete_and_order_hours(data, default_value=0):
    """Completes and orders hourly data with default values for missing hours.
    
    Args:
        data (dict): Dictionary of hour-value pairs to complete.
        default_value (int, optional): Default value for missing hours. Defaults to 0.
    
    Returns:
        dict: Ordered dictionary with all 24 hours in "HH:00" format.
    """
    all_hours = [datetime(2000, 1, 1, h).strftime("%H:00") for h in range(24)]
    completed_data = {hour: data.get(hour, default_value) for hour in all_hours}
    return dict(sorted(completed_data.items()))


def is_valid_email(email):
    """Validates an email address format.
    
    Args:
        email (str): Email address to validate.
    
    Returns:
        bool: True if valid email format, False otherwise.
    """
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_regex, email) is not None


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


@redis_bp.route('/create_user', methods=['POST'])
def create_user():
    """Creates a new user in the Redis database.
    
    Returns:
        tuple: (JSON response, HTTP status code)
    """
    try:
        data = request.get_json()
        user_email = data.get('user_email')
        user_name = data.get('user_name')
        user_password = data.get('user_password')
    except Exception as error:
        return jsonify({'error': f'Invalid input: {str(error)}'}), 400

    if not all([user_email, user_name, user_password]):
        return jsonify({'error': 'Missing required fields'}), 400
    if not is_valid_email(user_email):
        return jsonify({'error': 'Invalid email format'}), 400

    try:
        response = redis_model.create_user(user_name, user_email, user_password)
        return jsonify(response), 200
    except Exception as error:
        return jsonify({'error': str(error)}), 500


@redis_bp.route('/add_consumption', methods=['POST'])
def add_consumption():
    """Adds consumption data for a user.
    
    Returns:
        tuple: (JSON response, HTTP status code)
    """
    try:
        data = request.get_json()
        user_email = data['user_email']
        date = data['date']
        hour = data['hour']
        value = data['value']
    except KeyError as error:
        return jsonify({'error': f'Missing key: {str(error)}'}), 400

    try:
        response = redis_model.add_consumption(user_email, date, hour, value)
        return jsonify(response), 200
    except ValueError as error:
        return jsonify({'error': str(error)}), 400


@redis_bp.route('/add_production', methods=['POST'])
def add_production():
    """Adds production data for a user.
    
    Returns:
        tuple: (JSON response, HTTP status code)
    """
    try:
        data = request.get_json()
        user_email = data['user_email']
        date = data['date']
        hour = data['hour']
        value = data['value']
    except KeyError as error:
        return jsonify({'error': f'Missing key: {str(error)}'}), 400

    try:
        response = redis_model.add_production(user_email, date, hour, value)
        return jsonify(response), 200
    except ValueError as error:
        return jsonify({'error': str(error)}), 400


@redis_bp.route('/get_production_day', methods=['POST'])
def get_production():
    """Retrieves production data for the current day.
    
    Returns:
        tuple: (JSON response, HTTP status code)
    """
    try:
        data = request.get_json()
        user_email = data['email']
    except KeyError:
        return jsonify({'error': 'Missing required field: email'}), 400

    try:
        existing_data = redis_model.get_user(user_email)
        if existing_data is None:
            return jsonify({'error': 'User not registered'}), 400

        current_date = datetime.now().strftime("%Y-%m-%d")
        response = redis_model.get_production_day(user_email, current_date)[0]
        ordered_response = complete_and_order_hours(response)

        sys.stderr.write(
            f"|{os.getpid()}| [Controller] (get_production) "
            f"Completed dict: {ordered_response}\n"
        )
        return jsonify({'hourly': ordered_response}), 200
    except ValueError as error:
        return jsonify({'error': str(error)}), 400


@redis_bp.route('/get_consumption_day', methods=['POST'])
def get_consumption():
    """Retrieves consumption data for the current day.
    
    Returns:
        tuple: (JSON response, HTTP status code)
    """
    try:
        data = request.get_json()
        user_email = data['email']
    except KeyError:
        return jsonify({'error': 'Missing required field: email'}), 400

    try:
        existing_data = redis_model.get_user(user_email)
        if existing_data is None:
            return jsonify({'error': 'User not registered'}), 400

        current_date = datetime.now().strftime("%Y-%m-%d")
        response = redis_model.get_consumption_day(user_email, current_date)[0]
        ordered_response = complete_and_order_hours(response)

        sys.stderr.write(
            f"|{os.getpid()}| [Controller] (get_consumption) "
            f"Completed dict: {ordered_response}\n"
        )
        return jsonify({'hourly': ordered_response}), 200
    except ValueError as error:
        return jsonify({'error': str(error)}), 400


@redis_bp.route('/get_surplus_day', methods=['POST'])
def get_surplus_hourly():
    """Retrieves hourly energy surplus for the current day.
    
    Returns:
        tuple: (JSON response, HTTP status code)
    """
    try:
        data = request.get_json()
        user_email = data['email']
    except KeyError:
        return jsonify({'error': 'Missing required field: email'}), 400

    try:
        existing_data = redis_model.get_user(user_email)
        if existing_data is None:
            return jsonify({'error': 'User not registered'}), 400

        response = get_surplus_aux(user_email=user_email)
        return jsonify({'hourly': response}), 200
    except ValueError as error:
        return jsonify({'error': str(error)}), 400