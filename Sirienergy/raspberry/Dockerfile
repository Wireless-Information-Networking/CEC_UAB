# Use Python image
FROM python:3.9

# Set working directory
WORKDIR /app

# Copy and install requirements
COPY ./requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

#-------------------------------------------------
#requirements for mqtt
RUN pip install --no-cache-dir paho-mqtt requests
#-------------------------------------------------
# Run the app
CMD ["python", "app.py"]
