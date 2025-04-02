import unittest
from unittest.mock import patch, mock_open
from puppeteer import (
    get_solar_production,
    get_total_consumption,
    get_battery_data,
    get_solar_grid_consumption,
    get_device_satistical_data,  # Corrected typo from 'get_device_satistical_data'
    generate_output
)
import tempfile
import os
import sys

class TestPuppeteer(unittest.TestCase):
    """A test class for unit testing functions in Puppeteer.py."""

    def setUp(self):
        """Set up the test environment before each test."""
        # Create a temporary directory for file-based tests
        self.temp_dir = tempfile.TemporaryDirectory()
        self.history_file_path = os.path.join(self.temp_dir.name, 'battery_history.json')
        # Define sample timestamps for consistent testing
        self.ts1 = "2024-01-01 00:00:00+01:00"
        self.ts2 = "2024-01-01 00:05:00+01:00"

    def tearDown(self):
        """Clean up the test environment after each test."""
        self.temp_dir.cleanup()

    ### Test for get_solar_production
    @patch('solar_module.solar_irradiance.get_solar_irradiance')
    def test_get_solar_production(self, mock_get_irradiance):
        """Test the get_solar_production function."""
        # Mock the external solar irradiance data
        mock_get_irradiance.return_value = {
            self.ts1: 0.0,    # No sunlight
            self.ts2: 100.0   # Some sunlight (W/m²)
        }
        
        # Define test parameters
        panel_eff = 0.2       # Panel efficiency (20%)
        num_panels = 10       # Number of panels
        panel_area_m2 = 2     # Area per panel in square meters
        
        # Calculate expected output: (irradiance * area * efficiency * num_panels) / 1000 (to kW)
        expected = {
            self.ts1: 0.0,                         # 0 W/m² → 0 kW
            self.ts2: (100 * 2 * 0.2 * 10) / 1000  # 100 W/m² → 0.4 kW
        }
        
        # Call the function with mocked data
        result = get_solar_production(
            solar_irr_data_json=mock_get_irradiance.return_value,
            pannel_eff=panel_eff,
            num_pannels=num_panels,
            panel_area_m2=panel_area_m2
        )
        
        # Assert the result matches the expected output
        self.assertEqual(result, expected)

    ### Tests for get_total_consumption
    @patch('npc.run_simulation')
    def test_get_total_consumption_success(self, mock_run_simulation):
        """Test get_total_consumption when simulation succeeds."""
        # Mock successful simulation output
        mock_run_simulation.return_value = (
            {self.ts1: 1.0},  # Electricity used
            {self.ts1: 2.0},  # Water used
            {self.ts1: {"electricity": {"Kitchen_stove": 0.5}}}  # Device consumption
        )
        result = get_total_consumption(config_file_data={}, output_file="test.json")
        # Verify the tuple structure and content
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], {self.ts1: 1.0})
        self.assertEqual(result[1], {self.ts1: 2.0})
        self.assertEqual(result[2], {self.ts1: {"electricity": {"Kitchen_stove": 0.5}}})

    @patch('builtins.print')
    @patch('sys.exit')
    @patch('npc.run_simulation')
    def test_get_total_consumption_failure(self, mock_run_simulation, mock_exit, mock_print):
        """Test get_total_consumption when simulation fails."""
        # Mock simulation failure
        mock_run_simulation.return_value = None
        # Expect SystemExit due to exit(1) in the function
        with self.assertRaises(SystemExit):
            get_total_consumption(config_file_data={}, output_file="test.json")
        # Verify failure message and exit code
        mock_print.assert_called_with("\033[91mSimulation failed with result None\033[0m")
        mock_exit.assert_called_with(1)

    ### Test for get_battery_data
    @patch('battery_module.battery_sim.battery_status')
    def test_get_battery_data(self, mock_battery_status):
        """Test get_battery_data function."""
        # Sample input data
        solar_prod = {self.ts1: 0.4, self.ts2: 0.5}
        total_consumpt = {self.ts1: 0.3, self.ts2: 0.4}
        # Mock battery_status responses for initial and subsequent calls
        mock_battery_status.side_effect = [
            {"battery": {"charge_level_kwh": 1.2, "discharging_rate": 0.0, "health_status": 100.0}},
            {"battery": {"charge_level_kwh": 1.25, "discharging_rate": 0.0, "health_status": 99.9}}
        ]
        result = get_battery_data(
            battery_capacity_ah=100,
            voltage=12,
            solar_prod=solar_prod,
            total_consumpt=total_consumpt,
            charge_eff=0.9,
            discharge_eff=0.9,
            energy_loss_convrt=0.05,
            degrading_ratio=0.001,
            initial_state_charge=100.0
        )
        # Verify timestamps and mocked data
        self.assertIn(self.ts1, result)
        self.assertIn(self.ts2, result)
        self.assertEqual(result[self.ts1], {"battery": {"charge_level_kwh": 1.2, "discharging_rate": 0.0, "health_status": 100.0}})
        self.assertEqual(result[self.ts2], {"battery": {"charge_level_kwh": 1.25, "discharging_rate": 0.0, "health_status": 99.9}})

    ### Test for get_solar_grid_consumption
    def test_get_solar_grid_consumption(self):
        """Test get_solar_grid_consumption function."""
        # Test normal consumption
        solar_prod = {self.ts1: 0.4}
        total_consumpt = {self.ts1: 0.5}
        expected = {self.ts1: 0.1}  # 0.5 - 0.4
        result = get_solar_grid_consumption(solar_prod, total_consumpt)
        self.assertEqual(result, expected)
        
        # Test excess solar production
        solar_prod = {self.ts1: 0.6}
        expected = {self.ts1: -0.1}  # 0.5 - 0.6
        result = get_solar_grid_consumption(solar_prod, total_consumpt)
        self.assertEqual(result, expected)

    ### Test for get_device_statistical_data
    def test_get_device_statistical_data(self):
        """Test get_device_statistical_data function."""
        # Sample device consumption data
        dev_dict = {
            self.ts1: {
                "electricity": {"Kitchen_stove": 0.5, "Living_room_tv": 0.1},
                "water": {"Bathroom_shower": 10.0}
            }
        }
        result = get_device_satistical_data(dev_dict)
        # Verify structure and basic statistics
        self.assertIn(self.ts1, result)
        elec_stats = result[self.ts1]["electricity"]
        self.assertEqual(elec_stats["number_of_devices"], 2)
        self.assertAlmostEqual(elec_stats["mean_consumption"], 0.3, delta=0.01)
        self.assertEqual(result[self.ts1]["water"]["number_of_devices"], 1)

    ### Test for generate_output
    @patch('builtins.open', new_callable=mock_open)
    @patch('json.dump')
    def test_generate_output(self, mock_json_dump, mock_open_file):
        """Test generate_output function."""
        # Sample data for all parameters
        house_id = "test_house"
        solar_prod = {self.ts1: 0.4}
        electricity_consumption = {self.ts1: 0.5}
        water_consumption = {self.ts1: 10.0}
        device_consumption = {self.ts1: {"electricity": {"Kitchen_stove": 0.3}, "water": {"Bathroom_shower": 10.0}}}
        solar_grid_consumption = {self.ts1: 0.1}
        battery_data = {self.ts1: {"battery": {"charge_level_kwh": 1.2, "discharging_rate": 0.0, "health_status": 100.0}}}
        device_statistical_data = {
            self.ts1: {
                "electricity": {"gini_coefficient": 0.0, "number_of_devices": 1},
                "water": {"number_of_devices": 1}
            }
        }
        temperature = 20.0
        humidity = 50.0
        air_quality = 50
        air_quality_description = "Good"
        
        # Call the function
        generate_output(
            houseID=house_id,
            solar_production=solar_prod,
            electricity_consumption=electricity_consumption,
            water_consumption=water_consumption,
            device_consumption=device_consumption,
            solar_grid_consumption=solar_grid_consumption,
            battery_data=battery_data,
            device_statistical_data=device_statistical_data,
            temperature=temperature,
            humidity=humidity,
            air_quality=air_quality,
            air_quality_description=air_quality_description
        )
        
        # Verify file opening
        mock_open_file.assert_called_with(f"results/{house_id}_output.json", "w")
        
        # Verify the data structure passed to json.dump
        output_data = mock_json_dump.call_args[0][0]
        self.assertEqual(len(output_data), 1)
        ts_data = output_data[0]
        self.assertEqual(ts_data["house_id"], house_id)
        self.assertEqual(ts_data["timestamp"], self.ts1)
        self.assertEqual(ts_data["energy_management_sensors"]["solar_power"]["production"], 0.4)
        self.assertEqual(ts_data["energy_management_sensors"]["battery"]["charge_level"], 1.2)
        self.assertEqual(ts_data["water_management_sensors"]["usage_tracking"], 10.0)
        self.assertEqual(ts_data["climate_and_environment_sensors"]["temperature"], 20.0)

if __name__ == '__main__':
    """Run all tests when the script is executed."""
    unittest.main()