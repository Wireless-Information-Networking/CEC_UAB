"""
train_models.py — one-shot training pipeline.

Run from the project root:
    python -m app.train_models            # train if models absent
    python -m app.train_models --force    # always retrain

Produces four artefacts under MODELS_DIR:
    trained_models.pkl   — dict of {target: {model, features, test}}
    solar_model.pkl      — LightGBM solar forecaster
    sim_frame.pkl        — pre-built simulation DataFrame
    price_meta.pkl       — {p33, p67, df_fac}
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error, r2_score

# Allow running as `python -m app.train_models` or `python app/train_models.py`
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Config
from app.utils import (
    ConstantPredictor,
    get_price_band,
    get_price_weight,
    set_price_thresholds,
    get_energy_state,
    get_recommendation,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# 1 — PRICE DATA
# ══════════════════════════════════════════════════════════════════

def load_price_data() -> tuple[pd.DataFrame, float, float]:
    logger.info("Loading PVPC price data …")

    df_fac = pd.read_excel(Config.PRICE_FACTURACION)
    df_exc = pd.read_excel(Config.PRICE_EXCEDENTE)   # loaded for completeness
    df_mer = pd.read_excel(Config.PRICE_MERCADO)     # loaded for completeness

    df_fac.columns = ["hora", "price_facturacion"]
    df_exc.columns = ["hora", "price_excedente"]
    df_mer.columns = ["hora", "price_mercado"]

    # EUR/MWh → EUR/kWh
    df_fac["price_facturacion"] /= 1000
    df_exc["price_excedente"]   /= 1000
    df_mer["price_mercado"]     /= 1000

    df_fac = df_fac.reset_index(drop=True)
    df_fac["timestamp"] = pd.date_range(
        start="2023-01-01 00:00:00",
        periods=len(df_fac),
        freq="h",
    )
    df_fac["hour"] = df_fac["timestamp"].dt.hour

    p33 = float(df_fac["price_facturacion"].quantile(0.33))
    p67 = float(df_fac["price_facturacion"].quantile(0.67))
    set_price_thresholds(p33, p67)

    df_fac["price_band"]   = df_fac["price_facturacion"].apply(get_price_band)
    df_fac["price_weight"] = df_fac["price_facturacion"].apply(get_price_weight)

    logger.info(
        "Prices: %d rows | €%.4f–%.4f | p33=%.4f p67=%.4f",
        len(df_fac),
        df_fac["price_facturacion"].min(),
        df_fac["price_facturacion"].max(),
        p33, p67,
    )
    return df_fac, p33, p67


# ══════════════════════════════════════════════════════════════════
# 2 — HOUSE DATA
# ══════════════════════════════════════════════════════════════════

def load_house_data(df_fac: pd.DataFrame) -> pd.DataFrame:
    logger.info("Loading house data (chunked) …")

    raw_cols = ["timestamp", "P_agg", "ac_1", "ac_2", "boiler", "fridge", "washing_machine"]
    chunks   = []

    for chunk in pd.read_csv(Config.HOUSE_PATH, chunksize=500_000):
        chunk["timestamp"] = pd.to_datetime(chunk["timestamp"], errors="coerce")
        chunk = chunk.dropna(subset=["timestamp"])
        keep  = [c for c in raw_cols if c in chunk.columns]
        chunk = chunk[keep]
        for col in ["ac_1", "ac_2", "boiler", "fridge", "washing_machine"]:
            if col in chunk.columns:
                chunk[col] = chunk[col].fillna(0)
        chunks.append(chunk)

    house_raw = (
        pd.concat(chunks, ignore_index=True)
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    logger.info("Raw rows: %d", len(house_raw))

    # ── Hourly resample ───────────────────────────────────────
    house_hourly = (
        house_raw.set_index("timestamp")
        .resample("h").mean()
        .reset_index()
    )

    # ── Unit conversion: W (mean of 1-min samples) → kWh ─────
    def _convert(df: pd.DataFrame, raw: str, new: str) -> pd.DataFrame:
        if raw not in df.columns:
            return df
        m       = df[raw].mean()
        df[new] = df[raw] / 1000 if m > 0.5 else df[raw].clip(lower=0)
        logger.info("  %-22s mean=%.5f → new_col=%s", raw, m, new)
        return df

    house_hourly = _convert(house_hourly, "P_agg",           "consumption_kwh")
    house_hourly = _convert(house_hourly, "ac_1",            "ac1_kwh")
    house_hourly = _convert(house_hourly, "ac_2",            "ac2_kwh")
    house_hourly = _convert(house_hourly, "boiler",          "boiler_kwh")
    house_hourly = _convert(house_hourly, "fridge",          "fridge_kwh")
    house_hourly = _convert(house_hourly, "washing_machine", "wm_kwh")

    drop_cols = ["P_agg", "ac_1", "ac_2", "boiler", "fridge", "washing_machine"]
    house_hourly.drop(
        columns=[c for c in drop_cols if c in house_hourly.columns],
        inplace=True,
    )
    house_hourly.dropna(subset=["consumption_kwh"], inplace=True)
    house_hourly.reset_index(drop=True, inplace=True)

    # ── Time features ─────────────────────────────────────────
    ts = house_hourly["timestamp"]
    house_hourly["hour"]        = ts.dt.hour
    house_hourly["dayofweek"]   = ts.dt.dayofweek
    house_hourly["month"]       = ts.dt.month
    house_hourly["day_of_year"] = ts.dt.dayofyear

    # ── Merge real PVPC price ─────────────────────────────────
    house_hourly = house_hourly.merge(
        df_fac[["timestamp", "price_facturacion", "price_band", "price_weight"]],
        on="timestamp",
        how="left",
    ).rename(columns={"price_facturacion": "price_eur_kwh"})

    logger.info("house_hourly shape: %s", house_hourly.shape)
    return house_hourly


# ══════════════════════════════════════════════════════════════════
# 3 — SOLAR DATA
# ══════════════════════════════════════════════════════════════════

def load_solar_data() -> pd.DataFrame:
    logger.info("Loading solar data …")

    solar_raw = pd.read_csv(Config.SOLAR_PATH)
    solar_raw["timestamp"] = pd.to_datetime(solar_raw["timestamp"], errors="coerce")
    solar_raw = solar_raw.dropna(subset=["timestamp"])
    solar_raw = solar_raw.rename(columns={"generation": "solar_kwh"})
    solar_raw["solar_kwh"] = solar_raw["solar_kwh"].clip(lower=0)
    solar_raw["timestamp"] = solar_raw["timestamp"].dt.floor("h")

    solar_hourly = (
        solar_raw[["timestamp", "solar_kwh"]]
        .drop_duplicates("timestamp")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    if solar_hourly["solar_kwh"].max() > 100:
        solar_hourly["solar_kwh"] /= 1000
        logger.info("Converted solar Wh → kWh")

    solar_hourly["solar_kwh"] /= Config.N_HOUSES

    logger.info(
        "Solar: %d rows | max per-house %.3f kWh/h",
        len(solar_hourly),
        solar_hourly["solar_kwh"].max(),
    )
    return solar_hourly


# ══════════════════════════════════════════════════════════════════
# 4 — FEATURE ENGINEERING
# ══════════════════════════════════════════════════════════════════

def build_features(df: pd.DataFrame, target: str) -> pd.DataFrame:
    d = df.copy().sort_values("timestamp").reset_index(drop=True)

    ts = d["timestamp"]
    d["hour"]        = ts.dt.hour
    d["dayofweek"]   = ts.dt.dayofweek
    d["month"]       = ts.dt.month
    d["day_of_year"] = ts.dt.dayofyear
    d["is_weekend"]  = d["dayofweek"].isin([5, 6]).astype(int)

    d["is_high_price"] = (d["price_band"] == "HIGH").astype(int)
    d["is_low_price"]  = (d["price_band"] == "LOW").astype(int)
    d["is_morning"]    = d["hour"].between(6, 10).astype(int)
    d["is_evening"]    = d["hour"].between(17, 22).astype(int)
    d["is_summer"]     = d["month"].isin([6, 7, 8, 9]).astype(int)
    d["is_winter"]     = d["month"].isin([12, 1, 2, 3]).astype(int)

    d["hour_sin"]  = np.sin(2 * np.pi * d["hour"] / 24)
    d["hour_cos"]  = np.cos(2 * np.pi * d["hour"] / 24)
    d["dow_sin"]   = np.sin(2 * np.pi * d["dayofweek"] / 7)
    d["dow_cos"]   = np.cos(2 * np.pi * d["dayofweek"] / 7)
    d["month_sin"] = np.sin(2 * np.pi * d["month"] / 12)
    d["month_cos"] = np.cos(2 * np.pi * d["month"] / 12)

    s = d[target].shift(1)
    for lag in [1, 2, 3, 24, 168]:
        d[f"lag_{lag}h"] = d[target].shift(lag)

    d["roll_mean_6h"]   = s.rolling(6,   min_periods=3).mean()
    d["roll_mean_3h"]   = s.rolling(3,   min_periods=1).mean()
    d["roll_mean_24h"]  = s.rolling(24,  min_periods=12).mean()
    d["roll_std_24h"]   = s.rolling(24,  min_periods=12).std().fillna(0)
    d["roll_mean_168h"] = s.rolling(168, min_periods=48).mean()
    d["diff_1h"]        = d[target].shift(1).diff(1)
    d["diff_24h"]       = d[target].shift(24).diff(24)

    if target != "consumption_kwh" and "consumption_kwh" in d.columns:
        d["total_cons_lag1"]   = d["consumption_kwh"].shift(1)
        d["total_cons_roll24"] = (
            d["consumption_kwh"].shift(1).rolling(24, min_periods=6).mean()
        )

    return d.dropna().reset_index(drop=True)


def build_solar_features(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy().sort_values("timestamp").reset_index(drop=True)

    ts = d["timestamp"]
    d["hour"]        = ts.dt.hour
    d["dayofweek"]   = ts.dt.dayofweek
    d["month"]       = ts.dt.month
    d["day_of_year"] = ts.dt.dayofyear

    d["is_daylight"]   = d["hour"].between(6, 21).astype(int)
    d["is_peak_solar"] = d["hour"].between(10, 15).astype(int)

    d["hour_sin"]  = np.sin(2 * np.pi * d["hour"] / 24)
    d["hour_cos"]  = np.cos(2 * np.pi * d["hour"] / 24)
    d["month_sin"] = np.sin(2 * np.pi * d["month"] / 12)
    d["month_cos"] = np.cos(2 * np.pi * d["month"] / 12)

    d["solar_lag_1h"]  = d["solar_kwh"].shift(1)
    d["solar_lag_24h"] = d["solar_kwh"].shift(24)

    return d.dropna().reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════
# 5 — TRAIN APPLIANCE MODELS
# ══════════════════════════════════════════════════════════════════

def train_all_models(house_hourly: pd.DataFrame) -> dict:
    logger.info("Training appliance models …")

    feat_datasets: dict = {}
    feature_lists: dict = {}

    for target in Config.ALL_TARGETS:
        if target not in house_hourly.columns:
            logger.warning("Column %s missing — skipping.", target)
            continue
        fd   = build_features(house_hourly, target)
        feat_datasets[target] = fd
        feats = [f for f in Config.BASE_FEATURES if f in fd.columns]
        if target != "consumption_kwh":
            for x in ["total_cons_lag1", "total_cons_roll24"]:
                if x in fd.columns:
                    feats.append(x)
        feature_lists[target] = feats

    trained_models: dict = {}

    # ── Fridge: constant predictor ────────────────────────────
    if "fridge_kwh" in feat_datasets:
        fd       = feat_datasets["fridge_kwh"]
        sp       = int(len(fd) * 0.8)
        mean_val = float(fd.iloc[:sp]["fridge_kwh"].mean())
        te       = fd.iloc[sp:]
        trained_models["fridge_kwh"] = {
            "model":    ConstantPredictor(mean_val),
            "features": feature_lists["fridge_kwh"],
            "test":     te,
        }
        logger.info("  fridge_kwh: ConstantPredictor(%.5f)", mean_val)

    # ── XGBoost for all other appliances ──────────────────────
    for target, cfg in Config.XGB_CONFIGS.items():
        if target not in feat_datasets:
            continue

        fd  = feat_datasets[target]
        fs  = feature_lists[target]
        sp  = int(len(fd) * 0.8)
        tr  = fd.iloc[:sp]
        te  = fd.iloc[sp:]
        Xtr, ytr = tr[fs], tr[target]
        Xte, yte = te[fs], te[target]

        model = xgb.XGBRegressor(**cfg)
        model.fit(Xtr, ytr)

        upper    = float(ytr.quantile(0.99))
        raw_pred = np.clip(model.predict(Xte), 0, upper)
        last_val = yte.shift(1).bfill().values
        pred     = 0.7 * raw_pred + 0.3 * last_val

        mae = mean_absolute_error(yte, pred)
        r2  = r2_score(yte, pred)
        logger.info(
            "  %-20s  MAE=%.4f  R²=%.3f  test=%d rows",
            target, mae, r2, len(te),
        )

        trained_models[target] = {
            "model":    model,
            "features": fs,
            "train":    tr,
            "test":     te,
        }

    return trained_models


# ══════════════════════════════════════════════════════════════════
# 6 — TRAIN SOLAR MODEL
# ══════════════════════════════════════════════════════════════════

def train_solar_model(solar_hourly: pd.DataFrame):
    logger.info("Training solar forecasting model …")

    sf = build_solar_features(solar_hourly)
    sp = int(len(sf) * 0.8)
    s_tr, s_te = sf.iloc[:sp], sf.iloc[sp:]

    model = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, verbose=-1)
    model.fit(
        s_tr[Config.SOLAR_FEATURES], s_tr["solar_kwh"],
        callbacks=[lgb.early_stopping(50, verbose=False),
                   lgb.log_evaluation(period=-1)],
        eval_set=[(s_te[Config.SOLAR_FEATURES], s_te["solar_kwh"])],
    )

    pred = np.clip(model.predict(s_te[Config.SOLAR_FEATURES]), 0, None)
    mae  = mean_absolute_error(s_te["solar_kwh"], pred)
    logger.info("  solar MAE=%.4f", mae)

    return model, sf, s_te, pred


# ══════════════════════════════════════════════════════════════════
# 7 — BUILD SIMULATION FRAME
# ══════════════════════════════════════════════════════════════════

def build_sim_frame(
    trained_models: dict,
    solar_pred: np.ndarray,
    df_fac: pd.DataFrame,
) -> pd.DataFrame:
    logger.info("Building simulation frame …")

    ci  = trained_models["consumption_kwh"]
    ct  = ci["test"]
    ytr = ci["train"]["consumption_kwh"]

    upper    = float(ytr.quantile(0.99))
    raw_pred = np.clip(ci["model"].predict(ct[ci["features"]]), 0, upper)
    last_val = ct["consumption_kwh"].shift(1).bfill().values
    y_pc     = 0.7 * raw_pred + 0.3 * last_val
    n        = len(y_pc)

    sim = pd.DataFrame({
        "timestamp":                 ct["timestamp"].values,
        "actual_consumption_kwh":    ct["consumption_kwh"].values,
        "predicted_consumption_kwh": y_pc,
    })

    n_solar = min(len(solar_pred), n)
    sim     = sim.iloc[:n_solar].copy()
    sim["predicted_solar_kwh"] = solar_pred[:n_solar]

    # ── Per-appliance predictions ─────────────────────────────
    for t in ["ac1_kwh", "ac2_kwh", "boiler_kwh", "fridge_kwh", "wm_kwh"]:
        if t not in trained_models:
            continue
        info   = trained_models[t]
        raw_p  = np.clip(info["model"].predict(info["test"][info["features"]]), 0, 2.0)
        last_v = info["test"][t].shift(1).bfill().values
        preds  = 0.7 * raw_p + 0.3 * last_v
        sim[f"pred_{t}"] = preds[: len(sim)]

    # ── Time features ─────────────────────────────────────────
    ts = pd.to_datetime(sim["timestamp"])
    sim["hour"]      = ts.dt.hour
    sim["dayofweek"] = ts.dt.dayofweek
    sim["month"]     = ts.dt.month

    # ── PVPC price (mapped from real timestamps) ──────────────
    price_map             = df_fac.set_index("timestamp")["price_facturacion"]
    sim["price_eur_kwh"]  = sim["timestamp"].map(price_map).ffill()
    sim["price_band"]     = sim["price_eur_kwh"].apply(get_price_band)
    sim["price_weight"]   = sim["price_eur_kwh"].apply(get_price_weight)

    # ── Energy balance ────────────────────────────────────────
    sim["net_energy_kwh"]   = sim["predicted_solar_kwh"] - sim["predicted_consumption_kwh"]
    sim["energy_state"]     = sim["net_energy_kwh"].apply(get_energy_state)
    sim["opportunity_score"]= sim["predicted_solar_kwh"] * sim["price_weight"]

    sim["scenario"], sim["recommendation"] = zip(*sim.apply(
        lambda r: get_recommendation(r["energy_state"], r["price_band"]), axis=1
    ))

    sim["is_golden_window"] = (sim["energy_state"] == "SURPLUS") & (sim["price_band"] == "HIGH")
    sim["is_danger_window"] = (sim["energy_state"] == "DEFICIT") & (sim["price_band"] == "HIGH")

    logger.info(
        "sim: %s rows | golden=%d danger=%d",
        len(sim),
        sim["is_golden_window"].sum(),
        sim["is_danger_window"].sum(),
    )
    return sim


# ══════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════

def run_training(force: bool = False) -> None:
    Config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    Config.LOG_DIR.mkdir(parents=True, exist_ok=True)

    if not force and Config.SIM_FRAME_PATH.exists():
        logger.info(
            "Artefacts already present at %s. Use --force to retrain.",
            Config.MODELS_DIR,
        )
        return

    logger.info("=== Training pipeline START ===")

    # Validate data files exist
    for path in [Config.HOUSE_PATH, Config.SOLAR_PATH, Config.PRICE_FACTURACION]:
        if not path.exists():
            raise FileNotFoundError(
                f"Required data file not found: {path}\n"
                "Place your CSV/XLSX files in the data/ directory."
            )

    df_fac, p33, p67  = load_price_data()
    house_hourly       = load_house_data(df_fac)
    solar_hourly       = load_solar_data()
    trained_models     = train_all_models(house_hourly)
    solar_model, _, s_te, sp = train_solar_model(solar_hourly)
    sim = build_sim_frame(trained_models, sp, df_fac)

    logger.info("Persisting artefacts …")
    joblib.dump(trained_models, Config.TRAINED_MODELS_PATH, compress=3)
    joblib.dump(solar_model,    Config.SOLAR_MODEL_PATH,    compress=3)
    joblib.dump(sim,            Config.SIM_FRAME_PATH,      compress=3)
    joblib.dump({"p33": p33, "p67": p67, "df_fac": df_fac}, Config.PRICE_META_PATH, compress=3)

    logger.info("=== Training pipeline COMPLETE ===")
    logger.info("  %s", Config.TRAINED_MODELS_PATH)
    logger.info("  %s", Config.SOLAR_MODEL_PATH)
    logger.info("  %s", Config.SIM_FRAME_PATH)
    logger.info("  %s", Config.PRICE_META_PATH)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train energy-optimisation models")
    parser.add_argument("--force", action="store_true", help="Retrain even if artefacts exist")
    args = parser.parse_args()
    run_training(force=args.force)
