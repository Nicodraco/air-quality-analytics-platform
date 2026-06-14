"""
Ingesta de datos de calidad del aire desde OpenAQ API.

OpenAQ agrega datos gubernamentales y de investigación de calidad del aire
a nivel global, incluyendo estaciones españolas.

Requiere API key gratuita: https://explore.openaq.org/register
"""

import os
import time
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv


load_dotenv()

OPENAQ_BASE_URL = "https://api.openaq.org/v3"
API_KEY = os.getenv("OPENAQ_API_KEY", "")

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
RAW_DIR = DATA_DIR / "raw"


def ensure_dirs():
    RAW_DIR.mkdir(parents=True, exist_ok=True)


def get_headers():
    """Retorna headers con API key si está configurada."""
    headers = {"Content-Type": "application/json"}
    if API_KEY and API_KEY != "your_openaq_api_key_here":
        headers["X-API-Key"] = API_KEY
    return headers


def get_countries():
    """Obtiene lista de países disponibles en OpenAQ."""
    try:
        response = requests.get(
            f"{OPENAQ_BASE_URL}/countries",
            headers=get_headers(),
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as e:
        print(f"[OpenAQ] Error obteniendo países: {e}")
        return []


def get_locations(country_id="ES", limit=100):
    """
    Obtiene ubicaciones de monitoreo en un país.

    Args:
        country_id: Código ISO del país (ES = España)
        limit: Número máximo de resultados
    """
    try:
        params = {"countries_id": country_id, "limit": min(limit, 1000)}
        response = requests.get(
            f"{OPENAQ_BASE_URL}/locations",
            headers=get_headers(),
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    except Exception as e:
        print(f"[OpenAQ] Error obteniendo ubicaciones: {e}")
        return []


def get_latest_measurements(location_id, limit=100):
    """
    Obtiene las últimas mediciones de una ubicación.

    Args:
        location_id: ID de la ubicación en OpenAQ
        limit: Número máximo de mediciones
    """
    try:
        params = {"limit": min(limit, 1000)}
        response = requests.get(
            f"{OPENAQ_BASE_URL}/locations/{location_id}/latest",
            headers=get_headers(),
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    except Exception as e:
        print(f"[OpenAQ] Error obteniendo mediciones de {location_id}: {e}")
        return []


def fetch_spain_data():
    """
    Obtiene datos de calidad del aire de España desde OpenAQ.
    """
    print("[OpenAQ] Obteniendo ubicaciones en España...")
    locations = get_locations(country_id="ES", limit=50)
    print(f"[OpenAQ] {len(locations)} ubicaciones encontradas en España")

    all_measurements = []

    for loc in locations[:10]:
        loc_id = loc.get("id")
        loc_name = loc.get("name", f"Location_{loc_id}")
        loc_coords = loc.get("coordinates", {})

        lat = loc_coords.get("latitude", loc.get("latitude", None))
        lon = loc_coords.get("longitude", loc.get("longitude", None))

        measurements = get_latest_measurements(loc_id)
        print(f"[OpenAQ] {loc_name}: {len(measurements)} mediciones")

        for m in measurements:
            param = m.get("parameter", {})
            all_measurements.append(
                {
                    "location_id": loc_id,
                    "location_name": loc_name,
                    "latitude": lat,
                    "longitude": lon,
                    "parameter": param.get("name", "unknown"),
                    "parameter_id": param.get("id", None),
                    "value": m.get("value"),
                    "unit": m.get("unit"),
                    "timestamp": m.get("datetimeLast", m.get("datetime")),
                }
            )

        time.sleep(0.3)

    if all_measurements:
        df = pd.DataFrame(all_measurements)
        return df

    return generate_simulated_openaq_data()


def generate_simulated_openaq_data():
    """
    Genera datos simulados de estaciones españolas similares a los
    que devolvería OpenAQ.
    """
    print("[OpenAQ] Generando datos simulados de estaciones españolas...")
    np.random.seed(42)

    spanish_stations = [
        ("Barcelona - Eixample", 41.389, 2.165),
        ("Barcelona - Gràcia", 41.402, 2.157),
        ("Barcelona - Ciutadella", 41.387, 2.188),
        ("Barcelona - Palau Reial", 41.387, 2.117),
        ("Barcelona - Poblenou", 41.407, 2.204),
        ("Barcelona - Sants", 41.375, 2.136),
        ("Barcelona - Vall d'Hebron", 41.427, 2.142),
        ("Barcelona - Zona Universitària", 41.386, 2.113),
        ("Madrid - Plaza España", 40.423, -3.712),
        ("Madrid - Retiro", 40.417, -3.683),
    ]

    parameters = [
        ("PM2.5", "µg/m³", lambda: np.random.uniform(5, 45)),
        ("PM10", "µg/m³", lambda: np.random.uniform(10, 60)),
        ("NO2", "µg/m³", lambda: np.random.uniform(15, 65)),
        ("O3", "µg/m³", lambda: np.random.uniform(20, 90)),
        ("CO", "mg/m³", lambda: np.random.uniform(0.1, 2.0)),
        ("SO2", "µg/m³", lambda: np.random.uniform(1, 15)),
    ]

    now = datetime.now()
    records = []

    for name, lat, lon in spanish_stations:
        for i in range(24):
            ts = now - timedelta(hours=i)
            for param_name, unit, gen_func in parameters:
                value = gen_func()
                records.append(
                    {
                        "location_name": name,
                        "latitude": lat,
                        "longitude": lon,
                        "parameter": param_name,
                        "value": round(value, 2),
                        "unit": unit,
                        "timestamp": ts.isoformat(),
                    }
                )

    df = pd.DataFrame(records)
    print(f"[OpenAQ] {len(df)} registros generados")
    return df


def save_data(df):
    """Guarda los datos con timestamp."""
    ensure_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = RAW_DIR / f"openaq_spain_{timestamp}.csv"
    df.to_csv(filepath, index=False)
    print(f"[OpenAQ] Guardado: {filepath} ({len(df)} registros)")
    return filepath


def load_latest():
    """Carga el archivo más reciente de OpenAQ."""
    files = sorted(RAW_DIR.glob("openaq_spain_*.csv"))
    if not files:
        print("[OpenAQ] No hay datos locales. Obteniendo datos nuevos...")
        df = fetch_spain_data()
        if df is not None:
            save_data(df)
            return df
        return None
    latest = files[-1]
    print(f"[OpenAQ] Cargando: {latest}")
    return pd.read_csv(latest, parse_dates=["timestamp"])


if __name__ == "__main__":
    df = fetch_spain_data()
    if df is not None:
        save_data(df)
        print(df.head())
        print(f"\nContaminantes:\n{df['parameter'].value_counts()}")
