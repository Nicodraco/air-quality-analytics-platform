"""
Predicción de tendencias de contaminación con Random Forest por zona.

Entrena con histórico diario (hasta 3 meses) y pronostica los próximos días
por región/zona.
"""

import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from src.config import FORECAST_DAYS, ML_MIN_TRAINING_DAYS, MODELS_DIR, SILVER_DIR, ensure_dirs
from src.gold.loader import query_facts


warnings.filterwarnings("ignore")

NUMERIC_COLS = [
    "pm25", "pm10", "no2", "so2", "o3", "co", "aqi_index",
    "temperature", "humidity", "precipitation", "wind_speed",
]
EXCLUDE_FEATURES = {
    "measured_at", "station_id", "station_name", "source", "station_type",
    "region", "municipality", "latitude", "longitude", "country",
    "pm10", "pm25", "no2", "so2", "o3", "co", "aqi_index",
    "temperature", "humidity", "precipitation", "wind_speed",
    "target_value",
}


def load_training_data() -> pd.DataFrame:
    """Carga histórico para ML priorizando Silver (histórico acumulado)."""
    frames: list[pd.DataFrame] = []

    weather_path = SILVER_DIR / "silver_weather.parquet"
    air_path = SILVER_DIR / "silver_air_quality.parquet"
    if weather_path.exists():
        w = pd.read_parquet(weather_path)
        w = w.rename(columns={"timestamp": "measured_at"})
        frames.append(w)
    if air_path.exists():
        a = pd.read_parquet(air_path)
        a = a.rename(columns={"timestamp": "measured_at"})
        frames.append(a)

    if frames:
        df = pd.concat(frames, ignore_index=True)
        df["measured_at"] = pd.to_datetime(df["measured_at"], utc=True)
        dedup_cols = [c for c in ["station_id", "source", "measured_at"] if c in df.columns]
        if len(dedup_cols) >= 2:
            df = df.drop_duplicates(subset=dedup_cols, keep="last")
        return df.sort_values("measured_at")

    gold_df = query_facts(limit=50000)
    if gold_df.empty:
        return pd.DataFrame()
    gold_df["measured_at"] = pd.to_datetime(gold_df["measured_at"], utc=True)
    return gold_df.sort_values("measured_at")


def _pick_target(df: pd.DataFrame) -> str:
    for col in ["pm25", "no2", "pm10", "aqi_index"]:
        if col in df.columns and df[col].notna().sum() >= 10:
            return col
    return "pm25"


def aggregate_zone_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega mediciones a nivel diario por región/zona."""
    data = df.copy()
    data["measured_at"] = pd.to_datetime(data["measured_at"], utc=True)
    data["date"] = data["measured_at"].dt.floor("D")

    if "region" not in data.columns:
        data["region"] = "Desconocida"
    data["region"] = data["region"].fillna("Desconocida")

    cols = [c for c in NUMERIC_COLS if c in data.columns]
    if not cols:
        return pd.DataFrame()

    daily = (
        data.groupby(["region", "date"], as_index=False)[cols]
        .mean()
        .rename(columns={"date": "measured_at"})
        .sort_values(["region", "measured_at"])
    )
    return daily


def _add_lag_features(g: pd.DataFrame, target: str) -> pd.DataFrame:
    series = g[target].ffill().bfill()
    for w in [3, 7, 14]:
        g[f"{target}_ma_{w}"] = series.rolling(w, min_periods=1).mean()
    g[f"{target}_lag_1"] = series.shift(1)
    g[f"{target}_lag_7"] = series.shift(7)

    ts = g["measured_at"]
    g["day_of_week"] = ts.dt.dayofweek
    g["month"] = ts.dt.month
    g["day_sin"] = np.sin(2 * np.pi * ts.dt.dayofyear / 365)
    g["day_cos"] = np.cos(2 * np.pi * ts.dt.dayofyear / 365)
    return g


def build_zone_training_frame(
    zone_df: pd.DataFrame, target: str, forecast_days: int
) -> pd.DataFrame:
    """Expande el histórico con horizontes de predicción (1..N días)."""
    g = zone_df.sort_values("measured_at").copy()
    g = _add_lag_features(g, target)
    series = g[target].ffill().bfill()

    rows = []
    for horizon in range(1, forecast_days + 1):
        chunk = g.copy()
        chunk["horizon_days"] = horizon
        chunk["target_value"] = series.shift(-horizon)
        rows.append(chunk)

    expanded = pd.concat(rows, ignore_index=True)
    return expanded.dropna(subset=["target_value"])


def build_zone_inference_frame(
    zone_df: pd.DataFrame, target: str, forecast_days: int
) -> pd.DataFrame:
    """Construye filas de inferencia para los próximos N días."""
    g = zone_df.sort_values("measured_at").copy()
    g = _add_lag_features(g, target)
    last = g.iloc[-1:].copy()
    last_ts = last["measured_at"].iloc[0]

    rows = []
    for horizon in range(1, forecast_days + 1):
        row = last.copy()
        future_ts = last_ts + pd.Timedelta(days=horizon)
        row["measured_at"] = future_ts
        row["horizon_days"] = horizon
        row["day_of_week"] = future_ts.dayofweek
        row["month"] = future_ts.month
        row["day_sin"] = np.sin(2 * np.pi * future_ts.dayofyear / 365)
        row["day_cos"] = np.cos(2 * np.pi * future_ts.dayofyear / 365)
        rows.append(row)

    return pd.concat(rows, ignore_index=True)


def _select_feature_cols(featured: pd.DataFrame) -> list[str]:
    return [
        c for c in featured.columns
        if c not in EXCLUDE_FEATURES
        and featured[c].dtype in [np.float64, np.int64, np.float32, np.int32]
        and featured[c].notna().sum() > len(featured) * 0.3
    ]


def train_and_predict_by_zone(
    df: pd.DataFrame,
    forecast_days: int | None = None,
) -> dict | None:
    """Entrena un modelo por zona y genera pronósticos diarios."""
    forecast_days = forecast_days or FORECAST_DAYS
    daily = aggregate_zone_daily(df)
    if daily.empty:
        print("[ML] No hay datos agregados por zona")
        return None

    all_forecasts: list[dict] = []
    metrics_by_zone: dict[str, dict] = {}
    models_by_zone: dict[str, dict] = {}
    min_days = max(ML_MIN_TRAINING_DAYS, forecast_days * 3)

    for region in sorted(daily["region"].dropna().unique()):
        zone_df = daily[daily["region"] == region].copy()
        zone_days = len(zone_df)
        if zone_days < min_days:
            print(
                f"[ML] {region}: datos insuficientes ({zone_days} días, mínimo {min_days}). "
                f"Ejecuta el pipeline completo para cargar {ML_MIN_TRAINING_DAYS}+ días de histórico."
            )
            continue

        target = _pick_target(zone_df)
        featured = build_zone_training_frame(zone_df, target, forecast_days)
        feature_cols = _select_feature_cols(featured)

        if len(featured) < 30 or not feature_cols:
            print(f"[ML] {region}: features insuficientes")
            continue

        X = featured[feature_cols].fillna(0)
        y = featured["target_value"]

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=0.2, shuffle=False
        )

        model = RandomForestRegressor(
            n_estimators=120, max_depth=10, random_state=42, n_jobs=-1
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        metrics = {
            "target": target,
            "mae": float(mean_absolute_error(y_test, y_pred)),
            "rmse": float(np.sqrt(mean_squared_error(y_test, y_pred))),
            "r2": float(r2_score(y_test, y_pred)),
            "training_days": len(zone_df),
        }
        metrics_by_zone[region] = metrics
        print(f"[ML] {region} ({target}): MAE={metrics['mae']:.2f}, R²={metrics['r2']:.3f}")

        inference = build_zone_inference_frame(zone_df, target, forecast_days)
        X_inf = inference[feature_cols].fillna(0)
        preds = model.predict(scaler.transform(X_inf))

        last_date = zone_df["measured_at"].max()
        for i, horizon in enumerate(range(1, forecast_days + 1)):
            forecast_ts = last_date + pd.Timedelta(days=horizon)
            all_forecasts.append({
                "region": region,
                "forecast_date": forecast_ts.date().isoformat(),
                "day_ahead": horizon,
                "target": target,
                "predicted_value": round(max(0.0, float(preds[i])), 2),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            })

        models_by_zone[region] = {
            "model": model,
            "scaler": scaler,
            "features": feature_cols,
            "target": target,
        }

    if not all_forecasts:
        print("[ML] No se generaron pronósticos por zona")
        return None

    ensure_dirs()
    forecast_df = pd.DataFrame(all_forecasts)
    forecast_df.to_csv(MODELS_DIR / "zone_forecasts.csv", index=False)
    forecast_df.to_csv(MODELS_DIR / "forecasts.csv", index=False)

    joblib.dump(metrics_by_zone, MODELS_DIR / "zone_metrics.joblib")
    joblib.dump(
        {k: {"features": v["features"], "target": v["target"]} for k, v in models_by_zone.items()},
        MODELS_DIR / "zone_models_meta.joblib",
    )

    # Guardar un modelo representativo para compatibilidad
    first_zone = next(iter(models_by_zone.values()))
    joblib.dump(first_zone["model"], MODELS_DIR / "rf_model.joblib")
    joblib.dump(first_zone["scaler"], MODELS_DIR / "rf_scaler.joblib")
    joblib.dump(
        {"features": first_zone["features"], "target": first_zone["target"]},
        MODELS_DIR / "rf_meta.joblib",
    )

    print(f"[ML] Pronósticos por zona guardados: {MODELS_DIR / 'zone_forecasts.csv'}")
    return {"metrics_by_zone": metrics_by_zone, "forecasts": all_forecasts}


def load_zone_forecasts() -> pd.DataFrame:
    path = MODELS_DIR / "zone_forecasts.csv"
    if path.exists():
        return pd.read_csv(path)
    legacy = MODELS_DIR / "forecasts.csv"
    if legacy.exists():
        return pd.read_csv(legacy)
    return pd.DataFrame()


def train_and_predict(df: pd.DataFrame, horizons: list[int] | None = None):
    """Compatibilidad con dashboard: delega en predicción por zona."""
    result = train_and_predict_by_zone(df, forecast_days=FORECAST_DAYS)
    if not result:
        return None

    first_metrics = next(iter(result["metrics_by_zone"].values()))
    forecasts_by_hours = {}
    for row in result["forecasts"]:
        if row["day_ahead"] not in {1, 2, 7}:
            continue
        hours = row["day_ahead"] * 24
        forecasts_by_hours[f"{hours}h"] = {
            "hours": hours,
            "predicted_value": row["predicted_value"],
            "target": row["target"],
            "region": row["region"],
            "forecast_time": (
                datetime.fromisoformat(row["forecast_date"]).replace(tzinfo=timezone.utc)
                + timedelta(hours=12)
            ).isoformat(),
        }

    return {
        "metrics": first_metrics,
        "metrics_by_zone": result["metrics_by_zone"],
        "forecasts": forecasts_by_hours,
        "zone_forecasts": result["forecasts"],
    }


def run_ml_pipeline():
    df = load_training_data()
    if df.empty:
        print("[ML] No hay datos para entrenar")
        return None
    return train_and_predict_by_zone(df)


if __name__ == "__main__":
    run_ml_pipeline()
