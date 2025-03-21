"""Weather data controller for retrieving and visualizing weather conditions."""

from flask import Blueprint, jsonify, render_template, request
from app.models.weather_model import get_weather, get_sunrise_sunset, image_array

weather_bp = Blueprint('weather', __name__)


@weather_bp.route('/weather', methods=['POST'])
def weather() -> tuple[str | dict, int]:
    """Retrieves weather data and generates visual representation.

    Args:
        JSON payload containing:
            latitude (float): Location latitude in degrees
            longitude (float): Location longitude in degrees
            timezone (str): Timezone identifier (e.g. 'Europe/Berlin')

    Returns:
        Rendered HTML template with weather images on success
        JSON error response with status code on failure:
        - 400 for missing/invalid parameters
        - 500 for data retrieval failures

    Raises:
        Various exceptions from underlying weather model functions
    """
    required_params = ['latitude', 'longitude', 'timezone']
    data = request.get_json()

    # Validate required parameters
    if not all(param in data for param in required_params):
        missing = [p for p in required_params if p not in data]
        return jsonify({
            'error': f'Missing required parameters: {", ".join(missing)}'
        }), 400

    try:
        # Convert and validate coordinates
        latitude = float(data['latitude'])
        longitude = float(data['longitude'])
        timezone = data['timezone']

        # Retrieve weather data
        weather_codes = get_weather(latitude, longitude, timezone)
        sunrise, sunset = get_sunrise_sunset(latitude, longitude)
        image_list = image_array(weather_codes, sunrise, sunset)

        return render_template('weather_images.html', images=image_list)

    except ValueError as e:
        return jsonify({
            'error': f'Invalid coordinate values: {str(e)}'
        }), 400
    except Exception as e:
        return jsonify({
            'error': f'Weather data retrieval failed: {str(e)}'
        }), 500