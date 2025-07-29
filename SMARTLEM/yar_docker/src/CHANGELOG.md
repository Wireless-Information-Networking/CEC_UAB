# Change Log
All notable changes to this project will be documented in this file.
 
 
## 2025-01-20
 
### Added
- A ```CHANGELOG.md```
- Output of the algorithm example
- ```.env``` for api keys
- ```.gitignore```
- Water devices to ```config.json```
- New variables in the algorithm like area of each panel, number of panels and devices

### Changed
  
- Now all the solar generation is inside one unique file inside the solar path
- Updated the ```scheme.png```
- Updated the ```README```
- Updated the ```config.json```
- Now solar irradiance is messured live via the Solcast API (Carefull with the limits)
 
### Fixed
._.
 
### Deleted
- Some of the solar files, because now everything is just in one file

### For next day
Follow the scheme to create the room and device simulations. This is to calculate the total consumption, and this will help with the grid consumption as well  

## 2025-01-21
 
### Added
- NPC test folder
- ```npc.py``` for simulating room usage
- ```NPC diagram.png``` to clearly show algorithm
### Changed
  
- Person to 1 in ```config.json```

### Fixed
._.
 
### Deleted

### For next day
Continue with the npc test, add flags to it, connect with devices for device usage and plann how to do total consumption.

Add random activities for idle NPC

- [x] Add to much energy: Go for a jog, Go to the gym
- [x] Add to much fun: Meditate


## 2025-02-20
 
### Added
- To much energy actions
- To much fun actions
- Instead of being idle, it does something
- Bars in the graph for when it ends
### Changed

- Just added the bars in the graph for when it ends

### Fixed
._.
 
### Deleted

### For next day

- [x] Integrate house variables
- [x] Test NPC
- [x] Start testing how it interacts with objects

## 2025-03-5
 
### Added
- ```npc.py``` to home 
- ```electric_devices``` to ```config.json```
- ```House``` class to accept the config parameters

### Changed

- how ```temperature_humidity_airquality.py``` returns the info
- ```config.json``` to add room to devices
- ```npc.py``` to integrate room devices and the NPC now takes decision based on temperature

### Fixed
._.
 
### Deleted

### For next day

- [x] Test NPC in Raspberry Pie
- [x] Change method of saving data (json formatt)
- [x] Make it so that every delta it saves the data


## 2025-03-11
 
### Added
- Functions to create json and add action to json. Now the actions are added and can be consulted IRT
- Divided better the NPC configuration
- Two new variables ```update_each_seconds``` (bool) and ```actions_in_minutes``` to control if I want to generate actions each X amount of minutes or seconds
- ```add_action_to_json()``` adds the action to the action json every time an action finishes
- ```create_json_reg()``` to initialize the JSON file if it does not already exist


### Changed

- Added ```timezone``` and ```os```
- ```actions_in_minutes``` is a conditional that tells you if it should use minutes or seconds. 

### Fixed
._.
 
### Deleted
- All the ```*60``` since now that is controlled by ```actions_in_minutes```

### For next day
- [x] Add schedules (sleep at night, work...)


## 2025-03-12
 
### Added
- ```out_of_house_period``` in ```config.json``` to configure when the person is out of the house or not
- ```is_out_of_home()``` function that checks if the NPC is inside or outside the house. Right now it depends on the ```npc.time```, that artificially increases the time to advance in time and see how it reacts. In a future, an option of ```real time``` or ```simulation_time_period``` will be added to the ```config.json``` file.

- ```self.is_out_of_home()``` in ```decide_next_action()```

- ```type_of_simulation``` parameter in ```config.json```, which configures the ```type```, if its ```fast_foward``` or ```real_time```
- ```print_message``` in ```add_action_to_json()``` to show if the print action will be displayed in terminal o no
- A bar to show progress in ```real_time``` 

### Changed

- The main simulation loop because now we have to discriminate between ```real_time``` and ```fast_foward```

### Fixed
._.
 
### Deleted
._.

### For next day
- [x] Add distinction between kid or adult
- [x] Validate for more than one NPC (one kid and one adult for example)
- [ ] Connect to MQTT (local or no local) or not


## 2025-03-12
 
### Added

- ```npc``` sub group in the ```config.json``` with ```name``` and ```age_group```
- ```allowed_age_group``` to the ```Action``` class, so now the actions are white listed by age group 
- ```age_group``` to the NPC class to caracterize the age of the NPC
- Check in ```perform_action``` if the age is allowed for the action

### Changed

- The ```npcAnalysis.py``` to adapt to this new changes.

### Fixed
 
### Deleted

### For next day


## 2025-03-21

The upload of today includes the age adjustment, the adjust for multiple npcs, the creation of ```puppeteer.py``` and its completion, the creation of 
```unit_testing.py```, the upload of the testing folder, changed some names, a result example, modified the ```npcAnalysis``` and the ```sensor_data_rpi1.json``` so that it uncludes what I can have. Also added remote connection to the ```config.json``` thing and found a new way to ger irrandiance using ```pvlib```. 

### For next day

Test if the puppeteer.py works, the unit tests are passed but i have my doubts. Also, if it fails, which it will, you have to make it so that the clock is an external thing instead of a module dependent thing, because its horrible to sync 6 blocs. 
