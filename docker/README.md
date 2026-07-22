# Smart Energy Optimizer

Barcelona house-level energy management system.
XGBoost demand forecasting + LightGBM solar forecasting +
LP appliance scheduler + real-time PVPC price integration.

---

## Folder structure

```
energy-optimizer/
├── app/
│   ├── __init__.py          # package marker
│   ├── config.py            # all paths, env vars, hyper-parameters
│   ├── utils.py             # shared helpers (price bands, serialisation …)
│   ├── train_models.py      # one-shot training pipeline → .pkl artefacts
│   ├── optimizer.py         # LP scheduler, ApplianceSpec, plug-event handler
│   └── app.py               # Flask factory + all API routes
├── static/
│   └── dashboard.html       # production single-page dashboard
├── nginx/
│   ├── nginx.conf           # reverse proxy config
│   └── certs/               # place cert.pem + key.pem here for HTTPS
├── data/                    # ← place your CSV / XLSX files here
│   ├── H1_combined.csv
│   ├── generation_final.csv
│   ├── PrecioFacturacion.xlsx
│   ├── PrecioExcedente.xlsx
│   └── PrecioMercado.xlsx
├── models/                  # auto-populated by train_models.py
├── logs/                    # auto-created at startup
├── .env                     # active environment (not committed)
├── .env.example             # template
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
├── gunicorn.conf.py
├── requirements.txt
└── wsgi.py
```

---

## Prerequisites

| Tool          | Minimum version |
|---------------|-----------------|
| Python        | 3.11            |
| Docker        | 24.x            |
| Docker Compose | v2 (plugin)    |

---

## 1 — Prepare data files

Copy the five source files into `data/`:

```
data/H1_combined.csv
data/generation_final.csv
data/PrecioFacturacion.xlsx
data/PrecioExcedente.xlsx
data/PrecioMercado.xlsx
```

---

## 2 — Local Python setup (no Docker)

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and edit environment
cp .env.example .env
# Edit .env: set DATA_DIR, MODELS_DIR, LOG_DIR, STATIC_DIR to local paths
# e.g.  DATA_DIR=./data   MODELS_DIR=./models   LOG_DIR=./logs

# Train models (first run only — takes a few minutes)
python -m app.train_models

# Start development server
python wsgi.py
# → http://localhost:5000
```

---

## 3 — Local Docker setup (Windows / macOS / Linux)

### 3.1 Build and start

```bash
# Copy env file
cp .env.example .env
# Edit .env — defaults work for local Docker testing

# Build and start all services
docker compose up --build -d

# Stream logs
docker compose logs -f app
```

The first run trains models automatically (`entrypoint.sh`).
Allow up to 5 minutes for training before the health check passes.

### 3.2 Verify

```bash
# Health check
curl http://localhost/health

# API status
curl http://localhost/api/status

# Open dashboard
# http://localhost
```

### 3.3 Stop

```bash
docker compose down
```

---

## 4 — Train models manually

```bash
# Inside running container
docker compose exec app python -m app.train_models

# Force retrain even if artefacts exist
docker compose exec app python -m app.train_models --force

# Locally (virtual env active)
python -m app.train_models --force
```

Model artefacts saved to `models/`:
- `trained_models.pkl`  — XGBoost appliance models
- `solar_model.pkl`     — LightGBM solar forecaster
- `sim_frame.pkl`       — pre-built simulation DataFrame
- `price_meta.pkl`      — PVPC price thresholds (p33, p67)

---

## 5 — API reference

| Method | Endpoint              | Description                                     |
|--------|-----------------------|-------------------------------------------------|
| GET    | `/health`             | Health check — returns `{"status":"ok"}`        |
| GET    | `/api/status`         | Current sim snapshot (solar, price, state)      |
| GET    | `/api/schedule`       | Full LP schedule + override history             |
| GET    | `/api/plan`           | Appliance plan + hourly chart data              |
| GET    | `/api/available_dates`| List of schedulable dates in the dataset        |
| POST   | `/api/regenerate`     | Regenerate LP for a date `{"target_date":"…"}`  |
| POST   | `/api/event`          | Smart-plug / manual override event              |
| POST   | `/api/next`           | Advance simulation hour (demo)                  |

### `/api/event` payload

```json
{
  "appliance_key": "wm",
  "time": "11:30",
  "event_type": "unexpected"
}
```

`appliance_key`: `wm` | `boiler` | `ac1` | `ac2`  
`time`: `"HH:MM"` — sub-hourly precision for cost proration  
`event_type`: `"unexpected"` (plug detected) | `"manual"` (user override)

---

## 6 — Linux university VM deployment

### 6.1 First-time server setup

```bash
# Install Docker (Ubuntu 22.04 / 24.04)
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER
```

### 6.2 Clone and configure

```bash
git clone https://github.com/<your-org>/energy-optimizer.git
cd energy-optimizer

# Upload data files (from your machine)
scp data/*.csv data/*.xlsx user@vm-ip:~/energy-optimizer/data/

# Configure environment
cp .env.example .env
nano .env   # set SECRET_KEY, CORS_ORIGINS, domain
```

### 6.3 Start

```bash
docker compose up --build -d
docker compose logs -f
```

---

## 7 — UAB university domain + HTTPS

### 7.1 Obtain SSL certificate

```bash
# Option A: Let's Encrypt (if port 80 is publicly reachable)
sudo apt-get install -y certbot
sudo certbot certonly --standalone -d myproject.uab.es
sudo cp /etc/letsencrypt/live/myproject.uab.es/fullchain.pem nginx/certs/cert.pem
sudo cp /etc/letsencrypt/live/myproject.uab.es/privkey.pem   nginx/certs/key.pem

# Option B: University-provided certificate
# Place cert.pem and key.pem in nginx/certs/ manually
```

### 7.2 Update nginx.conf

Edit `nginx/nginx.conf`, change:

```nginx
server_name myproject.uab.es;      # line ~60
```

### 7.3 Update .env

```ini
CORS_ORIGINS=https://myproject.uab.es
```

### 7.4 Restart nginx

```bash
docker compose restart nginx
```

### 7.5 UAB NGINX template integration

If UAB provides an upstream NGINX container that terminates TLS and
forwards traffic internally, set `docker-compose.yml` to expose only
port 80 and disable the HTTPS server block in `nginx/nginx.conf`.
The UAB proxy handles HTTPS; the internal network uses plain HTTP.

```yaml
# docker-compose.yml — UAB mode
ports:
  - "80:80"   # only HTTP; TLS handled by UAB upstream proxy
```

---

## 8 — Scaling note

`STATE` (current schedule, override history) is stored in-process.  
With `GUNICORN_WORKERS=1` (default) this is fully consistent.  
For multi-worker deployments, move STATE to Redis and use `flask-caching`
or a dedicated state microservice.

---

## 9 — Useful commands

```bash
# View running containers
docker compose ps

# Tail app logs
docker compose logs -f app

# Retrain models without downtime
docker compose exec app python -m app.train_models --force

# Open shell inside app container
docker compose exec app /bin/sh

# Rebuild image after code changes
docker compose up --build -d app

# Remove all containers + volumes (destructive)
docker compose down -v
```
