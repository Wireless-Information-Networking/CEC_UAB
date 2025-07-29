from datetime import datetime, timezone
import pvlib
import pandas as pd
import matplotlib.pyplot as plt  # Add this import

def get_temp_hum_day(year: int, month: int, day: int):
    latitude, longitude = 41.38879, 2.15899  # Barcelona coordinates

    # Retrieve TMY data with the datetime index coerced to the desired year
    tmy_data, metadata, inputs, _ = pvlib.iotools.get_pvgis_tmy(
        latitude, longitude,
        outputformat='json',
        usehorizon=True,
        coerce_year=year
    )

    # Ensure the index is timezone-aware (UTC)
    tmy_data.index = tmy_data.index.tz_convert('UTC')

    # Filter data for the specified day
    mask = (tmy_data.index.month == month) & (tmy_data.index.day == day)
    day_data = tmy_data.loc[mask, ['temp_air', 'relative_humidity']]

    return day_data

# Example usage
if __name__ == "__main__":
    year = 2025
    month = 6
    day = 21
    day_data = get_temp_hum_day(year, month, day)
    print(day_data.to_string(index=True, header=True))

    # Plot temperature
    plt.figure(figsize=(10, 5))
    plt.plot(day_data.index, day_data['temp_air'], marker='o')
    plt.title(f"Temperature on {year}-{month:02d}-{day:02d} (Barcelona)")
    plt.xlabel("Time (UTC)")
    plt.ylabel("Temperature (°C)")
    plt.grid(True)
    plt.tight_layout()
    plt.show()
