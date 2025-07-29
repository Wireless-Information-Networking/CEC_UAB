#!/bin/bash

# MPSDS Docker Runner Script
# Usage: ./run_simulation.sh <path_to_config.json> <path_to_output_directory>

set -e

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed or not in PATH"
    exit 1
fi

# Check arguments
if [ $# -ne 2 ]; then
    echo "Usage: $0 <path_to_config.json> <path_to_output_directory>"
    echo "Example: $0 /home/user/myconfig.json /home/user/simulation_results"
    exit 1
fi

CONFIG_PATH="$1"
OUTPUT_PATH="$2"

# Check if config file exists
if [ ! -f "$CONFIG_PATH" ]; then
    echo "Error: Config file '$CONFIG_PATH' does not exist"
    exit 1
fi

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_PATH"

# Get absolute paths
CONFIG_ABS=$(realpath "$CONFIG_PATH")
OUTPUT_ABS=$(realpath "$OUTPUT_PATH")

CONFIG_DIR=$(dirname "$CONFIG_ABS")
CONFIG_FILE=$(basename "$CONFIG_ABS")

# Image name
IMAGE_NAME="mpsds-simulator"

echo "Building Docker image..."
docker build -t "$IMAGE_NAME" .

echo "Running simulation..."
echo "Config file: $CONFIG_ABS"
echo "Output directory: $OUTPUT_ABS"

# Run the Docker container
docker run --rm \
    -v "$CONFIG_DIR:/config:ro" \
    -v "$OUTPUT_ABS:/output" \
    "$IMAGE_NAME" \
    "/config/$CONFIG_FILE" \
    "/output"

echo "Simulation completed! Results are in: $OUTPUT_ABS"
