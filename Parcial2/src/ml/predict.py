"""
Modelo de predicción de tendencias de calidad del aire.

Usa Prophet-style decomposition con regresión lineal y Random Forest
para predecir concentraciones de NO2, PM2.5 y otros contaminantes.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler
import joblib
import warnings


warnings.filterwarnings("ignore")

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


def ensure_dirs():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)


def load_processed_data(filepath=None):
    """Carga datos preprocesados."""
    if filepath is None:
        filepath = PROCESSED_DIR / "air_quality_merged.parquet"

    if filepath.suffix == ".parquet":
        return pd.read_parquet(filepath)
    return pd.read_csv(filepath, parse_dates=["timestamp"])


def prepare_features(df, target_col="no2", window_sizes=[3, 7, 14, 30]):
    """
    Crea features temporales para predicción.

    Args:
        df: DataFrame con datos horarios/diarios
        target_col: Columna objetivo a predecir
        window_sizes: Tamaños de ventanas para medias móviles
    """
    data = df.copy()

    if target_col not in data.columns:
        available = [c for c in ["no2", "pm2_5", "pm10", "o3"] if c in data.columns]
        if not available:
            raise ValueError(f"Columna {target_col} no encontrada. Disponibles: {list(data.columns)}")
        target_col = available[0]
        print(f"[ML] Usando columna alternativa: {target_col}")

    data = data.sort_values("timestamp").reset_index(drop=True)

    if "location" in data.columns:
        location_groups = data.groupby("location")
    else:
        data["location"] = "all"
        location_groups = data.groupby("location")

    feature_dfs = []

    for loc, group in location_groups:
        g = group.sort_values("timestamp").copy()

        series = g[target_col].ffill().bfill()

        for w in window_sizes:
            g[f"{target_col}_ma_{w}d"] = series.rolling(window=w, min_periods=1).mean()
            g[f"{target_col}_std_{w}d"] = series.rolling(window=w, min_periods=1).std()

        g[f"{target_col}_lag_1"] = series.shift(1)
        g[f"{target_col}_lag_7"] = series.shift(7)

        g["hour_sin"] = np.sin(2 * np.pi * g["timestamp"].dt.hour / 24)
        g["hour_cos"] = np.cos(2 * np.pi * g["timestamp"].dt.hour / 24)
        g["month_sin"] = np.sin(2 * np.pi * g["timestamp"].dt.month / 12)
        g["month_cos"] = np.cos(2 * np.pi * g["timestamp"].dt.month / 12)
        g["day_of_week"] = g["timestamp"].dt.dayofweek
        g["is_weekend"] = (g["timestamp"].dt.dayofweek >= 5).astype(int)

        feature_dfs.append(g)

    result = pd.concat(feature_dfs, ignore_index=True)
    return result


def train_model(df, target_col="no2", test_size=0.2):
    """
    Entrena modelo Random Forest para predicción de contaminantes.

    Args:
        df: DataFrame con features
        target_col: Columna objetivo
        test_size: Proporción para test

    Returns: (modelo, scaler, métricas, y_test, y_pred)
    """
    exclude_cols = [
        "timestamp", "source", "location", target_col,
        "latitude", "longitude", "date",
        "location_name", "lat", "lon",
        "census_tract_id", "no2_uncertainty",
        "exceedance_probability",
    ]
    feature_cols = [
        c for c in df.columns
        if c not in exclude_cols
        and df[c].dtype in [np.float64, np.int64, np.float32, np.int32]
        and df[c].notna().sum() > len(df) * 0.5
    ]

    data = df[feature_cols + [target_col]].dropna()

    if len(data) < 100:
        print(f"[ML] Datos insuficientes ({len(data)} registros). Usando Ridge Regression.")
        return train_ridge_model(df, target_col, test_size)

    X = data[feature_cols]
    y = data[target_col]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=test_size, random_state=42, shuffle=False
    )

    model = RandomForestRegressor(
        n_estimators=100,
        max_depth=15,
        min_samples_leaf=5,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    metrics = {
        "mae": mean_absolute_error(y_test, y_pred),
        "rmse": np.sqrt(mean_squared_error(y_test, y_pred)),
        "r2": r2_score(y_test, y_pred),
        "feature_importance": dict(
            zip(feature_cols, model.feature_importances_)
        ),
    }

    print(f"[ML] Random Forest - {target_col}")
    print(f"      MAE: {metrics['mae']:.2f}, RMSE: {metrics['rmse']:.2f}, R²: {metrics['r2']:.3f}")

    return model, scaler, metrics, y_test, y_pred


def train_ridge_model(df, target_col="no2", test_size=0.2):
    """Modelo Ridge para datasets pequeños."""
    exclude_cols = [
        "timestamp", "source", "location", target_col,
        "latitude", "longitude", "date", "location_name",
    ]
    feature_cols = [
        c for c in df.columns
        if c not in exclude_cols
        and df[c].dtype in [np.float64, np.int64]
    ]

    data = df[feature_cols + [target_col]].dropna()
    X = data[feature_cols]
    y = data[target_col]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=test_size, random_state=42
    )

    model = Ridge(alpha=1.0)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    metrics = {
        "mae": mean_absolute_error(y_test, y_pred),
        "rmse": np.sqrt(mean_squared_error(y_test, y_pred)),
        "r2": r2_score(y_test, y_pred),
    }

    print(f"[ML] Ridge - {target_col}")
    print(f"      MAE: {metrics['mae']:.2f}, RMSE: {metrics['rmse']:.2f}, R²: {metrics['r2']:.3f}")

    return model, scaler, metrics, y_test, y_pred


def predict_future(model, scaler, last_data, periods=7):
    """
    Predice valores futuros.

    Args:
        model: Modelo entrenado
        scaler: Scaler ajustado
        last_data: Últimos datos con features
        periods: Días a predecir

    Returns: DataFrame con predicciones
    """
    last_features = last_data.drop(columns=["timestamp", "source", "location"], errors="ignore")

    numeric_cols = last_features.select_dtypes(include=[np.number]).columns
    last_numeric = last_features[numeric_cols].iloc[-1:]

    predictions = []
    current = last_numeric.copy()

    for i in range(periods):
        X_scaled = scaler.transform(current.fillna(0))
        pred = model.predict(X_scaled)[0]
        predictions.append(
            {
                "day": i + 1,
                "predicted_value": max(0, pred),
                "date": (
                    datetime.now() + timedelta(days=i + 1)
                ).strftime("%Y-%m-%d"),
            }
        )

    return pd.DataFrame(predictions)


def save_model(model, scaler, metrics, name="air_quality_model"):
    """Guarda modelo y scaler."""
    ensure_dirs()
    model_path = MODELS_DIR / f"{name}.joblib"
    scaler_path = MODELS_DIR / f"{name}_scaler.joblib"
    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)
    print(f"[ML] Modelo guardado: {model_path}")
    return model_path, scaler_path


def run_ml_pipeline():
    """Ejecuta el pipeline completo de ML."""
    print("=" * 60)
    print("PIPELINE DE ML - Predicción de Calidad del Aire")
    print("=" * 60)

    df = load_processed_data()
    if df is None or len(df) == 0:
        print("[ML] No hay datos procesados. Ejecuta preprocess.py primero.")
        return

    target = "no2" if "no2" in df.columns else "pm2_5"

    print(f"[ML] Preparando features para: {target}")
    featured_df = prepare_features(df, target_col=target)

    model, scaler, metrics, y_test, y_pred = train_model(featured_df, target_col=target)

    save_model(model, scaler, metrics)

    print("\n[ML] Pipeline completado exitosamente.")
    return model, scaler, metrics


if __name__ == "__main__":
    run_ml_pipeline()
