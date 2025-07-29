#!/bin/bash

# Example usage script for MPSDS Docker simulation

echo "MPSDS Docker Simulation Example"
echo "================================"

# Check if config file exists
if [ ! -f "config_default.json" ]; then
    echo "Error: config_default.json not found in current directory"
    echo "Please ensure you're running this from the MPSDS project directory"
    exit 1
fi

# Create a test output directory
OUTPUT_DIR="./docker_test_results"
echo "Creating output directory: $OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

echo ""
echo "Running simulation with Docker..."
echo "Config file: $(pwd)/config_default.json"
echo "Output directory: $(pwd)/$OUTPUT_DIR"
echo ""

# Run the simulation using Docker
docker run --rm \
    -v "$(pwd):/config:ro" \
    -v "$(pwd)/$OUTPUT_DIR:/output" \
    mpsds-simulator \
    "/config/config_default.json" \
    "/output"

# Check if simulation was successful
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Simulation completed successfully!"
    echo "Results are available in: $OUTPUT_DIR"
    echo ""
    echo "Generated files:"
    ls -la "$OUTPUT_DIR"
else
    echo ""
    echo "❌ Simulation failed!"
fi
