"""
utils.py — shared helpers used by every other module.

Includes:
  - ConstantPredictor  (sklearn-compatible; used for near-flat fridge load)
  - price-band logic   (thresholds loaded once from price_meta.pkl)
  - sub-hourly time helpers
  - JSON serialisation
  - 9-scenario recommendation engine
"""
from __future__ import annotations

import logging
from typing import Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
# ConstantPredictor — must live here (not in train_models) so that
# joblib can find the class when loading persisted models.
# ══════════════════════════════════════════════════════════════════

class ConstantPredictor:
    """Predict a fixed scalar for every row — used for the fridge."""

    def __init__(self, val: float) -> None:
        self.val = float(val)

    def predict(self, X) -> np.ndarray:
        return np.full(len(X), self.val)


# ══════════════════════════════════════════════════════════════════
# Price-band logic
# Module-level variables are set once at startup via set_price_thresholds().
# ══════════════════════════════════════════════════════════════════

_P33: float = 0.0
_P67: float = 0.0

def get_price_band_from_price(price: float) -> str:
    return get_price_band(price)


def get_price_weight_from_price(price: float) -> int:
    return get_price_weight(price)

def set_price_thresholds(p33: float, p67: float) -> None:
    """Call once after loading price_meta.pkl."""
    global _P33, _P67
    _P33, _P67 = float(p33), float(p67)
    logger.info(
        "Price thresholds — LOW < €%.4f  MEDIUM < €%.4f  HIGH ≥ €%.4f",
        p33, p67, p67,
    )


def get_p33() -> float:
    return _P33


def get_p67() -> float:
    return _P67


def get_price_band(price: float) -> str:
    if price >= _P67:
        return "HIGH"
    if price >= _P33:
        return "MEDIUM"
    return "LOW"


def get_price_weight(price: float) -> int:
    band = get_price_band(price)
    return 3 if band == "HIGH" else 2 if band == "MEDIUM" else 1


# ══════════════════════════════════════════════════════════════════
# Sub-hourly time helpers
# ══════════════════════════════════════════════════════════════════

def parse_hhmm(time_input) -> Tuple[int, int]:
    """
    Parse any time representation to (hour, minute).
    Accepts: "11:30", "11.5", 11.5, 11, "11"
    """
    if isinstance(time_input, str) and ":" in time_input:
        parts = time_input.strip().split(":")
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    val = float(time_input)
    h   = int(val)
    m   = round((val - h) * 60)
    return h, m


def time_to_decimal(time_input) -> float:
    """'11:30' → 11.5"""
    h, m = parse_hhmm(time_input)
    return h + m / 60.0


def partial_hour_fraction(time_str, is_start: bool = True) -> float:
    """
    Fraction of the hour slot that is usable given a sub-hourly boundary.
    is_start=True  → start at 11:45 means 15/60 = 0.25 of that slot usable.
    is_start=False → end   at 11:45 means 45/60 = 0.75 of that slot usable.
    """
    _, m = parse_hhmm(time_str)
    if is_start:
        return (60 - m) / 60.0
    return m / 60.0 if m > 0 else 1.0


def get_hour_slots_with_weights(start_time, end_time) -> dict:
    """
    Return {hour: weight} for a time window; weights sum to 1.0.
    Example: start="11:30", end="13:45"  → {11: 0.25, 12: 0.5, 13: 0.25}
    """
    sh, sm = parse_hhmm(start_time)
    eh, em = parse_hhmm(end_time)

    slots: dict[int, int] = {}
    total = 0

    if sh == eh:
        mins      = (em - sm) if em > sm else 60
        slots[sh] = mins
        total     = mins
    else:
        first        = 60 - sm
        slots[sh]    = first
        total       += first
        for h in range(sh + 1, eh):
            slots[h] = 60
            total   += 60
        if em > 0:
            slots[eh] = em
            total    += em

    if total == 0:
        total = 60

    return {h: mins / total for h, mins in slots.items()}


# ══════════════════════════════════════════════════════════════════
# JSON serialisation
# ══════════════════════════════════════════════════════════════════

def make_serializable(obj):
    """Recursively convert numpy types and strip lp_results_raw."""
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()
                if k != "lp_results_raw"}
    if isinstance(obj, list):
        return [make_serializable(i) for i in obj]
    if isinstance(obj, np.integer):   return int(obj)
    if isinstance(obj, np.floating):  return float(obj)
    if isinstance(obj, np.ndarray):   return obj.tolist()
    if isinstance(obj, np.bool_):     return bool(obj)
    return obj


# ══════════════════════════════════════════════════════════════════
# Energy-state helper
# ══════════════════════════════════════════════════════════════════

def get_energy_state(net: float) -> str:
    """net = solar_kwh - consumption_kwh"""
    if net > 0.1:   return "SURPLUS"
    if net < -0.1:  return "DEFICIT"
    return "BALANCED"


# ══════════════════════════════════════════════════════════════════
# 9-scenario recommendation engine
# ══════════════════════════════════════════════════════════════════

_SCENARIOS: dict = {
    ("SURPLUS",  "HIGH")  : ("GOLDEN_HOUR",   "🌟 GOLDEN HOUR: Run appliances NOW — free solar + peak price saving"),
    ("SURPLUS",  "MEDIUM"): ("SURPLUS_LLANO",  "📅 SCHEDULE: Good opportunity — run flexible appliances within 2 hours"),
    ("SURPLUS",  "LOW")   : ("SURPLUS_VALLE",  "☀️ OPTIONAL: Solar available and grid is also cheap"),
    ("DEFICIT",  "HIGH")  : ("DANGER_WINDOW",  "⚠️ DANGER: Avoid all usage — expensive grid and no solar"),
    ("DEFICIT",  "MEDIUM"): ("DEFICIT_LLANO",  "⚡ OPTIMIZE: Run essentials only — wait for cheaper hours"),
    ("DEFICIT",  "LOW")   : ("DEFICIT_VALLE",  "🔌 USE GRID: Cheapest import window — safe to run appliances"),
    ("BALANCED", "HIGH")  : ("BALANCED_PUNTA", "⏸ HOLD: Avoid adding extra load during peak price"),
    ("BALANCED", "MEDIUM"): ("BALANCED_LLANO", "🌤 PREFER SOLAR: Stable condition — use solar where possible"),
    ("BALANCED", "LOW")   : ("BALANCED_VALLE", "✅ NORMAL: No action needed — all conditions acceptable"),
}


def get_recommendation(energy_state: str, price_band: str) -> Tuple[str, str]:
    return _SCENARIOS.get(
        (energy_state, price_band),
        ("UNKNOWN", "🔍 Monitoring…"),
    )
