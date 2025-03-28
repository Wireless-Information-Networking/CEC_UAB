"""Redis-based user data management module.

This module provides a class to manage user data stored in Redis, including
user creation, consumption tracking, and production tracking.
"""

import hashlib
import json
import redis
from app.aux.aux_modules.logging_helper import log_message
from app.config import Config

MODULE_TYPE = "model"
MODULE_NAME = "CEC"
MODULE_DEBUG = 1


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
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
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

    def get_user(self, user_email: str) -> dict | None:
        """Retrieves user data from Redis.

        Args:
            user_email: The user's email (used as a unique key).

        Returns:
            A dictionary with the user data or None if not found.
        """
        key = f"user:{user_email}"
        json_data = self.client.execute_command("JSON.GET", key)
        if Config.DEBUG and MODULE_DEBUG and 1:
            log_message(
                "debug", MODULE_TYPE, MODULE_NAME, "get_user",
                f"Key: {key}, Query result: {json_data}"
            )
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
        if Config.DEBUG and MODULE_DEBUG and 1:
            log_message(
                "debug", MODULE_TYPE, MODULE_NAME, "get_data_day",
                f"Key: {key}, Date path: {date_path}"
            )
        try:
            existing_data = self.client.execute_command("JSON.GET", key,
                                                        date_path)
            if Config.DEBUG and MODULE_DEBUG and 1:
                log_message(
                    "debug", MODULE_TYPE, MODULE_NAME, "get_data_day",
                    f"Data got from BD: \n {existing_data}"
                )

            data_json = json.loads(existing_data) if existing_data else {}
            if Config.DEBUG and MODULE_DEBUG and 1:
                log_message(
                    "debug", MODULE_TYPE, MODULE_NAME, "get_data_day",
                    f"Data got from BD as a json: \n {data_json}"
                )

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
