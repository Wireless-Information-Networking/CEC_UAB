import requests


########################################### TEMPERATURE AND HUMIDITY ###########################################

def get_temp_hum():
    url_temp_hum = "https://wttr.in/Bellaterra?format=j1"
    try:
        # Realizar la solicitud GET
        response = requests.get(url_temp_hum)
        response.raise_for_status()  # Lanza una excepción si la solicitud falla
        
        # Convertir la respuesta en formato JSON
        weather_data = response.json()

        temperature = weather_data["current_condition"][0]["temp_C"]
        humidity = weather_data["current_condition"][0]["humidity"]

        return temperature, humidity
        
    except requests.exceptions.RequestException as e:
        print(f"Error obtaining temp and humid data: {e}")
    except KeyError as e:
        print(f"Error processing temp and humid data: {e}")


def get_aq():

     # Define the API URL and the API key
    url = "http://api.openweathermap.org/data/2.5/air_pollution?lat=41.502039828950366&lon=2.103702324404792&appid=1fedbd7ce89e07c285feadbacc97e42c"

    # Send the GET request
    response = requests.get(url)

    # Check if the response is successful
    if response.status_code == 200:
        data = response.json()
        
        # Retrieve the AQI value from the response
        aqi = data["list"][0]["main"]["aqi"]

        if aqi == 1:
            description = "Air quality outside is good"
        elif aqi == 2:
            description = "Air quality outside is fair"
        elif aqi == 3:
            description = "Air quality outside is moderate"
        elif aqi == 4:
            description = "Air quality outside is poor"
        elif aqi == 5:
            description = "Air quality outside is very poor"
        
        return aqi, description


    else:
        print(f"Error: Unable to fetch data (status code {response.status_code})")




# Llamar a la función
if __name__ == "__main__":
    
    temperature, humidity = get_temp_hum()
    aqi, description = get_aq()

    print(f"Temperature: {temperature}°C")
    print(f"Humidity: {humidity}%")
    print(f"AQI: {aqi} --> {description}")
    





















'''
########################################### AIR QUALITY ###########################################
    import openmeteo_requests
    import requests_cache
    import pandas as pd
    from retry_requests import retry

    # Setup the Open-Meteo API client with cache and retry on error
    cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    # Make sure all required weather variables are listed here
    # The order of variables in hourly or daily is important to assign them correctly below
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": 41.50232105928564,
        "longitude": 2.104142206661723,
        "current": "european_aqi",
    }
    responses = openmeteo.weather_api(url, params=params)

    # Process first location. Add a for-loop for multiple locations or weather models
    response = responses[0]
    print(f"Coordinates {response.Latitude()}°N {response.Longitude()}°E")
    print(f"Elevation {response.Elevation()} m asl")
    print(f"Timezone {response.Timezone()} {response.TimezoneAbbreviation()}")
    print(f"Timezone difference to GMT+0 {response.UtcOffsetSeconds()} s")

    # Current values. The order of variables needs to be the same as requested.
    current = response.Current()
    current_european_aqi = current.Variables(0).Value()

    print(f"Current time {current.Time()}")
    print(f"Current european_aqi {current_european_aqi}")

'''


