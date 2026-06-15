"""
Configuración central de la plataforma de monitoreo ambiental.
Lee variables desde .env (incluye API_KEY_AEMET del usuario).
"""

import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    value = os.getenv(key, default)
    return value.strip().strip('"').strip("'") if value else default


# --- APIs externas ---
API_KEY_AEMET = _env("API_KEY_AEMET")
AEMET_BASE_URL = _env(
    "AEMET_BASE_URL", "https://opendata.aemet.es/opendata/api"
)
URL_BUSQUEDA_MITECO = _env("URL_BUSQUEDA_MITECO", "https://miteco.gob.es")
URL_DATASTORE_MITECO = _env("URL_DATASTORE_MITECO", "https://miteco.gob.es")

# --- MinIO (Bronze) ---
MINIO_ENDPOINT = _env("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = _env("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = _env("MINIO_SECRET_KEY", "minioadmin123")
MINIO_BUCKET = _env("MINIO_BUCKET", "ambiental-lake")
MINIO_SECURE = _env("MINIO_SECURE", "false").lower() == "true"
USE_LOCAL_BRONZE_FALLBACK = _env("USE_LOCAL_BRONZE_FALLBACK", "true").lower() == "true"

# --- PostgreSQL (Gold) ---
POSTGRES_HOST = _env("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(_env("POSTGRES_PORT", "5432"))
POSTGRES_DB = _env("POSTGRES_DB", "ambiental_dw")
POSTGRES_USER = _env("POSTGRES_USER", "ambiental")
POSTGRES_PASSWORD = _env("POSTGRES_PASSWORD", "ambiental123")

# --- LLM ---
LLM_PROVIDER = _env("LLM_PROVIDER", "narrativo")  # ollama | openai | narrativo
LLM_API_KEY = _env("LLM_API_KEY")
LLM_API_URL = _env("LLM_API_URL", "http://localhost:11434")
LLM_MODEL = _env("LLM_MODEL", "llama3")

# --- Rutas locales ---
DATA_DIR = ROOT_DIR / "data"
BRONZE_LOCAL_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
REPORTS_DIR = ROOT_DIR / "reports"
MODELS_DIR = ROOT_DIR / "models"

# --- Pipeline ---
PIPELINE_INTERVAL_MINUTES = int(_env("PIPELINE_INTERVAL_MINUTES", "60"))

# Estaciones AEMET prioritarias (Madrid, Barcelona, Valencia, Sevilla)
AEMET_STATIONS = [
    {"idema": "3195", "name": "Madrid Retiro", "region": "Comunidad de Madrid", "municipality": "Madrid"},
    {"idema": "0076", "name": "Barcelona Fabra", "region": "Cataluña", "municipality": "Barcelona"},
    {"idema": "8416A", "name": "Valencia", "region": "Comunidad Valenciana", "municipality": "Valencia"},
    {"idema": "5783", "name": "Sevilla", "region": "Andalucía", "municipality": "Sevilla"},
]

# Límites OMS (µg/m³) para alertas
WHO_LIMITS = {
    "pm10": 45.0,
    "pm25": 15.0,
    "no2": 25.0,
    "so2": 40.0,
    "o3": 100.0,
    "co": 4000.0,
}


def postgres_url() -> str:
    return (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )


def ensure_dirs():
    for d in [BRONZE_LOCAL_DIR, SILVER_DIR, REPORTS_DIR, MODELS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
