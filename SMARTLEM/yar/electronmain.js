const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs').promises;
const { exec } = require('child_process');

let win; // Form window
let dashboardWin; // Dashboard window

function createWindow() {
  win = new BrowserWindow({
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  win.loadFile('public/index.html');
  win.setMenuBarVisibility(false);
  win.setAutoHideMenuBar(true);
  win.maximize();
  //win.webContents.openDevTools(); // Optional: Remove in production
}

function createDashboardWindow(simulationData, houseID) {
  dashboardWin = new BrowserWindow({
    width: 1400,
    height: 900,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  dashboardWin.loadFile('public/dashboard.html');
  dashboardWin.setMenuBarVisibility(false);
  dashboardWin.setAutoHideMenuBar(true);
  dashboardWin.maximize();
  //dashboardWin.webContents.openDevTools(); // Optional: Remove in production

  // Send simulation data to the dashboard window once it's ready
  dashboardWin.webContents.on('did-finish-load', () => {
    dashboardWin.webContents.send('simulation-data', { simulationData, houseID });
  });

  // Close the dashboard window when the app is closed
  dashboardWin.on('closed', () => {
    dashboardWin = null;
  });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

// Handle saving the config file
ipcMain.handle('save-config', async (event, configData) => {
  try {
    // Generate config file name from house name
    const houseName = (configData.basic_parameters.name || 'config').trim();
    const fileName = houseName.toLowerCase().replace(/\s+/g, '_') + '.json';
    const saveDir = path.join(__dirname, 'config_files');
    await fs.mkdir(saveDir, { recursive: true });
    const configFilePath = path.join(saveDir, fileName);
    await fs.writeFile(configFilePath, JSON.stringify(configData, null, 4), 'utf8');
    console.log('Config file saved at:', configFilePath);

    // Path to the venv's Python interpreter (adjust this to your venv path)
    const venvPython = path.join(__dirname, '.venv', 'bin', 'python3'); // For Unix-like systems
    // For Windows, use: path.join(__dirname, '.venv', 'Scripts', 'python.exe')
    const scriptPath = path.join(__dirname, 'mpsds_generate_simulation', 'puppeteer.py');
    const command = `${venvPython} "${scriptPath}" "${fileName}"`;

    // Run the Python script
    exec(command, (error, stdout, stderr) => {
      if (error) {
        console.error('Error running simulation:', error);
        win.webContents.send('simulation-error', error.message);
        return;
      }
      console.log('Simulation output:', stdout);
      if (stderr) console.error('Simulation stderr:', stderr);

      // Check for the specific output file with a polling mechanism
      const outputDir = path.join(__dirname, 'sim_result');
      const outputFile = path.join(outputDir, `${houseName.toLowerCase().replace(/\s+/g, '_')}_output.json`);
      const maxRetries = 30; // Maximum number of retries
      const interval = 1000; // Check every 1 second
      let attempts = 0;

      const checkFileExists = setInterval(() => {
        fs.access(outputFile, fs.constants.F_OK)
          .then(async () => {
            clearInterval(checkFileExists);
            console.log('Output file found:', outputFile);
            // Read the output file and open the dashboard
            try {
              const data = await fs.readFile(outputFile, 'utf-8');
              const parsedData = JSON.parse(data);
              win.webContents.send('simulation-complete', { filePath: outputFile, data: parsedData, houseID: houseName });
              // Open the dashboard window
              createDashboardWindow(parsedData, houseName);
              // Optionally close the form window
              win.close();
            } catch (err) {
              console.error('Error reading output file:', err);
              win.webContents.send('simulation-error', 'Failed to read output file');
            }
          })
          .catch(() => {
            attempts++;
            if (attempts >= maxRetries) {
              clearInterval(checkFileExists);
              console.error('Output file not found after waiting:', outputFile);
              win.webContents.send('simulation-error', 'Output file not found after waiting');
            }
          });
      }, interval);
    });

    return { success: true, configFilePath };
  } catch (err) {
    console.error('Error in save-config:', err);
    return { success: false, error: err.message };
  }
});

ipcMain.on('run-default-simulation', (event) => {
  const venvPython = path.join(__dirname, '.venv', 'bin', 'python3'); // Adjust for Windows if needed (e.g., 'Scripts\\python.exe')
  const scriptPath = path.join(__dirname, 'mpsds_generate_simulation', 'puppeteer.py');
  const command = `${venvPython} "${scriptPath}"`; // No config file argument

  exec(command, (error, stdout, stderr) => {
    if (error) {
      console.error('Error running default simulation:', error);
      win.webContents.send('simulation-error', error.message);
      return;
    }
    console.log('Default simulation output:', stdout);
    if (stderr) console.error('Default simulation stderr:', stderr);

    const outputFile = path.join(__dirname, 'sim_result', "john_doe's_smart_house_output.json");
    fs.access(outputFile, fs.constants.F_OK)
      .then(async () => {
        console.log('Default output file found:', outputFile);
        try {
          const data = await fs.readFile(outputFile, 'utf-8');
          const parsedData = JSON.parse(data);
          win.webContents.send('simulation-complete', { filePath: outputFile, data: parsedData, houseID: "john_doe's_smart_house" });
          // Open the dashboard window
          createDashboardWindow(parsedData, "john_doe's_smart_house");
          // Optionally close the form window
          win.close();
        } catch (err) {
          console.error('Error reading default output file:', err);
          win.webContents.send('simulation-error', 'Failed to read default output file');
        }
      })
      .catch(() => {
        console.error('Default output file not found:', outputFile);
        win.webContents.send('simulation-error', 'Default output file not found');
      });
  });
});

// New IPC handler to load simulation data (if needed separately)
ipcMain.handle('load-sim-data', async (event, houseID) => {
  try {
    const filePath = path.join(__dirname, 'sim_result', `${houseID}_output.json`);
    const data = await fs.readFile(filePath, 'utf-8');
    return JSON.parse(data);
  } catch (error) {
    console.error('Error reading simulation data:', error);
    return [];
  }
});