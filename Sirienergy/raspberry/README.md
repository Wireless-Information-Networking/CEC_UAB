# System Installation and Telemetry Guide

1. The initial phase involves obtaining the Venus OS software. Core installation procedures are available at the primary repository.
[Venus OS Repository](https://github.com/victronenergy/venus)

The selection of a precise disk image matching the Raspberry Pi hardware is necessary. The official wiki provides a guide for identifying the correct version.
[Raspberry Pi Image Selection](https://github.com/victronenergy/venus/wiki/raspberrypi-install-venus-image)

2. The dbus flashmq application works as a fast digital translator for solar power systems. It changes internal machine codes from batteries and inverters into standard internet formats. This process allows for reliable remote monitoring of live power data and lets system managers adjust settings from any location. Full operational details are found in the official documentation.
[Dbus Flashmq Documentation](https://github.com/victronenergy/dbus-flashmq/blob/master/README.md)

3. Activating the data stream requires connecting the local MQTT client to the SiriEnergy server. Assigning the broker address to 158.109.75.3 and specifying port 1883 allows telemetry to move directly into the cloud backend. This successful link enables the display of live energy metrics on the web dashboard for remote observation.

4. Identifying active data channels is possible through the read_data.py script located in the project branch. This utility displays all MQTT topics currently broadcast by the hardware. Expanding the system to track more variables requires modifying the app.py file within the same branch. Adding new subscription paths to this backend script enables the service to listen for and process additional telemetry streams.

5. The presentation layer allows for the addition of new informational windows. Editing the script at /OPEN4CEC/Sirienergy/sirienergy/static/js/app.js enables the creation of these visual components. Defining new display logic and UI containers within this file ensures that the added telemetry variables become visible on the web dashboard.
