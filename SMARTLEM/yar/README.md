# yar
Yar is an open-source Electron application dedicated to designing, simulating, and visualizing self-sustainable smart houses

## Overview

The Yar Smart House Simulator is a desktop application designed to simulate and monitor a smart home environment. It generates real-time data for energy management, water usage, and climate conditions, presenting this data through an interactive dashboard. The application is built using Electron for the frontend (with a web-based dashboard) and Python for the backend simulation logic. The dashboard provides insights into metrics like energy consumption, solar production, battery status, water usage, and climate conditions, with options to filter data by time range and export the dashboard in multiple formats.

### Purpose
The simulator aims to:
- Simulate realistic smart home data for testing and demonstration purposes.

- Provide a user-friendly dashboard to visualize key metrics.

- Allow users to export dashboard data for reporting or analysis.


### Technologies used
- **Electron:** For creating a cross-platform desktop application.

- **Python:** For simulating smart home data (via a script like puppeteer.py).

- **HTML/CSS/JavaScript:** For the dashboard UI, using Materialize CSS for styling and Chart.js for data visualization.

- **html2pdf.js:** For exporting the dashboard as a PDF.

- **Node.js:** For managing frontend dependencies (e.g., Chart.js, Materialize CSS).

- **MPSDS:** Custom algorithm used to simulate and predict energy consumption and production patterns in smart homes.

### Project structure

```
yar/
├─ config_files/
├─ mpsds_generate_simulation/
│  ├─ __pycache__/
│  │  ├─ npc.cpython-312.pyc
│  │  └─ puppeteer.cpython-312.pyc
│  ├─ battery_module/
│  │  ├─ __pycache__/
│  │  │  └─ battery_sim.cpython-312.pyc
│  │  └─ battery_sim.py
│  ├─ climateEnviroment/
│  │  ├─ __pycache__/
│  │  │  └─ temperature_humidty_airquality.cpython-312.pyc
│  │  └─ temperature_humidty_airquality.py
│  ├─ energy efficiency/
│  │  ├─ devices_sim.py
│  │  └─ loads.py
│  ├─ pollution/
│  │  ├─ co2levels.py
│  │  └─ sound.py
│  ├─ solar_module/
│  │  ├─ __pycache__/
│  │  │  └─ solar_irradiance.cpython-312.pyc
│  │  └─ solar_irradiance.py
│  ├─ testing_folder/
│  │  └─ get_solar_irradiance_better.py
│  ├─ water/
│  │  ├─ plot.py
│  │  ├─ water_config_OG.json
│  │  ├─ water_config.json
│  │  └─ water_sim.py
│  ├─ config_default.json
│  ├─ npc.py
│  ├─ npcAnalysis.py
│  ├─ pupeteer_testing.py
│  ├─ puppeteer.py
│  ├─ requirements.txt
│  ├─ sensor_data_rp1.json
│  └─ unit_testing.py
├─ public/
│  ├─ dashboard.html
│  ├─ gather.js
│  ├─ icon.ico
│  ├─ index.html
│  ├─ script.js
│  └─ styles.css
├─ .gitignore
├─ electronmain.js
├─ package-lock.json
├─ package.json
├─ preload.js
└─ README.md
```

- ```electronmain.js``` Entry point for the Electron app, responsible for creating the main window and handling IPC (Inter-Process Communication) between the frontend and backend.

- ```puppeteer.py```: A Python script that generates simulated smart home data (e.g., energy, water, climate metrics) and saves it as JSON files


### Setup Instructions
## Prerequisites
- ***Node.js (v14 or higher):*** For running Electron and managing frontend dependencies.

- ***Python (v3.8 or higher):*** For running the simulation script.

- ***Git:*** For cloning the repository (optional).

## Installation
- Clone repository
- Create .venv
- Install from ```requierements.txt```
- Install ```npm install```
- Run the app ```npm start```

## Usage
### Running the Simulator
- Start the application using ```npm start```.

- The Electron window opens, displaying the dashboard (dashboard.html).

- The dashboard automatically triggers the simulation by invoking puppeteer.py (via Electron’s IPC).

- Simulated data is generated and stored in the data/ directory as JSON files (e.g., john_doe's_smart_house.json).

- The dashboard loads the data and visualizes it in various sections (overview, charts, etc.).

### Dashboard Features
- Time Range Filter: Select a time range ("Last Day", "Last Month", "Last Year") to filter the displayed data.

- Overview Section: Displays key metrics:
- Average Battery Level (Ah)

- Total Solar Production (kWh)

- Total Grid Consumption (kWh)

- Total House Consumption (kWh)

- Total Water Usage (L)

- Energy Consumption Chart: Plots grid and device consumption (kW) over time.

- Solar Production Chart: Plots solar production (kW) over time.

- Battery Status: Shows the current battery level (percentage) and health status.

- Water Usage Chart: Displays water usage (L) over time as a bar chart.

- Climate Conditions: Shows the latest temperature (°C), humidity (%), and air quality.

### Export Options: Export the dashboard in three formats:
- PDF: Saves the visual dashboard as a PDF file.

- HTML: Saves the dashboard as a static HTML file.

- CSV: Exports the filtered data as a CSV file for analysis.

### Exporting the Dashboard
- Click the "Export" button next to the time range filter.

- Select an export format from the dropdown:
    - Export as PDF: Downloads a PDF file of the dashboard.

    - Export as HTML: Downloads an HTML file with the current dashboard content.

    - Export as CSV: Downloads a CSV file with the filtered data (timestamp, grid consumption, device consumption, etc.).

## TODO List for Future Improvements
The following features and improvements are planned to enhance the Yar Smart House Simulator:

1. Pull Dashboards from History:
    - Implement a feature to store historical simulation data with timestamps.

    - Add a UI component (e.g., a dropdown or calendar) to select and load past dashboards.

    - Store historical data in a structured format (e.g., a database or timestamped JSON files).

2. Add a 3D House Model:
    - Integrate a 3D model of the house using a library like Three.js.

    - Visualize sensor data spatially (e.g., highlight rooms with high energy usage).

    - Allow users to interact with the model (e.g., click on rooms to see detailed metrics).

3. Finish the UI:
    - Enhance the visual design with more polished styling (e.g., custom themes, animations).

    - Add tooltips or modals for detailed data insights (e.g., hover over a chart point to see exact values).

    - Improve responsiveness for different screen sizes.

    - Add a loading spinner or progress bar during simulation and data loading.

4. Improve PDF Export Quality:
    - Explore server-side PDF generation (e.g., using puppeteer in Node.js) for better chart rendering.

    - Alternatively, capture chart images separately and embed them in the PDF.

5. Add Real-Time Updates:
    - Implement a live mode where the dashboard updates in real-time as new simulation data is generated.

    - Use WebSockets or polling to fetch new data from the backend.

6. Database Integration:
    - Replace JSON file storage with a lightweight database (e.g., SQLite) for better data management.

    - Enable querying historical data efficiently.

7. User Authentication:
    - Add user authentication to support multiple users or houses.

    - Allow users to save their preferences (e.g., default time range, export format).

8. Advanced Analytics:
    - Add predictive analytics (e.g., forecast energy usage based on historical data).

    - Include cost calculations (e.g., cost of grid consumption based on electricity rates).

9. Cross-Platform Enhancements:
    - Ensure the app works seamlessly on Windows, macOS, and Linux.

    - Test and optimize for performance on low-spec devices.

10. Documentation and Testing:
    - Expand this documentation with detailed API references and user guides.

    - Add unit tests for both frontend (JavaScript) and backend (Python) components.

    - Include integration tests for the Electron app.



