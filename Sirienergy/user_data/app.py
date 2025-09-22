import os

from flask import Flask, request, jsonify

from datetime import datetime
import json
import redis
import sys
import hashlib

app = Flask(__name__)

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

def hour_value_to_list(surplus):
    surplus_list = []
    for value in surplus.values():
        surplus_list.append(value)
    return surplus_list

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

@app.route("/user_data/get_production_day", methods=["POST"])
def get_production():
    """Retrieves production data for the current day.
    
    Returns:
        tuple: (JSON response, HTTP status code)
    """
    try:
        data = request.get_json()
        user_email = data["email"]
    except KeyError:
        return jsonify({"error": "Missing required field: email"}), 400

    try:
        existing_data = redis_model.get_user(user_email)
        if existing_data is None:
            return jsonify({"error": "User not registered"}), 400

        current_date = datetime.now().strftime("%Y-%m-%d")
        response = redis_model.get_production_day(user_email, current_date)[0]
        ordered_response = complete_and_order_hours(response)

        sys.stderr.write(
            f"|{os.getpid()}| [Controller] (get_production) "
            f"Completed dict: {ordered_response}\n"
        )
        return jsonify({"hourly": ordered_response}), 200
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

@app.route("/user_data/get_consumption_day", methods=["POST"])
def get_consumption():
    """Retrieves consumption data for the current day.
    
    Returns:
        tuple: (JSON response, HTTP status code)
    """
    try:
        data = request.get_json()
        user_email = data["email"]
    except KeyError:
        return jsonify({"error": "Missing required field: email"}), 400

    try:
        existing_data = redis_model.get_user(user_email)
        if existing_data is None:
            return jsonify({"error": "User not registered"}), 400

        current_date = datetime.now().strftime("%Y-%m-%d")
        response = redis_model.get_consumption_day(user_email, current_date)[0]
        ordered_response = complete_and_order_hours(response)

        sys.stderr.write(
            f"|{os.getpid()}| [Controller] (get_consumption) "
            f"Completed dict: {ordered_response}\n"
        )
        return jsonify({"hourly": ordered_response}), 200
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

@app.route("/user_data/get_surplus_day", methods=["POST"])
def get_surplus_hourly():
    """Retrieves hourly energy surplus for the current day.
    
    Returns:
        tuple: (JSON response, HTTP status code)
    """
    try:
        data = request.get_json()
        user_email = data["email"]
    except KeyError:
        return jsonify({"error": "Missing required field: email"}), 400

    try:
        existing_data = redis_model.get_user(user_email)
        if existing_data is None:
            return jsonify({"error": "User not registered"}), 400

        response = get_surplus_aux(user_email=user_email)
        return jsonify({"hourly": response}), 200
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

@app.route("/user_data/get_cons_peaks", methods=["POST"])
def get_cons_peaks():
    try:
        data = request.json
        user_email = data["email"]

    except KeyError as e:
        return jsonify({"error": f"Missing key: {str(e)}"}), 400

    current_date = datetime.now().strftime("%Y-%m-%d")
    consumption = redis_model.get_consumption_day(user_email, current_date)[0]

    if consumption is None:
        return jsonify({"error": "User not registered"}), 400

    consumption = hour_value_to_list(consumption)

    consumption_mean = sum(consumption) / len(consumption)

    surplus = get_surplus_aux(user_email)

    peak_hours = []
    threshold = -1 * consumption_mean
    for key, value in surplus.items():
        if value < threshold:
            peak_hours.append(key)

    return jsonify({"peak_hours": peak_hours}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5008)