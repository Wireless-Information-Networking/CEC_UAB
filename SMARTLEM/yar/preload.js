const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  saveConfig: (data) => ipcRenderer.invoke('save-config', data),
  runDefaultSimulation: () => ipcRenderer.send('run-default-simulation'),
  loadSimData: (houseID) => ipcRenderer.invoke('load-sim-data', houseID),
  onSimulationComplete: (callback) => ipcRenderer.on('simulation-complete', (event, data) => callback(data)),
  onSimulationError: (callback) => ipcRenderer.on('simulation-error', (event, error) => callback(error)),
  onSimulationData: (callback) => ipcRenderer.on('simulation-data', (event, data) => callback(data))
});