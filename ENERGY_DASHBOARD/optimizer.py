"""
optimizer.py
LP appliance scheduler, ApplianceSpec dataclass,
morning schedule generator, and smart-plug / user-override handler.

Preserves the exact logic of notebook cells 12 (run_lp_day,
generate_morning_schedule, handle_smart_plug_event, ApplianceSpec,
parse_hhmm helpers) with no simplifications.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from app.config import Config
from app.utils import (
    get_price_band_from_price,
    get_price_weight_from_price,
    parse_hhmm,
    time_to_decimal,
    partial_hour_fraction,
    get_hour_slots_with_weights,
    get_recommendation,
    get_energy_state,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# ApplianceSpec  (exact from notebook cell 12)
# ══════════════════════════════════════════════════════════════════

@dataclass
class ApplianceSpec:
    key:            str
    name:           str
    total_energy:   float
    duration_hours: float
    priority:       int  = 2
    can_segment:    bool = True
    deadline_hour:  Optional[int] = None

    # Sub-hourly user constraints
    user_start_time: Optional[str] = None   # "HH:MM" exact start
    user_end_time:   Optional[str] = None   # "HH:MM" exact end
    preferred_start: Optional[int] = None   # soft hour preference

    # Computed by validate_and_fix()
    is_user_fixed:   bool      = field(default=False, init=False)
    locked_hours:    List[int] = field(default_factory=list,  init=False)
    hour_weights:    dict      = field(default_factory=dict,  init=False)
    hours_completed: float     = 0.0

    def validate_and_fix(self) -> None:
        """
        Resolve user time constraints.  Supports full and partial hours.
        Exact logic from notebook cell 12 ApplianceSpec.validate_and_fix().
        """
        if self.user_start_time is not None and self.user_end_time is not None:
            self.is_user_fixed = True
            self.hour_weights  = get_hour_slots_with_weights(
                self.user_start_time, self.user_end_time
            )
            self.locked_hours  = sorted(self.hour_weights.keys())
            start_dec          = time_to_decimal(self.user_start_time)
            end_dec            = time_to_decimal(self.user_end_time)
            self.duration_hours = max(end_dec - start_dec, 1 / 60)
            sh, sm = parse_hhmm(self.user_start_time)
            eh, em = parse_hhmm(self.user_end_time)
            logger.debug(
                "[Spec] %s: FIXED %02d:%02d→%02d:%02d slots=%s",
                self.name, sh, sm, eh, em, self.locked_hours,
            )

        elif self.user_start_time is not None:
            self.is_user_fixed  = False
            sh, sm              = parse_hhmm(self.user_start_time)
            self.preferred_start = sh
            first_fraction       = partial_hour_fraction(
                self.user_start_time, is_start=True
            )
            self.hour_weights = {sh: first_fraction}
            logger.debug(
                "[Spec] %s: PREFERRED start %02d:%02d (%.0f%% of first hour)",
                self.name, sh, sm, first_fraction * 100,
            )

        elif self.preferred_start is not None:
            self.is_user_fixed = False
            logger.debug(
                "[Spec] %s: SOFT preferred %02d:00", self.name, self.preferred_start
            )


# ══════════════════════════════════════════════════════════════════
# Occupied-slot pre-commitment (exact from notebook cell 12)
# ══════════════════════════════════════════════════════════════════

def _build_occupied_slots(specs: list[ApplianceSpec], hours: np.ndarray) -> np.ndarray:
    """
    Pre-commit energy for user-fixed appliances.
    Uses hour_weights to handle partial-hour slots correctly.
    """
    n        = len(hours)
    occupied = np.zeros(n)

    for spec in specs:
        if not spec.is_user_fixed:
            continue
        weights = spec.hour_weights or {}
        if not weights:
            e_per_h = spec.total_energy / max(len(spec.locked_hours), 1)
            weights = {h: e_per_h / spec.total_energy for h in spec.locked_hours}
        for h, weight in weights.items():
            idx = np.where(hours == h)[0]
            if len(idx) > 0:
                occupied[idx[0]] += spec.total_energy * weight

    return occupied


# ══════════════════════════════════════════════════════════════════
# Core LP solver  (exact from notebook cell 12 run_lp_day())
# ══════════════════════════════════════════════════════════════════

def run_lp_day(
    appliance_preds: dict,
    solar_fc:        np.ndarray,
    prices:          np.ndarray,
    hours:           np.ndarray,
    specs:           Optional[list] = None,
    current_hour:    int = 0,
    locked_before_t: Optional[dict] = None,
) -> tuple[pd.DataFrame, float, float, dict]:
    """
    Exact reproduction of notebook cell 12 run_lp_day().

    For each flexible appliance:
    1. If user-fixed → pre-commit to locked hours, skip LP.
    2. Freeze past decisions (rescheduling scenario).
    3. Build allowed-slot mask (block past, HIGH for WM, occupied, past deadline).
    4. Objective:  π̃(t) = price(t) − solar_bonus(t) + peak_penalty(t) − valle_bonus(t)
    5. Equality:   sum(x) = remaining_energy
    6. Inequality: x(t) ≤ adaptive_slot_cap(t)
    7. Solve via HiGHS.
    """
    n        = len(prices)
    prices   = np.array(prices,   dtype=float)
    solar_fc = np.array(solar_fc, dtype=float)
    hours    = np.array(hours,    dtype=int)

    spec_map: dict[str, ApplianceSpec] = {}
    if specs:
        for s in specs:
            s.validate_and_fix()
            spec_map[s.key] = s

    occupied = _build_occupied_slots(specs, hours) if specs else np.zeros(n)

    # Baseline load = fridge constant + small standby + pre-committed user loads
    fridge = np.array(
        appliance_preds.get("pred_fridge_kwh", np.zeros(n)), dtype=float
    )[:n]
    P = fridge + 0.05 + occupied

    flexible = {
        "wm":     ("pred_wm_kwh",     "Washing Machine"),
        "boiler": ("pred_boiler_kwh", "Boiler"),
        "ac1":    ("pred_ac1_kwh",    "AC Unit 1"),
        "ac2":    ("pred_ac2_kwh",    "AC Unit 2"),
    }

    results: dict = {}
    baseline_cost = float(np.dot(np.maximum(P - solar_fc, 0), prices))

    for key, (col, name) in flexible.items():
        orig = np.array(
            appliance_preds.get(col, np.zeros(n)), dtype=float
        )[:n]
        spec = spec_map.get(key)

        # ── USER FIXED: skip LP entirely ──────────────────────
        if spec and spec.is_user_fixed and spec.locked_hours:
            opt     = np.zeros(n)
            e_per_h = spec.total_energy / max(len(spec.locked_hours), 1)
            for h in spec.locked_hours:
                idx = np.where(hours == h)[0]
                if len(idx):
                    opt[idx[0]] = e_per_h

            baseline_cost += float(
                np.dot(np.maximum(P + orig - solar_fc, 0), prices)
            )
            results[key] = {
                "name": name, "original": orig.copy(), "optimized": opt,
                "shifted": False, "total_energy": spec.total_energy,
                "is_user_fixed": True, "segments": spec.locked_hours,
            }
            P += opt
            logger.debug("LP: %-20s FIXED by user @ %s", name, spec.locked_hours)
            continue

        # ── PRESERVE PAST DECISIONS (rescheduling) ────────────
        frozen_opt = np.zeros(n)
        if locked_before_t and key in locked_before_t:
            prev = np.array(locked_before_t[key])
            for t in range(n):
                if hours[t] < current_hour and t < len(prev):
                    frozen_opt[t] = prev[t]

        frozen_energy    = float(frozen_opt.sum())
        total_energy     = float(orig.sum())
        remaining_energy = max(total_energy - frozen_energy, 0.0)

        baseline_cost += float(
            np.dot(np.maximum(P + orig - solar_fc, 0), prices)
        )

        if remaining_energy < 0.005:
            results[key] = {
                "name": name, "original": orig.copy(), "optimized": frozen_opt,
                "shifted": False, "total_energy": total_energy,
                "is_user_fixed": False, "segments": [],
            }
            P += frozen_opt
            continue

        # ── ALLOWED SLOTS ─────────────────────────────────────
        v = np.ones(n)

        # Block past hours
        for t in range(n):
            if hours[t] < current_hour:
                v[t] = 0

        # Block HIGH price for washing machine
        if key == "wm":
            for t in range(n):
                if get_price_band_from_price(float(prices[t])) == "HIGH":
                    v[t] = 0

        # Block user-fixed occupied slots
        for t in range(n):
            if occupied[t] > 0.1:
                v[t] = 0

        # Apply deadline
        if spec and spec.deadline_hour is not None:
            for t in range(n):
                if hours[t] > spec.deadline_hour:
                    v[t] = 0

        allowed_idx = np.where(v > 0)[0]

        if len(allowed_idx) == 0:
            results[key] = {
                "name": name, "original": orig.copy(), "optimized": frozen_opt,
                "shifted": False, "total_energy": total_energy,
                "is_user_fixed": False, "segments": [],
            }
            P += frozen_opt
            continue

        n_allowed = len(allowed_idx)

        # ── OBJECTIVE: π̃(t) = price − solar_bonus + peak_penalty − valle_bonus ─
        c_base = prices[allowed_idx].copy()

        solar_coverage = np.minimum(
            solar_fc[allowed_idx] / max(remaining_energy, 0.01), 1.0
        )
        solar_bonus = c_base * solar_coverage * Config.LP_SOLAR_BONUS_COEFF

        price_penalty = np.array([
            c_base[i] * Config.LP_PEAK_PENALTY_COEFF
            if get_price_band_from_price(float(prices[allowed_idx[i]])) == "HIGH"
            else 0.0
            for i in range(n_allowed)
        ])

        valle_bonus = np.array([
            c_base[i] * Config.LP_VALLE_BONUS_COEFF
            if get_price_band_from_price(float(prices[allowed_idx[i]])) == "LOW"
            else 0.0
            for i in range(n_allowed)
        ])

        pref_penalty = np.zeros(n_allowed)
        if spec and spec.preferred_start is not None:
            for i, t in enumerate(allowed_idx):
                if hours[t] < spec.preferred_start:
                    pref_penalty[i] = Config.LP_SOFT_PREF_PENALTY

        c_final = c_base - solar_bonus + price_penalty - valle_bonus + pref_penalty

        # ── EQUALITY: total energy preserved ──────────────────
        A_eq = np.ones((1, n_allowed))
        b_eq = np.array([remaining_energy])

        # ── INEQUALITY: per-slot adaptive cap ─────────────────
        fair_share = remaining_energy / max(n_allowed, 1)
        slot_cap   = np.full(n_allowed, fair_share * Config.LP_SLOT_CAP_BASE_MULT)

        for i, t in enumerate(allowed_idx):
            price_t = float(prices[t])
            solar_t = float(solar_fc[t])
            net_t   = solar_t - float(P[t])
            band_t  = get_price_band_from_price(price_t)

            if net_t > 0.05 and band_t == "HIGH":
                slot_cap[i] = fair_share * Config.LP_GOLDEN_CAP_MULT
            elif net_t > 0.05:
                slot_cap[i] = fair_share * Config.LP_SOLAR_CAP_MULT
            elif band_t == "HIGH":
                slot_cap[i] = fair_share * Config.LP_HIGH_CAP_MULT

        slot_cap = np.maximum(slot_cap, fair_share * Config.LP_MIN_CAP_MULT)

        # Partial-hour cap for user preferred_start
        if spec and spec.user_start_time is not None and not spec.is_user_fixed:
            sh, sm = parse_hhmm(spec.user_start_time)
            if sm > 0:
                frac = partial_hour_fraction(spec.user_start_time, is_start=True)
                for i, t in enumerate(allowed_idx):
                    if hours[t] == sh:
                        slot_cap[i] = min(slot_cap[i], frac * remaining_energy)
                        break

        A_ub   = np.eye(n_allowed)
        b_ub   = slot_cap
        bounds = [(0.0, None)] * n_allowed

        result = linprog(
            c=c_final, A_eq=A_eq, b_eq=b_eq,
            A_ub=A_ub, b_ub=b_ub, bounds=bounds,
            method="highs",
        )

        if result.success:
            opt = frozen_opt.copy()
            for i, t in enumerate(allowed_idx):
                opt[t] += max(float(result.x[i]), 0.0)

            # Numerical safety: rescale if total drifts
            total_assigned = float(opt.sum())
            if abs(total_assigned - total_energy) > 0.01:
                scale = total_energy / max(total_assigned, 1e-9)
                opt   = opt * scale

            shifted  = not np.allclose(opt, orig, atol=0.01)
            segments = [int(hours[t]) for t in range(n) if opt[t] > 0.005]
            orig_peak = int(hours[int(np.argmax(orig))]) if orig.max() > 0.005 else -1
            logger.debug(
                "LP: %-20s orig=%02d:00 → spread=%s %s",
                name, orig_peak, segments,
                "SHIFTED ✅" if shifted else "unchanged",
            )
        else:
            opt      = frozen_opt.copy()
            shifted  = False
            segments = [int(hours[t]) for t in range(n) if opt[t] > 0.005]
            logger.warning("LP: %-20s FAILED — kept original", name)

        results[key] = {
            "name": name, "original": orig.copy(), "optimized": opt,
            "shifted": shifted, "total_energy": total_energy,
            "is_user_fixed": False, "segments": segments,
        }
        P += opt

    # ── Build output DataFrame ────────────────────────────────
    rows = []
    for t in range(n):
        rows.append({
            "hour":       int(hours[t]),
            "price":      float(prices[t]),
            "solar":      float(solar_fc[t]),
            "total_load": float(P[t]),
            "price_band": get_price_band_from_price(float(prices[t])),
        })
    df = pd.DataFrame(rows)
    df["grid_kwh"]   = np.maximum(df["total_load"] - df["solar"], 0)
    df["solar_used"] = np.minimum(df["total_load"], df["solar"])
    df["grid_cost"]  = df["grid_kwh"] * df["price"]
    opt_cost         = float(df["grid_cost"].sum())

    return df, opt_cost, baseline_cost, results


# ══════════════════════════════════════════════════════════════════
# Morning schedule generator  (exact from notebook cell 12)
# ══════════════════════════════════════════════════════════════════

def generate_morning_schedule(
    sim_frame:       pd.DataFrame,
    start_hour:      int = 6,
    target_date:     Optional[str] = None,
    specs:           Optional[list] = None,
    current_hour:    int = 0,
    locked_before_t: Optional[dict] = None,
) -> dict:
    """
    Exact reproduction of notebook cell 12 generate_morning_schedule().
    Selects one day's data, runs the LP, and returns a rich dict that
    the Flask API serialises directly.
    """
    sim_ts = pd.to_datetime(sim_frame["timestamp"])

    if target_date:
        mask     = sim_ts.dt.strftime("%Y-%m-%d") == str(target_date)
        day_pool = sim_frame[mask].copy()
        if len(day_pool) == 0:
            first_date = sim_ts.dt.date.iloc[0]
            day_pool   = sim_frame[sim_ts.dt.date == first_date].copy()
    else:
        first_date = sim_ts.dt.date.iloc[0]
        day_pool   = sim_frame[sim_ts.dt.date == first_date].copy()

    day_df   = day_pool.sort_values("timestamp").reset_index(drop=True)
    day_rows = day_df[pd.to_datetime(day_df["timestamp"]).dt.hour >= start_hour].head(24)

    if len(day_rows) < 24:
        remaining_needed = 24 - len(day_rows)
        last_ts   = pd.to_datetime(day_rows["timestamp"].iloc[-1])
        next_rows = sim_frame[
            pd.to_datetime(sim_frame["timestamp"]) > last_ts
        ].head(remaining_needed)
        day_rows = pd.concat([day_rows, next_rows]).reset_index(drop=True)

    day_df = day_rows.reset_index(drop=True)
    n      = len(day_df)

    actual_ts    = pd.to_datetime(day_df["timestamp"].iloc[0])
    actual_date  = actual_ts.strftime("%Y-%m-%d")
    day_display  = actual_ts.strftime("%A, %d %B %Y")
    end_ts       = actual_ts + pd.Timedelta(hours=n - 1)
    sched_period = (
        f"{actual_ts.strftime('%d %b %Y')} {start_hour:02d}:00 → "
        f"{end_ts.strftime('%d %b %Y')} {end_ts.strftime('%H')}:00"
    )

    app_preds = {
        col: day_df[col].values[:n]
        for col in day_df.columns
        if col.startswith("pred_")
        and "solar" not in col
        and "consumption" not in col
    }
    solar_fc = day_df["predicted_solar_kwh"].values[:n]
    prices   = day_df["price_eur_kwh"].values[:n]
    hours    = day_df["hour"].values[:n].astype(int)

    # Auto-build specs if none provided
    if specs is None:
        specs = []
        for col, vals in app_preds.items():
            key = col.replace("pred_", "").replace("_kwh", "")
            if key not in Config.APPL_NAMES:
                continue
            total_e = float(np.sum(vals))
            if total_e < 0.005:
                continue
            specs.append(ApplianceSpec(
                key=key, name=Config.APPL_NAMES[key],
                total_energy=total_e,
                duration_hours=max(total_e / 0.3, 1.0),
            ))

    lp_df, opt_cost, base_cost, lp_results = run_lp_day(
        app_preds, solar_fc, prices, hours,
        specs=specs,
        current_hour=current_hour,
        locked_before_t=locked_before_t,
    )

    # ── Build schedule_items ──────────────────────────────────
    schedule_items: list = []
    for key, res in lp_results.items():
        if res["total_energy"] < 0.005:
            continue
        opt          = np.array(res["optimized"])
        active_hours = sorted([int(hours[t]) for t in range(n) if opt[t] > 0.005])
        if not active_hours:
            continue

        best_t   = int(np.argmax(opt))
        best_h   = int(hours[best_t])
        price_at = float(prices[best_t])
        solar_at = float(solar_fc[best_t])
        is_free  = solar_at > float(opt[best_t])
        band     = get_price_band_from_price(price_at)

        net_at = (
            solar_at - float(lp_df.iloc[best_t]["total_load"])
            if best_t < len(lp_df) else 0.0
        )
        scenario, _ = get_recommendation(get_energy_state(net_at), band)

        schedule_items.append({
            "key":              key,
            "name":             res["name"],
            "scheduled_hour":   best_h,
            "active_hours":     active_hours,
            "total_energy":     round(float(res["total_energy"]), 4),
            "price_at_hour":    round(price_at, 4),
            "solar_at_hour":    round(solar_at, 4),
            "is_free":          bool(is_free),
            "price_band":       band,
            "scenario":         scenario,
            "shifted":          bool(res.get("shifted", False)),
            "color":            Config.APPL_COLORS.get(key, "#7F8C8D"),
            "status":           "waiting",
            "user_forced":      bool(res.get("is_user_fixed", False)),
            "smart_plug_event": None,
            "user_note":        "🔒 User-fixed" if res.get("is_user_fixed") else "",
        })

    schedule_items.sort(key=lambda x: x["scheduled_hour"])

    chart_data = [
        {
            "hour":        int(hours[t]),
            "solar":       round(float(solar_fc[t]), 4),
            "price":       round(float(prices[t]), 4),
            "price_band":  get_price_band_from_price(float(prices[t])),
            "consumption": round(float(day_df.iloc[t]["predicted_consumption_kwh"]), 4),
        }
        for t in range(n)
    ]

    saving = float(base_cost - opt_cost)

    logger.info(
        "Baseline: €%.4f  Optimized: €%.4f  Saving: €%.4f",
        base_cost, opt_cost, saving,
    )

    return {
        "generated_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        "actual_date":    actual_date,
        "day_display":    day_display,
        "sched_period":   sched_period,
        "start_hour":     int(start_hour),
        "schedule":       schedule_items,
        "chart_data":     chart_data,
        "baseline_cost":  round(float(base_cost), 4),
        "optimized_cost": round(float(opt_cost), 4),
        "daily_saving":   round(saving, 4),
        "lp_results_raw": lp_results,
        "hours_array":    [int(h) for h in hours],
        "solar_array":    [round(float(s), 4) for s in solar_fc],
        "prices_array":   [round(float(p), 4) for p in prices],
        "n_hours":        n,
    }


# ══════════════════════════════════════════════════════════════════
# Smart-plug / manual-override handler  (exact from notebook cell 12)
# ══════════════════════════════════════════════════════════════════

def handle_smart_plug_event(
    appliance_key:  str,
    detected_hour:  int,
    current_hour:   int,
    morning_data:   dict,
    sim_frame:      pd.DataFrame,
    trained_models: dict,
    event_type:     str = "unexpected",
    detected_time:  Optional[str] = None,
) -> dict:
    """
    Exact reproduction of notebook cell 12 handle_smart_plug_event().
    Locks the detected appliance to the reported hour (with sub-hourly
    cost proration), then re-runs the LP for all remaining appliances
    in remaining hours.
    """
    # Sub-hourly time parsing
    detected_minute = 0
    if detected_time is not None:
        detected_hour, detected_minute = parse_hhmm(detected_time)

    # Fraction of the detected hour actually used
    hour_fraction = (60 - detected_minute) / 60.0 if detected_minute > 0 else 1.0

    hours_arr  = np.array(morning_data["hours_array"])
    solar_arr  = np.array(morning_data["solar_array"]).copy()
    prices_arr = np.array(morning_data["prices_array"])
    lp_raw     = morning_data["lp_results_raw"]

    detected_idx_arr = np.where(hours_arr == detected_hour)[0]
    detected_idx     = int(detected_idx_arr[0]) if len(detected_idx_arr) > 0 else 0

    forced_res  = lp_raw.get(appliance_key)
    locked_item = None
    locked_cost = 0.0
    note        = ""

    if forced_res:
        total_e  = float(forced_res["total_energy"])
        price_at = (
            float(prices_arr[detected_idx]) if detected_idx < len(prices_arr) else 0.0
        )
        solar_at = (
            float(solar_arr[detected_idx]) if detected_idx < len(solar_arr) else 0.0
        )

        opt_arr       = np.array(forced_res["optimized"])
        lp_sched_h    = (
            int(hours_arr[np.argmax(opt_arr)]) if opt_arr.max() > 0.005 else None
        )
        grid_used     = max(total_e - solar_at, 0.0)
        locked_cost   = grid_used * price_at * hour_fraction

        if detected_idx < len(solar_arr):
            solar_arr[detected_idx] = max(solar_at - total_e, 0.0)

        appl_label = Config.APPL_NAMES.get(appliance_key, appliance_key)

        if event_type == "unexpected":
            if lp_sched_h and lp_sched_h != detected_hour:
                note = (
                    f"⚡ {appl_label} detected at {detected_hour:02d}:00 "
                    f"— LP had {lp_sched_h:02d}:00. "
                    f"Cost: {'FREE' if grid_used < 0.01 else f'€{locked_cost:.4f}'}. Rescheduling."
                )
            else:
                note = (
                    f"⚡ {appl_label} detected at {detected_hour:02d}:00. Rescheduling."
                )
        else:
            note = (
                f"👤 {appl_label} manually run at {detected_hour:02d}:00. "
                f"Cost: {'FREE' if grid_used < 0.01 else f'€{locked_cost:.4f}'}."
            )

        locked_item = {
            "key":              appliance_key,
            "name":             Config.APPL_NAMES.get(appliance_key, appliance_key),
            "scheduled_hour":   detected_hour,
            "scheduled_time":   detected_time if detected_time else f"{detected_hour:02d}:00",
            "active_hours":     [detected_hour],
            "hour_fraction":    hour_fraction,
            "total_energy":     round(total_e, 4),
            "price_at_hour":    round(price_at, 4),
            "solar_at_hour":    round(solar_at, 4),
            "is_free":          grid_used < 0.01,
            "price_band":       get_price_band_from_price(price_at),
            "scenario":         "DANGER_WINDOW" if price_at > 0 else "BALANCED_VALLE",
            "shifted":          False,
            "color":            Config.APPL_COLORS.get(appliance_key, "#7F8C8D"),
            "status":           "overridden",
            "user_forced":      True,
            "smart_plug_event": event_type,
            "user_note":        note,
        }
        logger.info(
            "⚡ PLUG EVENT: %s at %02d:00 | cost=%.4f",
            Config.APPL_NAMES.get(appliance_key), detected_hour, locked_cost,
        )

    # ── Remaining hours and appliances ────────────────────────
    remaining_mask = hours_arr >= current_hour
    rem_hours      = hours_arr[remaining_mask]
    rem_solar      = solar_arr[remaining_mask]
    rem_prices     = prices_arr[remaining_mask]
    n_rem          = int(sum(remaining_mask))

    if n_rem == 0:
        return {
            "rescheduled_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "event_type":     event_type,
            "trigger":        note,
            "schedule":       [locked_item] if locked_item else [],
            "new_cost":       round(locked_cost, 4),
            "daily_saving":   0.0,
            "baseline_cost":  morning_data.get("baseline_cost", 0),
            "chart_data":     morning_data["chart_data"],
            "hours_array":    morning_data["hours_array"],
            "solar_array":    morning_data["solar_array"],
            "prices_array":   morning_data["prices_array"],
        }

    # ── Build remaining appliance predictions ─────────────────
    app_preds_remaining: dict     = {}
    remaining_specs:     list     = []

    if "fridge_kwh" in trained_models:
        fi = trained_models["fridge_kwh"]
        fp = np.clip(
            fi["model"].predict(fi["test"][fi["features"]]), 0, None
        )
        nf  = min(len(fp), len(hours_arr))
        fa  = fp[:nf]
        app_preds_remaining["pred_fridge_kwh"] = (
            fa[remaining_mask]
            if len(fa) >= len(hours_arr)
            else np.full(n_rem, 0.037)
        )

    for key, res in lp_raw.items():
        if key == appliance_key:
            continue
        orig_opt  = np.array(res["optimized"])
        rem_opt   = (
            orig_opt[remaining_mask]
            if len(orig_opt) >= len(hours_arr)
            else np.zeros(n_rem)
        )
        total_rem = float(rem_opt.sum())
        if total_rem < 0.005:
            continue
        app_preds_remaining[f"pred_{key}_kwh"] = rem_opt
        remaining_specs.append(ApplianceSpec(
            key=key,
            name=Config.APPL_NAMES.get(key, key),
            total_energy=total_rem,
            duration_hours=max(total_rem / 0.3, 1.0),
        ))

    new_lp_results: dict = {}
    new_opt_cost         = locked_cost

    if app_preds_remaining and n_rem > 0:
        _, opt_c, _, new_lp_results = run_lp_day(
            app_preds_remaining, rem_solar, rem_prices, rem_hours,
            specs=remaining_specs, current_hour=current_hour,
        )
        new_opt_cost += opt_c

    # ── Assemble updated schedule ─────────────────────────────
    new_schedule: list = []
    if locked_item:
        new_schedule.append(locked_item)

    for key, res in new_lp_results.items():
        if res["total_energy"] < 0.005:
            continue
        base_key = key.replace("pred_", "").replace("_kwh", "")
        opt      = np.array(res["optimized"])
        best_t   = int(np.argmax(opt))
        best_h   = int(rem_hours[best_t]) if best_t < len(rem_hours) else current_hour
        active   = [int(rem_hours[t]) for t in range(len(opt)) if opt[t] > 0.005]
        price_at = float(rem_prices[best_t]) if best_t < len(rem_prices) else 0.0
        solar_at = float(rem_solar[best_t])  if best_t < len(rem_solar)  else 0.0

        new_schedule.append({
            "key":              base_key,
            "name":             res["name"],
            "scheduled_hour":   best_h,
            "active_hours":     active,
            "total_energy":     round(float(res["total_energy"]), 4),
            "price_at_hour":    round(price_at, 4),
            "solar_at_hour":    round(solar_at, 4),
            "is_free":          solar_at > float(opt[best_t]),
            "price_band":       get_price_band_from_price(price_at),
            "scenario":         "BALANCED_VALLE",
            "shifted":          True,
            "color":            Config.APPL_COLORS.get(base_key, "#7F8C8D"),
            "status":           "rescheduled",
            "user_forced":      False,
            "smart_plug_event": None,
            "user_note":        (
                f"Rescheduled after "
                f"{Config.APPL_NAMES.get(appliance_key, appliance_key)} event"
            ),
        })

    new_schedule.sort(key=lambda x: x["scheduled_hour"])

    logger.info("✅ UPDATED SCHEDULE (from %02d:00):", current_hour)
    for item in new_schedule:
        tag  = "← EVENT" if item["user_forced"] else "rescheduled"
        cost = "FREE ☀️" if item["is_free"] else f"€{item['price_at_hour']:.4f}"
        logger.info(
            "   %02d:00  %-20s  %s  %s",
            item["scheduled_hour"], item["name"], cost, tag,
        )

    return {
        "rescheduled_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "event_type":     event_type,
        "trigger":        note,
        "schedule":       new_schedule,
        "new_cost":       round(new_opt_cost, 4),
        "baseline_cost":  morning_data.get("baseline_cost", 0),
        "daily_saving":   round(
            morning_data.get("baseline_cost", 0) - new_opt_cost, 4
        ),
        "chart_data":     morning_data["chart_data"],
        "hours_array":    morning_data["hours_array"],
        "solar_array":    morning_data["solar_array"],
        "prices_array":   morning_data["prices_array"],
    }
