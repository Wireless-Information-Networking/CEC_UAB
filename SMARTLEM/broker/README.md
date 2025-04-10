# MQTT Admin Panel

This project is an Electron-based application designed to manage and monitor an MQTT broker. It provides a user-friendly interface for administrators to control the broker, manage connected clients, and view system information.

## Features

- **Broker Management**:
  - Start, stop, and restart the MQTT broker.
  - View the current status of the broker (online/offline).
  
- **Client Management**:
  - View connected clients and their metadata.
  - Add clients to a whitelist for authentication.
  - Disconnect or remove clients from the broker.

- **System Information**:
  - Display host IP address, gateway, and operating system details.

- **Logging**:
  - Color-coded logs for API, success, warning, error, and server messages.

- **Integration**:
  - Send production and consumption data to external APIs.
  - Manage client metadata and whitelist.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-repo/mqtt-admin-panel.git
   cd mqtt-admin-panel
    ```

2. Install dependencies
```bash
npm install
```

3. Start the application:
```bash
npm start
```

## File Structure
- ```eleconfig.js```: Main Electron process file. Handles broker management, IPC communication, and MQTT logic.
- ```preload.js```: Preload script for exposing secure APIs to the renderer process.
- ```index.html```: Main dashboard interface for managing clients and broker status.
- ```settings_index.html```: Settings page for broker configuration and system information.
- ```tmessage.js```: Utility for color-coded logging in the console.
- ```whitelist.json```: Stores whitelisted client IDs.
- ```connected.json```: Tracks currently connected clients.

## Known Issues
- Ensure Docker is installed and running on the host machine for broker management.
- The application assumes the broker container is named ```emqx```.
