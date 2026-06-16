"""
Capa Silver: limpieza, normalización y conversión a Parquet.

Tablas: silver_weather, silver_air_quality, silver_stations
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from src.config import INGESTION_LOOKBACK_DAYS, SILVER_DIR, ensure_dirs


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


def _normalize_to_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Colapsa múltiples lecturas horarias al promedio diario por estación."""
    if df.empty or "timestamp" not in df.columns:
        return df

    data = df.copy()
    data["timestamp"] = _to_datetime(data["timestamp"])
    data["date"] = data["timestamp"].dt.floor("D")

    meta_cols = [
        "station_id", "station_name", "region", "municipality",
        "country", "latitude", "longitude", "source", "station_type",
    ]
    numeric_cols = [
        c for c in data.columns
        if c not in meta_cols + ["timestamp", "date", "raw"]
        and pd.api.types.is_numeric_dtype(data[c])
    ]

    agg: dict[str, str] = {c: "mean" for c in numeric_cols}
    for col in meta_cols:
        if col in data.columns:
            agg[col] = "first"

    daily = (
        data.groupby(["station_id", "date"], as_index=False)
        .agg(agg)
        .rename(columns={"date": "timestamp"})
    )
    return daily


def _merge_parquet(name: str, new_df: pd.DataFrame, dedup_cols: list[str]) -> pd.DataFrame:
    """Fusiona datos nuevos con Parquet existente sin perder histórico."""
    path = SILVER_DIR / f"{name}.parquet"
    if path.exists():
        existing = pd.read_parquet(path)
    else:
        existing = pd.DataFrame()

    if new_df.empty:
        return existing

    if existing.empty:
        merged = new_df
    else:
        merged = pd.concat([existing, new_df], ignore_index=True)

    dedup_subset = [c for c in dedup_cols if c in merged.columns]
    if dedup_subset:
        merged = merged.drop_duplicates(subset=dedup_subset, keep="last")

    if "timestamp" in merged.columns:
        merged["timestamp"] = _to_datetime(merged["timestamp"])
        merged = merged.sort_values("timestamp")
        cutoff = datetime.now(timezone.utc) - timedelta(days=INGESTION_LOOKBACK_DAYS + 7)
        merged = merged[merged["timestamp"] >= cutoff]

    path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(path, index=False)
    return merged


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
        air_quality = _normalize_to_daily(air_quality)
        air_quality["aqi_index"] = air_quality.apply(compute_aqi, axis=1)

    outputs = {
        "silver_weather": _merge_parquet(
            "silver_weather", weather, ["station_id", "timestamp"]
        ),
        "silver_air_quality": _merge_parquet(
            "silver_air_quality", air_quality, ["station_id", "timestamp"]
        ),
        "silver_stations": _merge_parquet(
            "silver_stations", stations, ["station_id", "source"]
        ),
    }

    for name, df in outputs.items():
        if df is not None and not df.empty:
            print(f"[Silver] {name}: {len(df)} registros -> {SILVER_DIR / f'{name}.parquet'}")
        else:
            print(f"[Silver] {name}: sin datos")

    return outputs


if __name__ == "__main__":
    from src.bronze.storage import load_latest_bronze

    aemet = load_latest_bronze("aemet") or {"weather_records": []}
    miteco = load_latest_bronze("miteco") or {"air_quality_records": []}
    run_silver_transform(aemet, miteco)
