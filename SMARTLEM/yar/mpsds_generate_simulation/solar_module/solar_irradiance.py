
from pvlib import location
import pandas as pd
from typing import Dict

def get_solar_irradiance(lat: float, lon: float, tz: str, start_date: str, end_date: str) -> Dict[str, float]:
    """
    Function to obtain the global solar irradiance at a specific location and date range.
    
    Args:
        lat: float. Latitude of the location.
        lon: float. Longitude of the location.
        tz: str. Time zone of the location.
        start_date: str. Start date.
        end_date: str. End date.
    
    Returns:
        ghi_dict: dict. Dictionary with the global solar irradiance for the specified date range.
    """
    
    start_date = pd.to_datetime(start_date) # Convertir a formato datetime
    end_date = pd.to_datetime(end_date) # Convertir a formato datetime
    
    # Definir el tiempo
    times = pd.date_range(start=start_date, end=end_date, freq='5min', tz=tz)

    # Crear objeto de ubicación
    ubicacion = location.Location(lat, lon, tz=tz)

    # Obtener datos de cielo despejado
    cielo_despejado = ubicacion.get_clearsky(times)

    # GHI de cielo despejado
    ghi = cielo_despejado['ghi']
    ghi_dict = {str(k): v for k, v in ghi.to_dict().items()}
    
    return ghi_dict


# Example usage
if __name__ == "__main__":
    
    
    latitud_barcelona, longitud_barcelona = 41.38879, 2.15899  # Barcelona, España
    tz = 'Europe/Madrid'
    fecha_inicio = pd.Timestamp('2024-01-01')
    fecha_fin = pd.Timestamp('2024-01-02')
    
    ghi_dict = get_solar_irradiance(latitud_barcelona, longitud_barcelona, tz, fecha_inicio, fecha_fin)
    print(ghi_dict)
    
    #save it in json file
    import json
    with open('ghi_dict.json', 'w') as f:
        json.dump(ghi_dict, f)
    