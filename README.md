# CEC_UAB

Energy software solutions for Citizen Energy Communities (CECs), developed by the Universitat Autònoma de Barcelona.

## Sirienergy

Sirienergy is a web application designed to provide users with insights into their energy consumption, production, and other related metrics. This repository contains the server-side code for the Sirienergy application.

## SMART-LEM

### Yar
Yar is an open-source Electron application dedicated to designing, simulating, and visualizing self-sustainable smart houses

#### Overview
The Yar Smart House Simulator is a desktop application designed to simulate and monitor a smart home environment. It generates real-time data for energy management, water usage, and climate conditions, presenting this data through an interactive dashboard. The application is built using Electron for the frontend (with a web-based dashboard) and Python for the backend simulation logic. The dashboard provides insights into metrics like energy consumption, solar production, battery status, water usage, and climate conditions, with options to filter data by time range and export the dashboard in multiple formats.

### Broker

The Broker Panel is an Electron-based application designed to manage and monitor an MQTT broker. It provides a user-friendly interface for administrators to control the broker, manage connected clients, and view system information. Key features include broker management, client management, system information display, and integration with Sirienergy.

### Connection
The Yar simulator is designed to interoperate seamlessly with Sirienergy through a RESTful API. This integration allows Yar to send real-time or batch simulation data—such as energy consumption, solar production, and battery usage—directly to the Sirienergy backend, where it can be stored, visualized, and analyzed.

This connection enables users to:
- Aggregate and analyze simulated data alongside real consumption data.

- Test different self-sustainability strategies within the Sirienergy environment.

- Export simulation results to the Sirienergy dashboard for unified reporting.

To enable this connection, Yar must be configured with the appropriate API endpoint and authentication credentials. This is done through the graphical interface of the simulator, where users must specify their Sirienergy login credentials. Once logged in, Yar will handle the authentication and secure communication with the Sirienergy API automatically.

Additionally, in the ```YAR``` repository, two Python files named ```create_client.py``` and ```siri_send_data.py```  provides a clear example of how to interact programmatically with the Sirienergy API. This files serve both as a reference for developers and as a potential integration point for advanced users who want to automate or customize data exchange processes beyond the default behavior.
