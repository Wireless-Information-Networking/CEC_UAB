# Use Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy and install requirements
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

# Run the app
CMD ["python", "run.py"]
