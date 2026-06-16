"""
Ingesta de datos meteorológicos desde AEMET OpenData.

Flujo de dos pasos: meta-endpoint -> URL de datos JSON.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from src.config import (
    AEMET_BASE_URL,
    AEMET_STATIONS,
    API_KEY_AEMET,
    INGESTION_LOOKBACK_DAYS,
)


class AemetClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or API_KEY_AEMET
        self.base_url = AEMET_BASE_URL.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"api_key": self.api_key, "accept": "application/json"})

    def _fetch_meta(self, endpoint: str) -> dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        print(f"[AEMET] GET {url}")
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        meta = response.json()
        if meta.get("estado") != 200:
            raise RuntimeError(f"AEMET error: {meta.get('descripcion', meta)}")
        return meta

    def _fetch_data_url(self, data_url: str) -> Any:
        time.sleep(0.3)
        response = self.session.get(data_url, timeout=60)
        response.raise_for_status()
        return response.json()

    def fetch(self, endpoint: str) -> Any:
        meta = self._fetch_meta(endpoint)
        data_url = meta.get("datos")
        if not data_url:
            raise RuntimeError("AEMET no devolvió URL de datos")
        return self._fetch_data_url(data_url)

    def fetch_stations_inventory(self) -> list[dict]:
        data = self.fetch("valores/climatologicos/inventarioestaciones/todasestaciones")
        if isinstance(data, list):
            return data
        return []

    def fetch_station_observation(self, idema: str) -> list[dict]:
        endpoint = f"observacion/convencional/datos/estacion/{idema}"
        data = self.fetch(endpoint)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def fetch_daily_climatology(
        self, idema: str, start: datetime, end: datetime
    ) -> list[dict]:
        fmt = "%Y-%m-%dT%H:%M:%SUTC"
        endpoint = (
            f"valores/climatologicos/diarios/datos/fechaini/"
            f"{start.strftime(fmt)}/fechafin/{end.strftime(fmt)}/estacion/{idema}"
        )
        data = self.fetch(endpoint)
        return data if isinstance(data, list) else []


def _parse_observation(record: dict, station_meta: dict) -> dict:
    """Normaliza un registro de observación AEMET."""
    return {
        "station_id": station_meta.get("idema", record.get("idema", "")),
        "station_name": station_meta.get("name", record.get("nombre", "")),
        "region": station_meta.get("region", ""),
        "municipality": station_meta.get("municipality", ""),
        "latitude": _to_float(record.get("lat") or station_meta.get("latitud")),
        "longitude": _to_float(record.get("lon") or station_meta.get("longitud")),
        "timestamp": record.get("fint") or record.get("fecha") or datetime.now(timezone.utc).isoformat(),
        "temperature": _to_float(record.get("ta") or record.get("tmed")),
        "humidity": _to_float(record.get("hr") or record.get("humedad")),
        "precipitation": _to_float(record.get("prec") or record.get("precipitacion")),
        "wind_speed": _to_float(record.get("vv") or record.get("velmedia")),
        "pressure": _to_float(record.get("pres") or record.get("presMax")),
        "source": "aemet",
        "raw": record,
    }


def _parse_daily(record: dict, station_meta: dict) -> dict:
    return {
        "station_id": station_meta.get("idema", record.get("indicativo", "")),
        "station_name": station_meta.get("name", record.get("nombre", "")),
        "region": station_meta.get("region", ""),
        "municipality": station_meta.get("municipality", ""),
        "latitude": _to_float(station_meta.get("latitud")),
        "longitude": _to_float(station_meta.get("longitud")),
        "timestamp": record.get("fecha", datetime.now(timezone.utc).date().isoformat()),
        "temperature": _to_float(record.get("tmed")),
        "humidity": None,
        "precipitation": _to_float(record.get("prec")),
        "wind_speed": _to_float(record.get("velmedia")),
        "pressure": _to_float(record.get("presMax")),
        "source": "aemet",
        "raw": record,
    }


def _to_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _fetch_climatology_chunks(
    client: AemetClient,
    idema: str,
    start: datetime,
    end: datetime,
    chunk_days: int = 30,
) -> list[dict]:
    """Obtiene climatología diaria en bloques para respetar límites de la API."""
    records: list[dict] = []
    chunk_start = start

    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=chunk_days), end)
        batch = client.fetch_daily_climatology(idema, chunk_start, chunk_end)
        records.extend(batch)
        chunk_start = chunk_end + timedelta(days=1)
        time.sleep(0.5)

    return records


def _abort_aemet(payload: dict[str, Any], exc: Exception) -> dict[str, Any]:
    payload["error"] = str(exc)
    print(f"[AEMET] Fuente no disponible ({exc}); se continúa con la siguiente fuente.")
    print(f"[AEMET] Total registros meteorológicos: {len(payload['weather_records'])}")
    return payload


def ingest_aemet(api_key: str | None = None) -> dict[str, Any]:
    """
    Ejecuta ingesta AEMET completa con histórico configurable.

    Ante el primer error de red o API, aborta el resto de llamadas AEMET
    y devuelve el payload parcial para que el pipeline siga con MITECO.

    Returns:
        dict con keys: stations_inventory, weather_records, metadata
    """
    if not (api_key or API_KEY_AEMET):
        raise ValueError("API_KEY_AEMET no configurada en .env")

    client = AemetClient(api_key)
    payload: dict[str, Any] = {
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "source": "aemet",
        "lookback_days": INGESTION_LOOKBACK_DAYS,
        "stations_inventory": [],
        "weather_records": [],
    }

    try:
        inventory = client.fetch_stations_inventory()
        payload["stations_inventory"] = inventory[:500]
        print(f"[AEMET] Inventario: {len(inventory)} estaciones")
    except Exception as exc:
        return _abort_aemet(payload, exc)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=INGESTION_LOOKBACK_DAYS)
    print(f"[AEMET] Ventana histórica: {INGESTION_LOOKBACK_DAYS} días")

    for station in AEMET_STATIONS:
        idema = station["idema"]
        records: list[dict] = []
        seen: set[str] = set()

        try:
            daily = _fetch_climatology_chunks(client, idema, start, end)
            for row in daily:
                parsed = _parse_daily(row, station)
                key = f"{parsed['station_id']}|{parsed['timestamp']}"
                if key not in seen:
                    seen.add(key)
                    records.append(parsed)

            obs = client.fetch_station_observation(idema)
            for row in obs:
                parsed = _parse_observation(row, station)
                key = f"{parsed['station_id']}|{parsed['timestamp']}"
                if key not in seen:
                    seen.add(key)
                    records.append(parsed)
        except Exception as exc:
            payload["weather_records"].extend(records)
            return _abort_aemet(payload, exc)

        payload["weather_records"].extend(records)
        print(f"[AEMET] {station['name']}: {len(records)} registros")
        time.sleep(0.5)

    print(f"[AEMET] Total registros meteorológicos: {len(payload['weather_records'])}")
    return payload


if __name__ == "__main__":
    data = ingest_aemet()
    print(json.dumps({"records": len(data["weather_records"])}, indent=2))
