"""
Ingesta de datos de calidad del aire desde Open-Meteo Air Quality API.

Basado en datos CAMS/Copernicus de la Unión Europea.
No requiere API key. Gratuito para uso no comercial.

Variables disponibles: PM2.5, PM10, O3, NO2, SO2, CO, European AQI
"""

import os
import time
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta


OPENMETEO_AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
RAW_DIR = DATA_DIR / "raw"

BARCELONA_LAT = 41.3874
BARCELONA_LON = 2.1686

MADRID_LAT = 40.4168
MADRID_LON = -3.7038


def ensure_dirs():
    RAW_DIR.mkdir(parents=True, exist_ok=True)


def fetch_air_quality(
    latitude=BARCELONA_LAT,
    longitude=BARCELONA_LON,
    past_days=7,
    forecast_days=3,
):
    """
    Obtiene datos de calidad del aire de Open-Meteo.

    Args:
        latitude, longitude: Coordenadas de la ubicación
        past_days: Días históricos a incluir (max 92)
        forecast_days: Días de pronóstico (max 7)

    Returns: DataFrame con datos horarios
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": [
            "pm2_5",
            "pm10",
            "nitrogen_dioxide",
            "ozone",
            "sulphur_dioxide",
            "carbon_monoxide",
            "european_aqi",
        ],
        "past_days": past_days,
        "forecast_days": forecast_days,
        "timeformat": "iso8601",
    }

    print(f"[Open-Meteo] Solicitando datos para ({latitude}, {longitude})...")
    try:
        response = requests.get(OPENMETEO_AQ_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"[Open-Meteo] Error: {e}")
        return None

    hourly = data.get("hourly", {})
    if not hourly:
        print("[Open-Meteo] No se encontraron datos horarios")
        return None

    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(hourly["time"]),
            "pm2_5": hourly.get("pm2_5", [np.nan] * len(hourly["time"])),
            "pm10": hourly.get("pm10", [np.nan] * len(hourly["time"])),
            "no2": hourly.get("nitrogen_dioxide", [np.nan] * len(hourly["time"])),
            "o3": hourly.get("ozone", [np.nan] * len(hourly["time"])),
            "so2": hourly.get("sulphur_dioxide", [np.nan] * len(hourly["time"])),
            "co": hourly.get("carbon_monoxide", [np.nan] * len(hourly["time"])),
            "european_aqi": hourly.get(
                "european_aqi", [np.nan] * len(hourly["time"])
            ),
        }
    )

    df["latitude"] = latitude
    df["longitude"] = longitude
    df["location"] = (
        "Barcelona" if (latitude, longitude) == (BARCELONA_LAT, BARCELONA_LON)
        else f"Coords_{latitude}_{longitude}"
    )

    return df


def fetch_multiple_locations(
    locations=None, past_days=7, forecast_days=3
):
    """
    Obtiene datos de calidad del aire para múltiples ubicaciones.

    Args:
        locations: Lista de tuplas (lat, lon, nombre)
    """
    if locations is None:
        locations = [
            (BARCELONA_LAT, BARCELONA_LON, "Barcelona"),
            (MADRID_LAT, MADRID_LON, "Madrid"),
        ]

    all_dfs = []
    for lat, lon, name in locations:
        df = fetch_air_quality(lat, lon, past_days, forecast_days)
        if df is not None:
            df["location"] = name
            all_dfs.append(df)
        time.sleep(0.5)

    if all_dfs:
        return pd.concat(all_dfs, ignore_index=True)
    return None


def save_data(df):
    """Guarda los datos con timestamp."""
    ensure_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = RAW_DIR / f"openmeteo_aq_{timestamp}.csv"
    df.to_csv(filepath, index=False)
    print(f"[Open-Meteo] Guardado: {filepath} ({len(df)} registros)")
    return filepath


def load_latest():
    """Carga el archivo más reciente de Open-Meteo."""
    files = sorted(RAW_DIR.glob("openmeteo_aq_*.csv"))
    if not files:
        print("[Open-Meteo] No hay datos locales. Obteniendo datos nuevos...")
        df = fetch_multiple_locations(past_days=30)
        if df is not None:
            save_data(df)
            return df
        return None
    latest = files[-1]
    print(f"[Open-Meteo] Cargando: {latest}")
    return pd.read_csv(latest, parse_dates=["timestamp"])


if __name__ == "__main__":
    df = fetch_multiple_locations(past_days=7, forecast_days=3)
    if df is not None:
        save_data(df)
        print(df.head())
        print(f"\nResumen:\n{df.describe()}")
