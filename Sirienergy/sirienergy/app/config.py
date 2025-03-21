import os

class Config:
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    WEATHER_API_API_KEY = os.getenv('WEATHER_API_API_KEY')
    ENTSO_E_API_KEY = os.getenv('ENTSO_E_API_KEY')
    DEBUG = 1
