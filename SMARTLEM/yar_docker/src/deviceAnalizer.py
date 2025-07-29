#!/usr/bin/env python3
"""
MPSDS Consumption Analysis and Visualization Script

This script analyzes and visualizes consumption data from the MPSDS simulation system.
It can graph energy consumption, water usage, battery performance, and device usage patterns.

Author: Generated for MPSDS project
Date: 2025-07-25
"""

import json
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import seaborn as sns
from pathlib import Path
import argparse
import warnings

# Set style for better-looking plots
plt.style.use('seaborn-v0_8')
sns.set_palette("husl")
warnings.filterwarnings('ignore')

class MPSDSAnalyzer:
    """Main class for analyzing and visualizing MPSDS consumption data."""
    
    def __init__(self, data_directory="./"):
        """Initialize the analyzer with data directory path."""
        self.data_dir = Path(data_directory)
        self.user_data = None
        self.simulation_output = None
        self.battery_history = None
        
    def load_data(self):
        """Load all available data files."""
        try:
            # Load user data (summary)
            user_data_path = self.data_dir / "results" / "user_data.json"
            if user_data_path.exists():
                with open(user_data_path, 'r') as f:
                    self.user_data = json.load(f)
                print(f"✓ Loaded user data: {self.user_data['house_name']}")
            
            # Load detailed simulation output
            sim_output_path = self.data_dir / "sim_result" / "john_doe's_smart_house_output.json"
            if sim_output_path.exists():
                with open(sim_output_path, 'r') as f:
                    self.simulation_output = json.load(f)
                print(f"✓ Loaded simulation output: {len(self.simulation_output)} records")
            
            # Load battery history
            battery_path = self.data_dir / "battery_history.json"
            if battery_path.exists():
                with open(battery_path, 'r') as f:
                    self.battery_history = json.load(f)
                print(f"✓ Loaded battery history: {len(self.battery_history['readings'])} readings")
                
        except Exception as e:
            print(f"Error loading data: {e}")
            
    def plot_energy_consumption_overview(self):
        """Create total electricity consumption overview plot."""
        if not self.simulation_output:
            print("No simulation output data available")
            return
            
        # Extract energy data
        timestamps = []
        total_consumption = []
        
        for record in self.simulation_output:
            timestamps.append(datetime.fromisoformat(record['timestamp']))
            energy_data = record['energy_management_sensors']
            total_consumption.append(energy_data['solar_power']['electricity_consumption'])
        
        # Create the total consumption overview plot
        fig, ax = plt.subplots(figsize=(15, 8))
        
        # Set white background
        fig.patch.set_facecolor('white')
        ax.set_facecolor('white')
        
        ax.plot(timestamps, total_consumption, color='red', linewidth=2, label='Total Electricity Consumption')
        ax.set_title('Total Electricity Consumption Over Time', fontsize=16, fontweight='bold')
        ax.set_ylabel('Energy (kWh)', fontsize=12)
        ax.set_xlabel('Time', fontsize=12)
        ax.grid(True, alpha=0.3)
        ax.legend()
        
        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        plt.savefig('total_electricity_consumption.png', dpi=300, bbox_inches='tight')
        plt.show()
        
        # Print summary statistics
        print(f"\n📊 Total Electricity Consumption Summary:")
        print(f"   Total consumption: {sum(total_consumption):.2f} kWh")
        print(f"   Average per hour: {np.mean(total_consumption):.3f} kWh")
        print(f"   Peak consumption: {max(total_consumption):.3f} kWh")
        
    def plot_solar_generation(self):
        """Create solar panel generation overview plot."""
        if not self.simulation_output:
            print("No simulation output data available")
            return
            
        # Extract solar generation data
        timestamps = []
        solar_production = []
        
        for record in self.simulation_output:
            timestamps.append(datetime.fromisoformat(record['timestamp']))
            energy_data = record['energy_management_sensors']
            solar_production.append(energy_data['solar_power']['production'])
        
        # Create the solar generation plot
        fig, ax = plt.subplots(figsize=(15, 8))
        
        ax.plot(timestamps, solar_production, color='orange', linewidth=2, label='Solar Panel Generation')
        ax.fill_between(timestamps, solar_production, alpha=0.3, color='orange')
        ax.set_title('Solar Panel Generation Over Time', fontsize=16, fontweight='bold')
        ax.set_ylabel('Energy Production (kWh)', fontsize=12)
        ax.set_xlabel('Time', fontsize=12)
        ax.grid(True, alpha=0.3)
        ax.legend()
        
        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        plt.savefig('solar_panel_generation.png', dpi=300, bbox_inches='tight')
        plt.show()
        
        # Print summary statistics
        print(f"\n☀️ Solar Panel Generation Summary:")
        print(f"   Total generation: {sum(solar_production):.2f} kWh")
        print(f"   Average per hour: {np.mean(solar_production):.3f} kWh")
        print(f"   Peak generation: {max(solar_production):.3f} kWh")
        print(f"   Hours with generation: {sum(1 for x in solar_production if x > 0)} hours")
        
    def plot_daily_consumption_matrix(self):
        """Create daily consumption breakdown in matrix format."""
        if not self.simulation_output:
            print("No simulation output data available")
            return
            
        # Extract energy data
        timestamps = []
        total_consumption = []
        
        for record in self.simulation_output:
            timestamps.append(datetime.fromisoformat(record['timestamp']))
            energy_data = record['energy_management_sensors']
            total_consumption.append(energy_data['solar_power']['electricity_consumption'])
        
        # Convert to pandas DataFrame for easier handling
        df = pd.DataFrame({
            'timestamp': timestamps,
            'consumption': total_consumption
        })
        df['date'] = df['timestamp'].dt.date
        
        # Get unique days
        unique_days = sorted(df['date'].unique())
        n_days = len(unique_days)
        
        # Calculate grid dimensions for matrix layout
        n_cols = min(4, n_days)  # Max 4 columns
        n_rows = (n_days + n_cols - 1) // n_cols  # Ceiling division
        
        # Create the daily matrix plot
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4 * n_rows))
        
        # Ensure axes is always 2D array
        if n_rows == 1:
            axes = axes.reshape(1, -1)
        elif n_cols == 1:
            axes = axes.reshape(-1, 1)
        
        # Create daily plots in matrix
        for i, day in enumerate(unique_days):
            row = i // n_cols
            col = i % n_cols
            
            # Filter data for this day
            day_data = df[df['date'] == day].copy()
            day_data['hour'] = day_data['timestamp'].dt.hour + day_data['timestamp'].dt.minute / 60
            
            # Create subplot
            ax = axes[row, col]
            ax.plot(day_data['hour'], day_data['consumption'], color='blue', linewidth=1.5, alpha=0.8)
            ax.set_title(f'{day.strftime("%Y-%m-%d")}', fontsize=12, fontweight='bold')
            ax.set_ylabel('kWh', fontsize=10)
            ax.set_xlabel('Hour of Day', fontsize=10)
            ax.grid(True, alpha=0.3)
            ax.set_xlim(0, 24)
            
            # Set x-ticks for hours
            ax.set_xticks([0, 6, 12, 18, 24])
            ax.tick_params(axis='both', which='major', labelsize=9)
            
            # Add daily statistics
            daily_total = day_data['consumption'].sum()
            daily_avg = day_data['consumption'].mean()
            daily_max = day_data['consumption'].max()
            
            # Add text box with stats
            stats_text = f'Total: {daily_total:.2f} kWh\nAvg: {daily_avg:.3f} kWh\nMax: {daily_max:.3f} kWh'
            ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, fontsize=8,
                   verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        # Remove empty subplots if any
        for i in range(n_days, n_rows * n_cols):
            row = i // n_cols
            col = i % n_cols
            axes[row, col].remove()
        
        plt.suptitle('Daily Electricity Consumption Breakdown', fontsize=16, fontweight='bold')
        plt.tight_layout()
        plt.savefig('daily_consumption_matrix.png', dpi=300, bbox_inches='tight')
        plt.show()
        
        # Print daily summary statistics
        daily_totals = df.groupby('date')['consumption'].sum()
        print(f"\n📊 Daily Consumption Summary:")
        print(f"   Days analyzed: {n_days}")
        print(f"   Average per day: {daily_totals.mean():.2f} kWh")
        print(f"   Highest day: {daily_totals.max():.2f} kWh on {daily_totals.idxmax()}")
        print(f"   Lowest day: {daily_totals.min():.2f} kWh on {daily_totals.idxmin()}")
        
    def plot_battery_performance(self):
        """Plot battery performance metrics."""
        if not self.battery_history:
            print("No battery history data available")
            return
            
        readings = self.battery_history['readings']
        
        timestamps = [datetime.fromisoformat(r['timestamp']) for r in readings]
        charge_levels = [r['charge_level_kwh'] for r in readings]
        state_of_charge = [r['state_charge'] for r in readings]
        health_status = [r['health_status'] for r in readings]
        cycles = [r['cycles'] for r in readings]
        
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 10))
        
        # Battery charge level
        ax1.plot(timestamps, charge_levels, color='blue', linewidth=2)
        ax1.set_title('Battery Charge Level Over Time', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Charge Level (kWh)', fontsize=12)
        ax1.grid(True, alpha=0.3)
        
        # State of charge percentage
        ax2.plot(timestamps, state_of_charge, color='green', linewidth=2)
        ax2.set_title('Battery State of Charge (%)', fontsize=14, fontweight='bold')
        ax2.set_ylabel('State of Charge (%)', fontsize=12)
        ax2.grid(True, alpha=0.3)
        
        # Battery health
        ax3.plot(timestamps, health_status, color='orange', linewidth=2)
        ax3.set_title('Battery Health Status', fontsize=14, fontweight='bold')
        ax3.set_ylabel('Health (%)', fontsize=12)
        ax3.grid(True, alpha=0.3)
        
        # Battery cycles
        ax4.plot(timestamps, cycles, color='red', linewidth=2)
        ax4.set_title('Battery Cycles', fontsize=14, fontweight='bold')
        ax4.set_ylabel('Cycles', fontsize=12)
        ax4.grid(True, alpha=0.3)
        
        # Format x-axis for all subplots
        for ax in [ax1, ax2, ax3, ax4]:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        plt.savefig('battery_performance.png', dpi=300, bbox_inches='tight')
        plt.show()
        
    def plot_device_consumption(self):
        """Plot individual device consumption patterns."""
        if not self.simulation_output:
            print("No simulation output data available")
            return
            
        # Collect device consumption data
        device_data = {}
        timestamps = []
        
        for record in self.simulation_output:
            timestamp = datetime.fromisoformat(record['timestamp'])
            timestamps.append(timestamp)
            
            device_consumption = record['energy_management_sensors']['energy_efficiency']['device_consumption']
            
            for device, consumption in device_consumption.items():
                if device not in device_data:
                    device_data[device] = []
                device_data[device].append(consumption)
        
        # Create stacked area plot
        fig, ax = plt.subplots(figsize=(15, 8))
        
        # Prepare data for stacked plot
        devices = list(device_data.keys())
        values = np.array([device_data[device] for device in devices])
        
        # Create stacked area plot
        ax.stackplot(timestamps, *values, labels=devices, alpha=0.7)
        
        ax.set_title('Device Energy Consumption Over Time (Stacked)', fontsize=14, fontweight='bold')
        ax.set_ylabel('Energy Consumption (kWh)', fontsize=12)
        ax.set_xlabel('Time', fontsize=12)
        ax.grid(True, alpha=0.3)
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        
        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        plt.savefig('device_consumption.png', dpi=300, bbox_inches='tight')
        plt.show()
        
    def plot_water_consumption(self):
        """Plot water consumption data if available."""
        if not self.user_data or 'actions' not in self.user_data:
            print("No water consumption data available")
            return
            
        # Extract water usage from actions
        water_usage = []
        timestamps = []
        
        start_date = datetime.fromisoformat(self.user_data['start_date'])
        current_time = start_date
        
        for action in self.user_data['actions']:
            if 'water_used' in action:
                water_usage.append(action['water_used'])
                timestamps.append(current_time)
                current_time += timedelta(seconds=action.get('duration', 300))
        
        if not water_usage:
            print("No water usage data found in actions")
            return
            
        # Create cumulative water usage plot
        cumulative_water = np.cumsum(water_usage)
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))
        
        # Instantaneous water usage
        ax1.plot(timestamps, water_usage, color='blue', linewidth=1, alpha=0.7)
        ax1.set_title('Instantaneous Water Usage', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Water Usage (L)', fontsize=12)
        ax1.grid(True, alpha=0.3)
        
        # Cumulative water usage
        ax2.plot(timestamps, cumulative_water, color='green', linewidth=2)
        ax2.set_title('Cumulative Water Usage', fontsize=14, fontweight='bold')
        ax2.set_ylabel('Cumulative Water Usage (L)', fontsize=12)
        ax2.set_xlabel('Time', fontsize=12)
        ax2.grid(True, alpha=0.3)
        
        # Format x-axis
        for ax in [ax1, ax2]:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        plt.savefig('water_consumption.png', dpi=300, bbox_inches='tight')
        plt.show()
        
    def plot_weekly_consumption_pattern(self):
        """Create a bar chart showing average daily kWh consumption for each day of the week."""
        if not self.simulation_output:
            print("No simulation output data available")
            return
            
        # Extract energy data with day of week
        timestamps = []
        total_consumption = []
        
        for record in self.simulation_output:
            timestamps.append(datetime.fromisoformat(record['timestamp']))
            energy_data = record['energy_management_sensors']
            total_consumption.append(energy_data['solar_power']['electricity_consumption'])
        
        # Convert to pandas DataFrame for easier handling
        df = pd.DataFrame({
            'timestamp': timestamps,
            'consumption': total_consumption
        })
        
        # Add day of week information
        df['day_of_week'] = df['timestamp'].dt.day_name()
        df['day_number'] = df['timestamp'].dt.dayofweek  # 0=Monday, 6=Sunday
        df['date'] = df['timestamp'].dt.date
        
        # Calculate daily totals first
        daily_totals = df.groupby(['date', 'day_of_week', 'day_number'])['consumption'].sum().reset_index()
        
        # Calculate average consumption for each day of the week
        weekly_averages = daily_totals.groupby(['day_of_week', 'day_number'])['consumption'].mean().reset_index()
        
        # Sort by day number to get proper weekday order (Monday to Sunday)
        weekly_averages = weekly_averages.sort_values('day_number')
        
        # Create the weekly pattern bar chart
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # Set white background
        fig.patch.set_facecolor('white')
        ax.set_facecolor('white')
        
        # Define colors for each day
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2']
        
        bars = ax.bar(weekly_averages['day_of_week'], weekly_averages['consumption'], 
                     color=colors, alpha=0.8, edgecolor='black', linewidth=1)
        
        ax.set_title('Daily Energy Consumption by Day of Week', fontsize=16, fontweight='bold')
        ax.set_ylabel('Daily Consumption (kWh)', fontsize=12)
        ax.set_xlabel('Day of Week', fontsize=12)
        ax.grid(True, alpha=0.3, axis='y')
        
        # Add value labels on top of bars
        for bar, value in zip(bars, weekly_averages['consumption']):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + height*0.01,
                   f'{value:.2f}', ha='center', va='bottom', fontsize=11, fontweight='bold')
        
        # Rotate x-axis labels for better readability
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        plt.tight_layout()
        plt.savefig('weekly_consumption_pattern.png', dpi=300, bbox_inches='tight')
        plt.show()
        
        # Print weekly summary statistics
        print(f"\n📅 Weekly Consumption Pattern Summary:")
        print(f"   Days analyzed: {len(daily_totals)} total days")
        for _, row in weekly_averages.iterrows():
            day_count = len(daily_totals[daily_totals['day_of_week'] == row['day_of_week']])
            print(f"   {row['day_of_week']}: {row['consumption']:.2f} kWh average ({day_count} days)")
        
        # Find highest and lowest consumption days
        max_day = weekly_averages.loc[weekly_averages['consumption'].idxmax()]
        min_day = weekly_averages.loc[weekly_averages['consumption'].idxmin()]
        print(f"   Highest consumption: {max_day['day_of_week']} ({max_day['consumption']:.2f} kWh)")
        print(f"   Lowest consumption: {min_day['day_of_week']} ({min_day['consumption']:.2f} kWh)")
        
    def plot_consumption_summary(self):
        """Create a summary dashboard with key metrics."""
        if not self.user_data:
            print("No user data available for summary")
            return
            
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 10))
        
        # Summary statistics
        total_energy = self.user_data.get('total_energy_used', 0)
        total_water = self.user_data.get('total_water_used', 0)
        total_time_hours = self.user_data.get('total_time', 0) / 3600
        house_name = self.user_data.get('house_name', 'Smart House')
        
        # Energy usage gauge
        ax1.pie([total_energy, 200 - total_energy], labels=['Used', 'Remaining'], 
                startangle=90, colors=['#ff7f7f', '#e0e0e0'])
        ax1.set_title(f'Total Energy Usage\n{total_energy:.2f} kWh', fontsize=14, fontweight='bold')
        
        # Water usage gauge
        ax2.pie([total_water, 3000 - total_water], labels=['Used', 'Remaining'], 
                startangle=90, colors=['#7f7fff', '#e0e0e0'])
        ax2.set_title(f'Total Water Usage\n{total_water:.2f} L', fontsize=14, fontweight='bold')
        
        # Simulation duration
        simulation_days = total_time_hours / 24
        ax3.bar(['Simulation Duration'], [simulation_days], color='green', alpha=0.7)
        ax3.set_title('Simulation Duration', fontsize=14, fontweight='bold')
        ax3.set_ylabel('Days', fontsize=12)
        
        # Summary text
        ax4.text(0.1, 0.8, f"House: {house_name}", fontsize=14, fontweight='bold')
        ax4.text(0.1, 0.6, f"Simulation Type: {self.user_data.get('type_of_simulation', 'N/A')}", fontsize=12)
        ax4.text(0.1, 0.4, f"Period: {self.user_data.get('start_date', 'N/A')} to {self.user_data.get('end_date', 'N/A')}", fontsize=12)
        ax4.text(0.1, 0.2, f"Energy Efficiency: {total_energy/simulation_days:.2f} kWh/day", fontsize=12)
        ax4.text(0.1, 0.0, f"Water Efficiency: {total_water/simulation_days:.2f} L/day", fontsize=12)
        ax4.set_xlim(0, 1)
        ax4.set_ylim(0, 1)
        ax4.axis('off')
        ax4.set_title('Summary Statistics', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        plt.savefig('consumption_summary.png', dpi=300, bbox_inches='tight')
        plt.show()
        
    def generate_all_plots(self):
        """Generate all available plots."""
        print("Generating all consumption analysis plots...")
        print("=" * 50)
        
        self.plot_consumption_summary()
        self.plot_energy_consumption_overview()
        self.plot_solar_generation()
        self.plot_daily_consumption_matrix()
        self.plot_weekly_consumption_pattern()
        self.plot_battery_performance()
        self.plot_device_consumption()
        self.plot_water_consumption()
        
        print("=" * 50)
        print("All plots generated successfully!")
        print("Saved files:")
        print("- consumption_summary.png")
        print("- total_electricity_consumption.png")
        print("- solar_panel_generation.png")
        print("- daily_consumption_matrix.png")
        print("- weekly_consumption_pattern.png")
        print("- battery_performance.png")
        print("- device_consumption.png")
        print("- water_consumption.png")

def main():
    """Main function to run the consumption analysis."""
    parser = argparse.ArgumentParser(description='MPSDS Consumption Analysis Tool')
    parser.add_argument('--data-dir', default='./', help='Directory containing data files')
    parser.add_argument('--plot', choices=['summary', 'energy', 'solar', 'daily', 'weekly', 'battery', 'devices', 'water', 'all'], 
                       default='all', help='Type of plot to generate')
    
    args = parser.parse_args()
    
    # Create analyzer instance
    analyzer = MPSDSAnalyzer(args.data_dir)
    
    # Load data
    print("Loading MPSDS consumption data...")
    analyzer.load_data()
    
    # Generate requested plots
    if args.plot == 'all':
        analyzer.generate_all_plots()
    elif args.plot == 'summary':
        analyzer.plot_consumption_summary()
    elif args.plot == 'energy':
        analyzer.plot_energy_consumption_overview()
    elif args.plot == 'solar':
        analyzer.plot_solar_generation()
    elif args.plot == 'daily':
        analyzer.plot_daily_consumption_matrix()
    elif args.plot == 'weekly':
        analyzer.plot_weekly_consumption_pattern()
    elif args.plot == 'battery':
        analyzer.plot_battery_performance()
    elif args.plot == 'devices':
        analyzer.plot_device_consumption()
    elif args.plot == 'water':
        analyzer.plot_water_consumption()

if __name__ == "__main__":
    main()
