"""
config.py — single source of truth for paths, env vars, and ML hyper-parameters.
Every other module imports from here; nothing is hard-coded elsewhere.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    # ── Directories (overridable via env) ─────────────────────
    DATA_DIR   = Path(os.getenv("DATA_DIR",   str(BASE_DIR / "data")))
    MODELS_DIR = Path(os.getenv("MODELS_DIR", str(BASE_DIR / "models")))
    STATIC_DIR = Path(os.getenv("STATIC_DIR", str(BASE_DIR / "static")))
    LOG_DIR    = Path(os.getenv("LOG_DIR",    str(BASE_DIR / "logs")))
        # LP optimizer constants
    LP_SOLAR_BONUS_COEFF = 0.6
    LP_PEAK_PENALTY_COEFF = 2.0
    LP_VALLE_BONUS_COEFF = 0.5
    LP_SOFT_PREF_PENALTY = 0.3

    LP_SLOT_CAP_BASE_MULT = 1.0
    LP_GOLDEN_CAP_MULT = 2.0
    LP_SOLAR_CAP_MULT = 1.5
    LP_HIGH_CAP_MULT = 0.6
    LP_MIN_CAP_MULT = 0.25

    # Appliance display metadata
    APPL_NAMES = {
        "ac1_kwh": "AC Unit 1",
        "ac2_kwh": "AC Unit 2",
        "boiler_kwh": "Boiler",
        "fridge_kwh": "Refrigerator",
        "wm_kwh": "Washing Machine",
        "consumption_kwh": "Total Consumption"
    }

    APPL_COLORS = {
        "ac1_kwh": "#3498DB",
        "ac2_kwh": "#2980B9",
        "boiler_kwh": "#E74C3C",
        "fridge_kwh": "#2ECC71",
        "wm_kwh": "#F39C12",
        "consumption_kwh": "#9B59B6"
    }
        # LP optimizer constants
    LP_SOLAR_BONUS_COEFF = 0.6
    LP_HIGH_PRICE_PENALTY = 1.5
    LP_LOW_PRICE_BONUS = 0.7
    LP_VALLE_BONUS_COEFF = 0.5
    LP_LLANO_PENALTY_COEFF = 0.2
    LP_PEAK_PENALTY_COEFF = 2.0

        # LP optimizer tuning
    LP_SOLAR_BONUS_COEFF = 0.6
    LP_HIGH_PRICE_PENALTY = 1.5
    LP_LOW_PRICE_BONUS = 0.7
    
    # ── Raw data files ────────────────────────────────────────
    HOUSE_PATH        = DATA_DIR / "H1_combined.csv"
    SOLAR_PATH        = DATA_DIR / "generation_final.csv"
    PRICE_FACTURACION = DATA_DIR / "PrecioFacturacion.xlsx"
    PRICE_EXCEDENTE   = DATA_DIR / "PrecioExcedente.xlsx"
    PRICE_MERCADO     = DATA_DIR / "PrecioMercado.xlsx"

    # ── Persisted artefacts ───────────────────────────────────
    TRAINED_MODELS_PATH = MODELS_DIR / "trained_models.pkl"
    SOLAR_MODEL_PATH    = MODELS_DIR / "solar_model.pkl"
    SIM_FRAME_PATH      = MODELS_DIR / "sim_frame.pkl"
    PRICE_META_PATH     = MODELS_DIR / "price_meta.pkl"

    # ── Domain / deployment ───────────────────────────────────
    N_HOUSES     = int(os.getenv("N_HOUSES", "13"))
    SECRET_KEY   = os.getenv("SECRET_KEY", "change-me-in-production")
    FLASK_DEBUG  = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

    # ── Logging ───────────────────────────────────────────────
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # ── XGBoost hyper-parameters ──────────────────────────────
    XGB_CONFIGS: dict = {
        "consumption_kwh": dict(n_estimators=400, learning_rate=0.03, max_depth=5, random_state=42),
        "ac1_kwh":         dict(n_estimators=300, learning_rate=0.02, max_depth=3, random_state=42),
        "ac2_kwh":         dict(n_estimators=300, learning_rate=0.02, max_depth=3, random_state=42),
        "boiler_kwh":      dict(n_estimators=200, learning_rate=0.02, max_depth=3, random_state=42),
        "wm_kwh":          dict(n_estimators=200, learning_rate=0.02, max_depth=3, random_state=42),
    }

    # ── Target columns and their display names ─────────────────
    ALL_TARGETS: dict = {
        "consumption_kwh": "Total Consumption",
        "ac1_kwh":         "AC Unit 1",
        "ac2_kwh":         "AC Unit 2",
        "boiler_kwh":      "Boiler",
        "fridge_kwh":      "Refrigerator",
        "wm_kwh":          "Washing Machine",
    }

    # ── Feature sets ──────────────────────────────────────────
    BASE_FEATURES: list = [
        "hour", "dayofweek", "month", "day_of_year",
        "is_weekend", "is_high_price", "is_low_price",
        "is_morning", "is_evening", "is_summer", "is_winter",
        "hour_sin", "hour_cos", "dow_sin", "dow_cos",
        "month_sin", "month_cos",
        "lag_1h", "lag_2h", "lag_3h", "lag_24h", "lag_168h",
        "roll_mean_3h", "roll_mean_24h", "roll_std_24h",
        "roll_mean_168h", "roll_mean_6h",
        "diff_1h", "diff_24h",
    ]

    SOLAR_FEATURES: list = [
        "hour", "dayofweek", "month", "day_of_year",
        "is_daylight", "is_peak_solar",
        "hour_sin", "hour_cos", "month_sin", "month_cos",
        "solar_lag_1h", "solar_lag_24h",
    ]
