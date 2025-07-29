# MPSDS Docker Setup

This repository now includes Docker support for easy deployment and execution of the MPSDS (Multi-Purpose Smart Data Simulator) system.

## Quick Start with Docker

### Prerequisites
- Docker installed on your system
- A configuration JSON file (you can use `config_default.json` as a template)

### Option 1: Using the provided script (Recommended)

1. **Build and run with the convenience script:**
```bash
./run_simulation.sh /path/to/your/config.json /path/to/output/directory
```

Example:
```bash
./run_simulation.sh ./config_default.json ./my_results
```

### Option 2: Manual Docker commands

1. **Build the Docker image:**
```bash
docker build -t mpsds-simulator .
```

2. **Run the simulation:**
```bash
docker run --rm \
  -v /host/path/to/config/directory:/config:ro \
  -v /host/path/to/output:/output \
  mpsds-simulator \
  /config/your_config.json \
  /output
```

Example:
```bash
docker run --rm \
  -v $(pwd):/config:ro \
  -v $(pwd)/results:/output \
  mpsds-simulator \
  /config/config_default.json \
  /output
```

## Directory Structure

The Docker container expects:
- **Config file**: Mounted to `/config` directory (read-only)
- **Output directory**: Mounted to `/output` directory (read-write)

## Command Syntax

The updated `puppeteer.py` now accepts command-line arguments:

```bash
python puppeteer.py <config_file_path> <output_directory_path>
```

Where:
- `<config_file_path>`: Path to your configuration JSON file
- `<output_directory_path>`: Directory where results will be saved

## Output Files

The simulation will generate several output files in your specified output directory:
- `user_data.json`: Detailed simulation data
- `<house_id>_output.json`: Main simulation results
- Various analysis plots and charts (PNG files)

## Configuration File

Make sure your configuration JSON file includes all required parameters. You can use `config_default.json` as a template and modify it according to your needs.

## Examples

### Example 1: Using default config
```bash
./run_simulation.sh ./config_default.json ./my_simulation_results
```

### Example 2: Using custom config from different directory
```bash
./run_simulation.sh /home/user/configs/custom_config.json /home/user/results/run_001
```

### Example 3: Manual Docker command with current directory
```bash
docker build -t mpsds-simulator .
docker run --rm \
  -v $(pwd):/config:ro \
  -v $(pwd)/docker_results:/output \
  mpsds-simulator \
  /config/config_default.json \
  /output
```

## Troubleshooting

1. **Permission Issues**: Make sure the output directory is writable by the Docker container
2. **Config File Not Found**: Ensure the config file path is correct and the file exists
3. **Build Failures**: Check that all dependencies in `requirements.txt` are available

## Notes

- The Docker container runs with Python 3.12
- All Python dependencies are automatically installed during the Docker build
- The simulation results will be owned by the user running Docker
- The container automatically creates the output directory if it doesn't exist
