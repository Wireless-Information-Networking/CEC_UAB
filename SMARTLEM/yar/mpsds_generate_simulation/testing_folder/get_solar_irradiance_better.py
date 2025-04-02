from datetime import datetime

def standardize_timestamp_format(timestamp):
    """Convert a timestamp to a standardized ISO format without 'T' separator."""
    dt = datetime.fromisoformat(timestamp.replace("T", " "))
    return dt.strftime("%Y-%m-%d %H:%M:%S%z")

def get_solar_grid_consumption(solar_production, total_electr_consumption):
    """
    Calculate the electrical grid consumption based on the solar production and total electricity consumption.
    
    If the value is negative, it means that there is an excess of solar production.
    If the value is positive, it means that the house is consuming more electricity than the solar panels are producing.
    
    Args:
        solar_production (dict): Solar production data in kW. With timestamp as key and production in kW as value.
        total_electr_consumption (dict): Total electricity consumption in kW. With timestamp as key and consumption in kW as value.
        
    Returns:
        dict: Dictionary containing the electrical grid consumption data. With timestamp as key and consumption in kW as value.
    """
    
    # If both dictionaries are empty, raise an error
    if not solar_production and not total_electr_consumption:
        raise ValueError("Both solar production and total electricity consumption are empty.")

    # If one of the dictionaries is empty, raise an error
    if not solar_production:
        raise ValueError("Solar production data is empty.")
    if not total_electr_consumption:
        raise ValueError("Total electricity consumption data is empty.")

    # Standardize timestamps in both dictionaries
    standardized_solar_production = {standardize_timestamp_format(ts): value for ts, value in solar_production.items()}
    standardized_total_electr_consumption = {standardize_timestamp_format(ts): value for ts, value in total_electr_consumption.items()}

    # If the timestamps are not the same, raise an error
    if standardized_solar_production.keys() != standardized_total_electr_consumption.keys():
        # Print the first of the solar production and total electricity consumption timestamps
        print(f" sp -> {list(standardized_solar_production.keys())[:5]}")
        print(f" ec -> {list(standardized_total_electr_consumption.keys())[:5]}")
        
        raise ValueError("Timestamps in solar production and total electricity consumption data do not match.")

    # Calculate the grid consumption
    grid_consumption = {
        timestamp: standardized_total_electr_consumption[timestamp] - standardized_solar_production[timestamp]
        for timestamp in standardized_solar_production.keys()
    }
    
    return grid_consumption

# Example usage
if __name__ == "__main__":
    # Example data
    solar_prod = {
        "2021-01-01 00:00:00+01:00": 0.5,
        "2021-01-01 00:05:00+01:00": 0.6,
        "2021-01-01 00:10:00+01:00": 0.7,
    }
    total_electr_consumption = {
        "2021-01-01 00:00:00+01:00": 1.0,
        "2021-01-01 00:05:00+01:00": 1.1,
        "2021-01-01 00:10:00+01:00": 1.2,
    }

    try:
        grid_consumption = get_solar_grid_consumption(solar_production=solar_prod, total_electr_consumption=total_electr_consumption)
        print("Grid consumption:", grid_consumption)
    except ValueError as e:
        print("Error:", e)