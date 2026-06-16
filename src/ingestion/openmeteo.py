"""
Ingesta de datos meteorológicos históricos desde Open-Meteo Archive API.

API gratuita, sin clave, con histórico diario de varios años.
https://open-meteo.com/en/docs/historical-weather-api
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from src.config import INGESTION_LOOKBACK_DAYS, WEATHER_STATIONS, OPENMETEO_ARCHIVE_URL


def _parse_daily(
    date_str: str,
    values: dict[str, list],
    idx: int,
    station: dict,
) -> dict:
    def _val(key: str) -> float | None:
        series = values.get(key)
        if not series or idx >= len(series):
            return None
        v = series[idx]
        return float(v) if v is not None else None

    return {
        "station_id": station["id"],
        "station_name": station["name"],
        "region": station["region"],
        "municipality": station["municipality"],
        "latitude": station["latitude"],
        "longitude": station["longitude"],
        "timestamp": f"{date_str}T12:00:00+00:00",
        "temperature": _val("temperature_2m_mean"),
        "humidity": _val("relative_humidity_2m_mean"),
        "precipitation": _val("precipitation_sum"),
        "wind_speed": _val("wind_speed_10m_mean"),
        "pressure": _val("surface_pressure_mean"),
        "source": "openmeteo",
        "raw": {k: values[k][idx] for k in values if idx < len(values[k])},
    }


def _fetch_station_history(
    station: dict, start: datetime, end: datetime
) -> list[dict]:
    params = {
        "latitude": station["latitude"],
        "longitude": station["longitude"],
        "start_date": start.date().isoformat(),
        "end_date": end.date().isoformat(),
        "daily": ",".join([
            "temperature_2m_mean",
            "relative_humidity_2m_mean",
            "precipitation_sum",
            "wind_speed_10m_mean",
            "surface_pressure_mean",
        ]),
        "timezone": "UTC",
    }
    url = OPENMETEO_ARCHIVE_URL
    print(
        f"[Open-Meteo] {station['name']}: "
        f"{params['start_date']} -> {params['end_date']}"
    )
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()
    data = response.json()

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    records = [
        _parse_daily(date_str, daily, i, station)
        for i, date_str in enumerate(dates)
    ]
    return records


def ingest_openmeteo() -> dict[str, Any]:
    """
    Obtiene climatología diaria histórica para las estaciones configuradas.

    Returns:
        dict compatible con bronze AEMET (weather_records, stations_inventory)
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=INGESTION_LOOKBACK_DAYS)

    payload: dict[str, Any] = {
        "ingested_at": end.isoformat(),
        "source": "openmeteo",
        "lookback_days": INGESTION_LOOKBACK_DAYS,
        "stations_inventory": WEATHER_STATIONS,
        "weather_records": [],
    }

    print(f"[Open-Meteo] Ventana histórica: {INGESTION_LOOKBACK_DAYS} días")

    for station in WEATHER_STATIONS:
        records = _fetch_station_history(station, start, end)
        payload["weather_records"].extend(records)
        print(f"[Open-Meteo] {station['name']}: {len(records)} registros")

    print(
        f"[Open-Meteo] Total registros meteorológicos: "
        f"{len(payload['weather_records'])}"
    )
    return payload


if __name__ == "__main__":
    data = ingest_openmeteo()
    print(json.dumps({"records": len(data["weather_records"])}, indent=2))
