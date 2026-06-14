"""
Generación de resúmenes diarios de calidad del aire usando LLM.

Utiliza API compatible con OpenAI para generar reportes legibles
sobre el estado de la calidad del aire.
"""

import os
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv


load_dotenv()

API_KEY = os.getenv("LLM_API_KEY", "")
API_URL = os.getenv("LLM_API_URL", "https://api.openai.com/v1")
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"


def ensure_dirs():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_latest_data():
    """Carga los datos más recientes para el resumen."""
    parquet_path = PROCESSED_DIR / "air_quality_merged.parquet"
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    csv_path = PROCESSED_DIR / "air_quality_merged.csv"
    if csv_path.exists():
        return pd.read_csv(csv_path, parse_dates=["timestamp"])
    return None


def prepare_summary_data(df):
    """
    Prepara estadísticas para el resumen diario.

    Returns: dict con datos estructurados
    """
    if df is None or len(df) == 0:
        return None

    df = df.sort_values("timestamp")
    latest_ts = df["timestamp"].max()
    today_data = df[df["timestamp"].dt.date == latest_ts.date()]

    if len(today_data) == 0:
        today_data = df.tail(24)

    pollutants = {}
    for col in ["pm2_5", "pm10", "no2", "o3", "so2", "co", "european_aqi"]:
        if col in today_data.columns:
            vals = today_data[col].dropna()
            if len(vals) > 0:
                pollutants[col] = {
                    "mean": round(vals.mean(), 1),
                    "max": round(vals.max(), 1),
                    "min": round(vals.min(), 1),
                }

    locations_data = {}
    if "location" in today_data.columns:
        for loc in today_data["location"].unique():
            loc_df = today_data[today_data["location"] == loc]
            loc_stats = {}
            for col in ["pm2_5", "pm10", "no2", "european_aqi"]:
                if col in loc_df.columns:
                    vals = loc_df[col].dropna()
                    if len(vals) > 0:
                        loc_stats[col] = round(vals.mean(), 1)
            if loc_stats:
                locations_data[loc] = loc_stats

    summary = {
        "date": latest_ts.strftime("%Y-%m-%d"),
        "total_records": len(today_data),
        "locations_count": len(locations_data),
        "pollutants": pollutants,
        "locations": locations_data,
        "data_sources": (
            df["source"].unique().tolist()
            if "source" in df.columns
            else ["unknown"]
        ),
    }

    return summary


def generate_prompt(summary_data):
    """Genera el prompt para el LLM."""
    if summary_data is None:
        return "No hay datos disponibles para generar un resumen."

    date = summary_data["date"]
    locs = summary_data["locations"]
    pols = summary_data["pollutants"]

    poll_details = ""
    for name, vals in pols.items():
        poll_details += f"  - {name}: media {vals['mean']}, máx {vals['max']}, mín {vals['min']}\n"

    loc_details = ""
    for name, vals in list(locs.items())[:5]:
        vals_str = ", ".join([f"{k}: {v}" for k, v in vals.items()])
        loc_details += f"  - {name}: {vals_str}\n"

    prompt = f"""Eres un analista ambiental. Genera un resumen ejecutivo breve de la calidad del aire.

Fecha: {date}
Registros analizados: {summary_data['total_records']}
Ubicaciones monitoreadas: {summary_data['locations_count']}
Fuentes de datos: {', '.join(summary_data['data_sources'])}

Promedios de contaminantes:
{poll_details}

Datos por ubicación:
{loc_details}

Genera un reporte de 3-4 párrafos que incluya:
1. Estado general de la calidad del aire
2. Contaminante más problemático y sus niveles
3. Ubicaciones con mejor y peor calidad del aire
4. Comparación con estándares de la OMS (si aplica)
5. Recomendaciones para la población

Usa lenguaje claro y accesible. Incluye datos numéricos relevantes.
Responde en español.
"""
    return prompt


def call_llm_api(prompt, max_tokens=800):
    """
    Llama a la API del LLM para generar el resumen.

    Si no hay API key configurada, genera un resumen basado en reglas.
    """
    if API_KEY and API_KEY != "your_llm_api_key_here":
        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "Eres un asistente experto en calidad del aire y datos ambientales.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.7,
            }

            with httpx.Client(timeout=30) as client:
                response = client.post(
                    f"{API_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                return result["choices"][0]["message"]["content"]

        except Exception as e:
            print(f"[LLM] Error llamando API: {e}")
            return fallback_summary(prompt)

    return fallback_summary(prompt)


def fallback_summary(prompt):
    """
    Genera resumen basado en reglas cuando no hay LLM disponible.
    """
    return (
        "📊 **Resumen de Calidad del Aire**\n\n"
        "Basado en los datos recopilados por el sistema de monitoreo, "
        "se observan niveles variables de contaminantes en las ubicaciones analizadas. "
        "Se recomienda consultar el dashboard interactivo para visualizar "
        "los datos detallados por estación y contaminante.\n\n"
        "Para activar los resúmenes generados por IA, configura la variable "
        "LLM_API_KEY en el archivo .env con una clave de API compatible con OpenAI.\n\n"
        "📈 Los datos históricos y predicciones están disponibles en las "
        "secciones de visualización del dashboard."
    )


def generate_daily_report(df=None):
    """
    Genera y guarda un resumen diario.
    """
    ensure_dirs()

    if df is None:
        df = load_latest_data()

    summary_data = prepare_summary_data(df)
    if summary_data is None:
        print("[LLM] No hay datos para generar resumen")
        return None

    prompt = generate_prompt(summary_data)
    report = call_llm_api(prompt)

    date_str = summary_data["date"]
    filename = REPORTS_DIR / f"resumen_calidad_aire_{date_str}.md"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# Resumen de Calidad del Aire - {date_str}\n\n")
        f.write(report)
        f.write("\n\n---\n")
        f.write(f"*Generado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")
        f.write(f"*Fuentes: {', '.join(summary_data['data_sources'])}*\n")

    print(f"[LLM] Resumen guardado: {filename}")
    return filename, report


if __name__ == "__main__":
    filepath, report = generate_daily_report()
    if report:
        print(f"\nResumen guardado en: {filepath}")
        print(report[:500] + "...")
