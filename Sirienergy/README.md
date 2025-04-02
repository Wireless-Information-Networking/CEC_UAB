# Sirienergy

## Overview

Sirienergy is a web application designed to provide users with insights into their energy consumption, production, and other related metrics. This repository contains the server-side code for the Sirienergy application.

## Features

- User authentication and management
- Energy consumption and production tracking
- Real-time weather data integration
- Energy price forecasting
- Visualization of energy data using charts
- Advices for users based on real data

## Project Structure
```
Sirienergy/  # Root project folder  
    ├── common/  # Shared utilities  
    ├── nginx/  # Nginx config  
    ├── sirienergy/  # Main app  
    │   ├── app/  # Core logic  
    │   │   ├── aux/  # Helpers  
    │   │   ├── controllers/  # Request handlers  
    │   │   ├── models/  # Database models  
    │   │   ├── static/  # CSS, JS, images  
    │   │   ├── templates/  # HTML templates  
    │   │   ├── views/  # View logic  
    │   │   ├── __init__.py  # Package init  
    │   │   └── config.py  # App settings  
    │   ├── .dockerignore  # Ignore files for Docker  
    │   ├── Dockerfile  # Docker build instructions  
    │   ├── requirements.txt  # Python dependencies  
    │   └── run.py  # App entry point  
    ├── .gitignore  # Ignore files for Git  
    ├── docker-compose.yml  # Docker services config  
    └── README  # Project info  
```

## Configuration

- The endpoint is set in `./nginx/nginx.conf`, defaulting to `sirienergy.uab.cat`.  
- API keys must be defined in `./sirienergy/.env`. Use `./sirienergy/.env.example` as a reference. Required services:  
  - [Open-Meteo](https://open-meteo.com/)  
  - [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/)  

## Installation

1. **Install dependencies:**  
   Ensure you have the following installed:  
   - Docker  
   - Docker Compose  

2. **Clone the repository:**  
   ```sh
   git clone https://github.com/Wireless-Information-Networking/CEC_UAB.git
   cd Sirienergy
   ```

3. **Configure the project:**  
   - Update `nginx.conf` if needed.  
   - Set API keys in `.env`.  

4. **Run the application:**  
   ```sh
   docker compose -f 'Sirienergy/docker-compose.yml' up -d --build
   ```

## Usage

- Open your endpoint in your browser.  
- Use the navigation bar to switch views (Home, User, etc.).  
- Fill out the user form to start tracking energy data.  





