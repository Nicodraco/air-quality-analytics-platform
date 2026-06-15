"""
Capa Silver: limpieza, normalización y conversión a Parquet.

Tablas: silver_weather, silver_air_quality, silver_stations
"""

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from src.config import SILVER_DIR, ensure_dirs


def _to_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce")


def _validate_coords(df: pd.DataFrame) -> pd.DataFrame:
    if "latitude" not in df.columns or "longitude" not in df.columns:
        return df
    valid = (
        df["latitude"].between(-90, 90)
        & df["longitude"].between(-180, 180)
        & df["latitude"].notna()
        & df["longitude"].notna()
    )
    invalid = (~valid).sum()
    if invalid:
        print(f"[Silver] {invalid} registros con coordenadas inválidas eliminados")
    return df[valid].copy()


def transform_weather(bronze_aemet: dict[str, Any]) -> pd.DataFrame:
    """Transforma datos AEMET Bronze -> silver_weather."""
    records = bronze_aemet.get("weather_records", [])
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df = df.drop_duplicates(subset=["station_id", "timestamp"], keep="last")
    df["timestamp"] = _to_datetime(df["timestamp"])
    df = df.dropna(subset=["timestamp"])
    df = _validate_coords(df)

    numeric_cols = [
        "temperature", "humidity", "precipitation", "wind_speed", "pressure"
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["country"] = "España"
    df["source"] = "aemet"
    df["station_type"] = "meteorological"

    keep = [
        "station_id", "station_name", "region", "municipality",
        "country", "latitude", "longitude", "timestamp",
        "temperature", "humidity", "precipitation", "wind_speed", "pressure",
        "source", "station_type",
    ]
    return df[[c for c in keep if c in df.columns]]


def transform_air_quality(bronze_miteco: dict[str, Any]) -> pd.DataFrame:
    """Transforma datos MITECO Bronze -> silver_air_quality."""
    records = bronze_miteco.get("air_quality_records", [])
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df = df.drop_duplicates(subset=["station_id", "timestamp"], keep="last")
    df["timestamp"] = _to_datetime(df["timestamp"])
    df = df.dropna(subset=["timestamp"])
    df = _validate_coords(df)

    pollutant_cols = ["pm10", "pm25", "no2", "so2", "o3", "co"]
    for col in pollutant_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["country"] = "España"
    df["source"] = "miteco"
    df["station_type"] = "air_quality"

    keep = [
        "station_id", "station_name", "region", "municipality",
        "country", "latitude", "longitude", "timestamp",
        "pm10", "pm25", "no2", "so2", "o3", "co",
        "source", "station_type",
    ]
    return df[[c for c in keep if c in df.columns]]


def transform_stations(
    bronze_aemet: dict[str, Any], bronze_miteco: dict[str, Any]
) -> pd.DataFrame:
    """Unifica metadatos de estaciones."""
    rows = []

    for record in bronze_aemet.get("weather_records", []):
        rows.append({
            "station_id": record.get("station_id"),
            "station_name": record.get("station_name"),
            "region": record.get("region"),
            "municipality": record.get("municipality"),
            "latitude": record.get("latitude"),
            "longitude": record.get("longitude"),
            "source": "aemet",
            "station_type": "meteorological",
        })

    for station in bronze_miteco.get("stations", []):
        rows.append({
            "station_id": station.get("station_id"),
            "station_name": station.get("station_name"),
            "region": station.get("region"),
            "municipality": station.get("municipality"),
            "latitude": station.get("latitude"),
            "longitude": station.get("longitude"),
            "source": "miteco",
            "station_type": "air_quality",
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).drop_duplicates(subset=["station_id", "source"])
    df = _validate_coords(df)
    df["country"] = "España"
    return df


def compute_aqi(row: pd.Series) -> float | None:
    """Índice simplificado de calidad del aire (0-100, mayor = peor)."""
    scores = []
    limits = {"pm25": 15, "pm10": 45, "no2": 25, "o3": 100, "so2": 40}
    for pollutant, limit in limits.items():
        val = row.get(pollutant)
        if pd.notna(val) and limit > 0:
            scores.append(min(100, (val / limit) * 50))
    return round(np.mean(scores), 1) if scores else None


def run_silver_transform(
    bronze_aemet: dict[str, Any], bronze_miteco: dict[str, Any]
) -> dict[str, pd.DataFrame]:
    """Ejecuta transformación Silver completa y guarda Parquet."""
    ensure_dirs()
    print("=" * 60)
    print("SILVER LAYER - Transformación")
    print("=" * 60)

    weather = transform_weather(bronze_aemet)
    air_quality = transform_air_quality(bronze_miteco)
    stations = transform_stations(bronze_aemet, bronze_miteco)

    if not air_quality.empty:
        air_quality["aqi_index"] = air_quality.apply(compute_aqi, axis=1)

    outputs = {
        "silver_weather": weather,
        "silver_air_quality": air_quality,
        "silver_stations": stations,
    }

    for name, df in outputs.items():
        if df is not None and not df.empty:
            path = SILVER_DIR / f"{name}.parquet"
            df.to_parquet(path, index=False)
            print(f"[Silver] {name}: {len(df)} registros -> {path}")
        else:
            print(f"[Silver] {name}: sin datos")

    return outputs


if __name__ == "__main__":
    from src.bronze.storage import load_latest_bronze

    aemet = load_latest_bronze("aemet") or {"weather_records": []}
    miteco = load_latest_bronze("miteco") or {"air_quality_records": []}
    run_silver_transform(aemet, miteco)
