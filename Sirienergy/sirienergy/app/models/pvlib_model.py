"""Photovoltaic power generation calculation module using pvlib."""

from datetime import datetime

import pandas as pd
import pvlib


def get_PV_gen(
    latitude: float,
    longitude: float,
    altitude: float,
    surface: float,
    efficiency: float,
    tz: str,
) -> list[float]:
    """Calculates photovoltaic (PV) power generation for a location and system.

    Args:
        latitude: Latitude of the location in degrees.
        longitude: Longitude of the location in degrees.
        altitude: Altitude of the location in meters.
        surface: Surface area of PV panels in square meters.
        efficiency: PV panel efficiency percentage (0-100).
        tz: Timezone of the location (e.g., 'Europe/Berlin').

    Returns:
        List of hourly PV power generation values in watts for September 21,
        2024.
    """
    location = pvlib.location.Location(
        latitude=latitude,
        longitude=longitude,
        tz=tz,
        altitude=altitude
    )

    times = pd.date_range(
        start=datetime(2024, 9, 21, 0),
        end=datetime(2024, 9, 21, 23, 59),
        freq='1h',
        tz=tz
    )

    clearsky = location.get_clearsky(times, model='ineichen')
    ghi = clearsky['ghi'].tolist()

    conversion_factor = (efficiency / 100) * surface
    return [irradiance * conversion_factor for irradiance in ghi]
