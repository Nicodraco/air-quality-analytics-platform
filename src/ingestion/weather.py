"""
Orquestador de ingesta meteorológica: AEMET (primario) -> Open-Meteo (respaldo).
"""

from typing import Any

from src.ingestion.aemet import ingest_aemet
from src.ingestion.openmeteo import ingest_openmeteo


def ingest_weather(api_key: str | None = None) -> dict[str, Any]:
    """
    Intenta AEMET; si no hay registros o falla, usa Open-Meteo Archive.
    """
    aemet_payload: dict[str, Any] | None = None

    try:
        aemet_payload = ingest_aemet(api_key=api_key)
        records = aemet_payload.get("weather_records", [])
        if records and not aemet_payload.get("error"):
            aemet_payload["weather_source"] = "aemet"
            return aemet_payload
        reason = aemet_payload.get("error", "sin registros")
        print(f"[Weather] AEMET sin datos útiles ({reason}); usando Open-Meteo.")
    except Exception as exc:
        print(f"[Weather] AEMET no disponible ({exc}); usando Open-Meteo.")

    openmeteo_payload = ingest_openmeteo()
    openmeteo_payload["weather_source"] = "openmeteo"
    if aemet_payload and aemet_payload.get("weather_records"):
        openmeteo_payload["weather_records"] = (
            aemet_payload["weather_records"] + openmeteo_payload["weather_records"]
        )
    return openmeteo_payload
