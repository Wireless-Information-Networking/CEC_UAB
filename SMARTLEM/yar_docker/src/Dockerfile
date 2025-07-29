# Use Python 3.12 slim image as base
FROM python:3.12-slim

# Set working directory in container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Create results directory
RUN mkdir -p /app/results /app/output

# Make puppeteer.py executable
RUN chmod +x puppeteer.py

# Set Python path to include the current directory
ENV PYTHONPATH=/app

# Create entrypoint script
RUN echo '#!/bin/bash\n\
if [ $# -eq 0 ]; then\n\
    echo "Usage: docker run -v /host/path/to/config:/config -v /host/path/to/output:/output mpsds-simulator /config/config.json /output"\n\
    exit 1\n\
fi\n\
\n\
CONFIG_FILE="$1"\n\
OUTPUT_DIR="$2"\n\
\n\
if [ ! -f "$CONFIG_FILE" ]; then\n\
    echo "Error: Config file $CONFIG_FILE does not exist"\n\
    exit 1\n\
fi\n\
\n\
if [ ! -d "$OUTPUT_DIR" ]; then\n\
    echo "Creating output directory: $OUTPUT_DIR"\n\
    mkdir -p "$OUTPUT_DIR"\n\
fi\n\
\n\
echo "Starting simulation with config: $CONFIG_FILE"\n\
echo "Output will be saved to: $OUTPUT_DIR"\n\
\n\
python puppeteer.py "$CONFIG_FILE" "$OUTPUT_DIR"\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Set the entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command (will be overridden by entrypoint args)
CMD []
