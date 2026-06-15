"""
Predicción de tendencias de contaminación con Random Forest.

Horizontes: 24 h, 48 h, 7 días.
Variables: clima + históricos de contaminantes.
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

from src.config import MODELS_DIR, SILVER_DIR, ensure_dirs
from src.gold.loader import query_facts


warnings.filterwarnings("ignore")


def load_training_data() -> pd.DataFrame:
    df = query_facts(limit=10000)
    if not df.empty:
        return df

    weather_path = SILVER_DIR / "silver_weather.parquet"
    air_path = SILVER_DIR / "silver_air_quality.parquet"
    frames = []
    if weather_path.exists():
        w = pd.read_parquet(weather_path)
        w = w.rename(columns={"timestamp": "measured_at"})
        frames.append(w)
    if air_path.exists():
        a = pd.read_parquet(air_path)
        a = a.rename(columns={"timestamp": "measured_at"})
        frames.append(a)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def prepare_features(df: pd.DataFrame, target: str = "pm25") -> pd.DataFrame:
    data = df.copy()
    data["measured_at"] = pd.to_datetime(data["measured_at"], utc=True)
    data = data.sort_values("measured_at")

    if target not in data.columns or data[target].notna().sum() < 10:
        for alt in ["no2", "pm10", "pm25", "o3"]:
            if alt in data.columns and data[alt].notna().sum() >= 10:
                target = alt
                break

    group_col = "station_id" if "station_id" in data.columns else None
    groups = [data] if not group_col else [g for _, g in data.groupby(group_col)]

    result = []
    for g in groups:
        g = g.sort_values("measured_at").copy()
        series = g[target].ffill().bfill()

        for w in [3, 7, 14]:
            g[f"{target}_ma_{w}"] = series.rolling(w, min_periods=1).mean()

        g[f"{target}_lag_1"] = series.shift(1)
        g[f"{target}_lag_24"] = series.shift(24)

        ts = g["measured_at"]
        g["hour"] = ts.dt.hour
        g["day_of_week"] = ts.dt.dayofweek
        g["month"] = ts.dt.month
        g["hour_sin"] = np.sin(2 * np.pi * g["hour"] / 24)
        g["hour_cos"] = np.cos(2 * np.pi * g["hour"] / 24)
        g["_target"] = target
        result.append(g)

    return pd.concat(result, ignore_index=True), target


def train_and_predict(df: pd.DataFrame, horizons: list[int] | None = None):
    horizons = horizons or [24, 48, 168]
    featured, target = prepare_features(df)
    featured = featured.dropna(subset=[target])

    exclude = {
        "measured_at", "station_id", "station_name", "source", "station_type",
        "region", "municipality", "latitude", "longitude", "country",
        "pm10", "pm25", "no2", "so2", "o3", "co", "aqi_index",
        "temperature", "humidity", "precipitation", "wind_speed", "_target",
    }
    feature_cols = [
        c for c in featured.columns
        if c not in exclude
        and featured[c].dtype in [np.float64, np.int64, np.float32, np.int32]
        and featured[c].notna().sum() > len(featured) * 0.3
    ]

    if len(featured) < 50 or not feature_cols:
        print(f"[ML] Datos insuficientes ({len(featured)} registros)")
        return None

    X = featured[feature_cols].fillna(0)
    y = featured[target]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.2, shuffle=False
    )

    model = RandomForestRegressor(
        n_estimators=100, max_depth=12, random_state=42, n_jobs=-1
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    metrics = {
        "target": target,
        "mae": mean_absolute_error(y_test, y_pred),
        "rmse": np.sqrt(mean_squared_error(y_test, y_pred)),
        "r2": r2_score(y_test, y_pred),
    }
    print(f"[ML] {target}: MAE={metrics['mae']:.2f}, R²={metrics['r2']:.3f}")

    ensure_dirs()
    joblib.dump(model, MODELS_DIR / "rf_model.joblib")
    joblib.dump(scaler, MODELS_DIR / "rf_scaler.joblib")
    joblib.dump({"features": feature_cols, "target": target}, MODELS_DIR / "rf_meta.joblib")

    forecasts = {}
    last_row = featured.iloc[-1:]
    last_features = last_row[feature_cols].fillna(0)
    X_last = scaler.transform(last_features)

    for hours in horizons:
        pred = max(0, float(model.predict(X_last)[0]))
        forecasts[f"{hours}h"] = {
            "hours": hours,
            "predicted_value": round(pred, 2),
            "target": target,
            "forecast_time": (
                datetime.now(timezone.utc) + timedelta(hours=hours)
            ).isoformat(),
        }

    forecast_df = pd.DataFrame(forecasts.values())
    forecast_df.to_csv(MODELS_DIR / "forecasts.csv", index=False)
    print(f"[ML] Pronósticos guardados: {MODELS_DIR / 'forecasts.csv'}")

    return {"metrics": metrics, "forecasts": forecasts}


def run_ml_pipeline():
    df = load_training_data()
    if df.empty:
        print("[ML] No hay datos para entrenar")
        return None
    return train_and_predict(df)


if __name__ == "__main__":
    run_ml_pipeline()
