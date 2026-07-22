"""
app.py
Flask application factory.

Startup sequence:
  1. Load artefacts produced by train_models.py (pkl files).
  2. Initialise price thresholds in utils.py module globals.
  3. Build first-day LP schedule → STATE.
  4. Register all API routes.

Routes (exact parity with notebook cell 14):
  GET  /                      → dashboard.html
  GET  /health                → health-check JSON
  GET  /api/status            → current sim-row snapshot
  GET  /api/plan              → appliance plan + hourly chart
  GET  /api/schedule          → full schedule + override history
  POST /api/event             → smart-plug or manual override
  GET  /api/available_dates   → list of schedulable dates
  POST /api/regenerate        → regenerate LP for a given date
  POST /api/next              → advance simulation hour (demo)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from app.config import Config
from app.utils import (
    get_price_band_from_price,
    set_price_thresholds,
    make_serializable,
    get_recommendation,
    get_energy_state,
    parse_hhmm,
)
from app.optimizer import (
    ApplianceSpec,
    generate_morning_schedule,
    handle_smart_plug_event,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# Logging
# ══════════════════════════════════════════════════════════════════

def _setup_logging() -> None:
    Config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s  %(levelname)s  %(name)s — %(message)s"
    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(Config.LOG_DIR / "app.log"),
    ]
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
        format=fmt,
        handlers=handlers,
    )


# ══════════════════════════════════════════════════════════════════
# Artefact loader
# ══════════════════════════════════════════════════════════════════

def _load_artefacts() -> tuple:
    """
    Load the four pkl files produced by train_models.py.
    Raises FileNotFoundError with a clear message if training hasn't run.
    """
    logger.info("Loading model artefacts from %s …", Config.MODELS_DIR)

    if not Config.SIM_FRAME_PATH.exists():
        raise FileNotFoundError(
            f"Simulation frame not found: {Config.SIM_FRAME_PATH}\n"
            "Run `python -m app.train_models` first, or let entrypoint.sh do it."
        )

    trained_models = joblib.load(Config.TRAINED_MODELS_PATH)
    solar_model    = joblib.load(Config.SOLAR_MODEL_PATH)
    sim            = joblib.load(Config.SIM_FRAME_PATH)
    price_meta     = joblib.load(Config.PRICE_META_PATH)

    # Restore module-level price thresholds
    set_price_thresholds(price_meta["p33"], price_meta["p67"])

    logger.info(
        "✅ Artefacts loaded — models=%d | sim=%d rows | p33=%.4f p67=%.4f",
        len(trained_models), len(sim),
        price_meta["p33"], price_meta["p67"],
    )
    return trained_models, solar_model, sim, price_meta


# ══════════════════════════════════════════════════════════════════
# Initial STATE builder
# ══════════════════════════════════════════════════════════════════

def _build_initial_state(sim: pd.DataFrame, trained_models: dict) -> dict:
    """
    Generate the first-day LP schedule and populate STATE.
    Exact reproduction of notebook cell 13 initialisation block.
    """
    first_date = pd.to_datetime(sim["timestamp"]).dt.date.iloc[0]
    day_sim    = sim[pd.to_datetime(sim["timestamp"]).dt.date == first_date].copy()

    appliance_specs = []
    for key, name in [
        ("wm",     "Washing Machine"),
        ("boiler", "Boiler"),
        ("ac1",    "AC Unit 1"),
        ("ac2",    "AC Unit 2"),
    ]:
        col     = f"pred_{key}_kwh"
        total_e = float(day_sim[col].sum()) if col in day_sim.columns else 0.0
        if total_e < 0.005:
            continue
        dur = 2 if key in ("wm", "ac1", "ac2") else 1
        appliance_specs.append(ApplianceSpec(
            key=key, name=name,
            total_energy=total_e,
            duration_hours=dur,
        ))

    morning_data = generate_morning_schedule(
        sim_frame=sim,
        start_hour=6,
        target_date=None,
        specs=appliance_specs,
        current_hour=0,
    )

    # Enrich with appliance_schedule for /api/schedule compatibility
    morning_data["appliance_schedule"] = {
        item["name"]: {
            "hours":        item["active_hours"],
            "display":      ", ".join(
                [f"{h:02d}:00" for h in item["active_hours"]]
            ),
            "total_energy": item["total_energy"],
            "is_free":      item["is_free"],
            "price_band":   item["price_band"],
            "scenario":     item.get("scenario", ""),
            "shifted":      item["shifted"],
            "status":       item["status"],
        }
        for item in morning_data.get("schedule", [])
    }
    morning_data["override_history"] = []

    return {
        "morning_schedule": morning_data,
        "current_schedule": morning_data,
        "override_history": [],
        "current_hour":     6,
        "sim_index":        0,
    }


# ══════════════════════════════════════════════════════════════════
# Flask factory
# ══════════════════════════════════════════════════════════════════

def create_app() -> Flask:
    _setup_logging()

    app = Flask(
        __name__,
        static_folder=str(Config.STATIC_DIR),
        static_url_path="/static",
    )
    app.config["SECRET_KEY"] = Config.SECRET_KEY

    CORS(app, origins=Config.CORS_ORIGINS)

    # ── Load artefacts once at startup ────────────────────────
    trained_models, solar_model, sim, price_meta = _load_artefacts()
    STATE = _build_initial_state(sim, trained_models)

    # ─────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────

    def _safe_float(val, default: float = 0.0) -> float:
        try:
            v = float(val)
            return default if v != v else round(v, 4)   # NaN check
        except Exception:
            return default

    # ─────────────────────────────────────────────────────────
    # Routes
    # ─────────────────────────────────────────────────────────

    @app.route("/")
    def index():
        return send_from_directory(str(Config.STATIC_DIR), "dashboard.html")

    # ── Health check ──────────────────────────────────────────
    @app.route("/health")
    def health():
        return jsonify({
            "status":      "ok",
            "timestamp":   datetime.now().isoformat(),
            "sim_rows":    len(sim),
            "models":      list(trained_models.keys()),
            "current_hour": STATE["current_hour"],
        })

    # ── Current simulation status ─────────────────────────────
    @app.route("/api/status")
    def status():
        idx = min(STATE["sim_index"], len(sim) - 1)
        row = sim.iloc[idx]
        ts  = pd.to_datetime(row["timestamp"])

        return jsonify({
            "current_hour":      STATE["current_hour"],
            "date_str":          ts.strftime("%A %d %B %Y"),
            "time_str":          ts.strftime("%H:%M"),
            "solar_now":         _safe_float(row["predicted_solar_kwh"]),
            "consumption_now":   _safe_float(row["predicted_consumption_kwh"]),
            "price_now":         _safe_float(row["price_eur_kwh"]),
            "price_band":        str(row["price_band"])
                                 if pd.notna(row.get("price_band")) else "LOW",
            "energy_state":      str(row["energy_state"])
                                 if pd.notna(row.get("energy_state")) else "BALANCED",
            "scenario":          str(row.get("scenario", "BALANCED_VALLE")),
            "recommendation":    str(row.get("recommendation",
                                            "✅ NORMAL: No action needed")),
            "is_golden":         bool(row.get("is_golden_window", False)),
            "is_danger":         bool(row.get("is_danger_window", False)),
            "opportunity_score": _safe_float(row.get("opportunity_score", 0)),
        })

    # ── Appliance plan + hourly chart data ────────────────────
    @app.route("/api/plan")
    def plan():
        sched = STATE["current_schedule"]
        if not sched:
            return jsonify({"error": "No schedule yet"}), 404

        appl_sched: dict = {}
        for item in sched.get("schedule", []):
            appl_sched[item["name"]] = {
                "hours":        item.get("active_hours", [item["scheduled_hour"]]),
                "display":      ", ".join([
                    f"{h:02d}:00"
                    for h in item.get("active_hours", [item["scheduled_hour"]])
                ]),
                "total_energy": item["total_energy"],
                "is_free":      item["is_free"],
                "price_band":   item["price_band"],
                "scenario":     item.get("scenario", ""),
                "shifted":      item["shifted"],
                "status":       item["status"],
            }

        chart = sched.get("chart_data", [])
        hourly_plan = [
            {
                "hour":        c["hour"],
                "solar":       c["solar"],
                "price":       c["price"],
                "price_band":  c["price_band"],
                "consumption": c["consumption"],
                "scenario":    get_recommendation(
                    get_energy_state(c["solar"] - c["consumption"]),
                    c["price_band"],
                )[0],
            }
            for c in chart
        ]

        return jsonify({
            "date":               sched.get("day_display", ""),
            "generated_at":       sched.get("generated_at", ""),
            "baseline_cost":      sched.get("baseline_cost", 0),
            "optimized_cost":     sched.get("optimized_cost", 0),
            "daily_saving":       sched.get("daily_saving", 0),
            "appliance_schedule": appl_sched,
            "hourly_plan":        hourly_plan,
            "schedule_items":     make_serializable(sched.get("schedule", [])),
        })

    # ── Full current schedule ─────────────────────────────────
    @app.route("/api/schedule")
    def get_schedule():
        sched = STATE["current_schedule"]
        if not sched:
            return jsonify({"error": "No schedule yet"}), 404
        out = make_serializable(sched)
        out["current_hour"]     = STATE["current_hour"]
        out["override_history"] = STATE["override_history"]
        return jsonify(out)

    # ── Smart-plug detected or manual user override ───────────
    @app.route("/api/event", methods=["POST"])
    def plug_event():
        data       = request.get_json() or {}
        key        = data.get("appliance_key", "")
        event_type = data.get("event_type", "manual")

        # Accept "time": "11:30" (sub-hourly) OR "hour": 11 (legacy)
        raw_time = data.get("time", None)
        raw_hour = data.get("hour", None)

        if raw_time is not None:
            hour, minute  = parse_hhmm(raw_time)
            detected_time = raw_time
        elif raw_hour is not None:
            hour, minute  = int(raw_hour), 0
            detected_time = f"{hour:02d}:00"
        else:
            hour, minute  = STATE["current_hour"], 0
            detected_time = f"{hour:02d}:00"

        valid_keys = ["wm", "boiler", "ac1", "ac2"]
        if key not in valid_keys:
            return jsonify({"error": f"Unknown appliance key: {key}"}), 400

        # ── Deduplication: block identical event within 60 s ──
        now = datetime.now()
        for past in STATE["override_history"]:
            if (
                past["appliance"]  == key
                and past["hour"]   == hour
                and past["event_type"] == event_type
            ):
                try:
                    past_dt = datetime.strptime(
                        f"{now.strftime('%Y-%m-%d')} {past['time']}",
                        "%Y-%m-%d %H:%M",
                    )
                    if abs((now - past_dt).total_seconds()) < 60:
                        logger.info("DUPLICATE blocked: %s at %02d:00", key, hour)
                        out = make_serializable(STATE["current_schedule"])
                        out["override_history"] = STATE["override_history"]
                        out["current_hour"]     = STATE["current_hour"]
                        out["duplicate"]        = True
                        return jsonify(out)
                except Exception:
                    pass

        logger.info("⚡ EVENT: %s — %s at %02d:00", event_type, key, hour)

        result = handle_smart_plug_event(
            appliance_key  = key,
            detected_hour  = hour,
            current_hour   = STATE["current_hour"],
            morning_data   = STATE["morning_schedule"],
            sim_frame      = sim,
            trained_models = trained_models,
            event_type     = event_type,
            detected_time  = detected_time,
        )

        # Chain lp_results_raw so subsequent overrides are aware of prior locks
        if result.get("lp_results_raw"):
            STATE["morning_schedule"]["lp_results_raw"] = result["lp_results_raw"]

        STATE["current_schedule"] = result
        STATE["override_history"].append({
            "time":       now.strftime("%H:%M"),
            "appliance":  key,
            "hour":       hour,
            "minute":     minute,
            "event_type": event_type,
            "trigger":    result.get("trigger", ""),
        })

        out = make_serializable(result)
        out["override_history"] = STATE["override_history"]
        out["current_hour"]     = STATE["current_hour"]
        return jsonify(out)

    # ── Available dates ───────────────────────────────────────
    @app.route("/api/available_dates")
    def available_dates():
        dates = sorted(
            pd.to_datetime(sim["timestamp"])
            .dt.strftime("%Y-%m-%d")
            .unique()
            .tolist()
        )
        return jsonify({"dates": dates, "count": len(dates)})

    # ── (Re-)generate schedule for a specific date ────────────
    @app.route("/api/regenerate", methods=["POST"])
    def regenerate():
        data        = request.get_json() or {}
        target_date = data.get("target_date", None)

        if target_date:
            logger.info("Generating schedule for: %s", target_date)
        else:
            logger.info("Regenerating schedule (next available day) …")

        m = generate_morning_schedule(
            sim, start_hour=6, target_date=target_date
        )
        # Enrich with appliance_schedule
        m["appliance_schedule"] = {
            item["name"]: {
                "hours":        item["active_hours"],
                "display":      ", ".join([f"{h:02d}:00" for h in item["active_hours"]]),
                "total_energy": item["total_energy"],
                "is_free":      item["is_free"],
                "price_band":   item["price_band"],
                "scenario":     item.get("scenario", ""),
                "shifted":      item["shifted"],
                "status":       item["status"],
            }
            for item in m.get("schedule", [])
        }
        m["override_history"] = []

        STATE["morning_schedule"]  = m
        STATE["current_schedule"]  = m
        STATE["override_history"]  = []

        logger.info("✅ Schedule ready: %s", m.get("day_display", "?"))

        out = make_serializable(m)
        out["current_hour"] = STATE["current_hour"]
        return jsonify(out)

    # ── Advance simulation hour (demo / testing) ──────────────
    @app.route("/api/next", methods=["POST"])
    def next_hour():
        STATE["current_hour"] = (STATE["current_hour"] + 1) % 24
        STATE["sim_index"]    = min(STATE["sim_index"] + 1, len(sim) - 1)
        logger.debug("Hour → %02d:00", STATE["current_hour"])
        return jsonify({"current_hour": STATE["current_hour"]})

    return app
