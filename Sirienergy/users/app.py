import os
import logging

from flask import Flask, request, jsonify

import re
import hashlib
import json
import redis

app = Flask(__name__)

def hash_password(password: str) -> str:
    """Hashes a password using SHA-256.

    Args:
        password: The password to hash.

    Returns:
        The hashed password as a hexadecimal string.
    """
    return hashlib.sha256(password.encode()).hexdigest()

def is_valid_email(email):
    """Validates an email address format.
    
    Args:
        email (str): Email address to validate.
    
    Returns:
        bool: True if valid email format, False otherwise.
    """
    email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(email_regex, email) is not None

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

@app.route("/users/create_user", methods=["POST"])
def create_user():
    """Creates a new user in the Redis database.
    
    Returns:
        tuple: (JSON response, HTTP status code)
    """
    try:
        data = request.get_json()
        user_email = data.get("user_email")
        user_name = data.get("user_name")
        user_password = data.get("user_password")
    except Exception as error:
        return jsonify({"error": f"Invalid input: {str(error)}"}), 400

    if not all([user_email, user_name, user_password]):
        return jsonify({"error": "Missing required fields"}), 400
    if not is_valid_email(user_email):
        return jsonify({"error": "Invalid email format"}), 400

    try:
        response = redis_model.create_user(user_name, user_email, user_password)
        return jsonify(response), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500
    
@app.route("/users/add_consumption", methods=["POST"])
def add_consumption():
    """Adds a consumption record for a user.
    
    Returns:
        tuple: (JSON response, HTTP status code)
    """
    try:
        data = request.get_json()
        user_email = data.get("user_email")
        date = data.get("date")
        hour = data.get("hour")
        value = data.get("value")
    except Exception as error:
        return jsonify({"error": f"Invalid input: {str(error)}"}), 400

    if not is_valid_email(user_email):
        return jsonify({"error": "Invalid email format"}), 400
    try:
        value = float(value)
    except ValueError:
        return jsonify({"error": "Value must be a number"}), 400

    try:
        response = redis_model.add_consumption(user_email, date, hour, value)
        return jsonify(response), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500
    
@app.route("/users/add_production", methods=["POST"])
def add_production():
    """Adds a production record for a user.
    
    Returns:
        tuple: (JSON response, HTTP status code)
    """
    try:
        data = request.get_json()
        user_email = data.get("user_email")
        date = data.get("date")
        hour = data.get("hour")
        value = data.get("value")
    except Exception as error:
        return jsonify({"error": f"Invalid input: {str(error)}"}), 400

    if not is_valid_email(user_email):
        return jsonify({"error": "Invalid email format"}), 400
    try:
        value = float(value)
    except ValueError:
        return jsonify({"error": "Value must be a number"}), 400

    try:
        response = redis_model.add_production(user_email, date, hour, value)
        return jsonify(response), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5007)