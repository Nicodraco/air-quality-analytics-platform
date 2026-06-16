"""
Pipeline ETL completo: Ingesta -> Bronze -> Silver -> Gold -> ML -> Alertas -> LLM
"""

import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.bronze.storage import save_bronze
from src.config import ensure_dirs
from src.gold.loader import load_gold, query_kpis
from src.ingestion.miteco import ingest_miteco
from src.ingestion.weather import ingest_weather
from src.llm.summaries import generate_daily_report
from src.ml.alerts import run_alerts
from src.ml.predict import run_ml_pipeline
from src.silver.transform import run_silver_transform


def run_full_pipeline(skip_ml: bool = False, skip_llm: bool = False) -> dict:
    """
    Ejecuta el pipeline Medallion completo.

    Returns:
        Resumen de ejecución con contadores y KPIs
    """
    ensure_dirs()
    started = datetime.now(timezone.utc)
    summary = {
        "started_at": started.isoformat(),
        "status": "ok",
        "steps": {},
        "errors": [],
    }

    print("\n" + "=" * 70)
    print("PIPELINE MEDALLION - Plataforma de Monitoreo Ambiental")
    print(f"Inicio: {started.isoformat()}")
    print("=" * 70)

    try:
        print("\n--- EXTRACCIÓN: METEOROLOGÍA (AEMET / Open-Meteo) ---")
        weather_data = ingest_weather()
        weather_key = save_bronze("weather", weather_data)
        summary["steps"]["bronze_weather"] = weather_key
        summary["steps"]["weather_source"] = weather_data.get("weather_source", "unknown")

        print("\n--- EXTRACCIÓN: MITECO ---")
        miteco_data = ingest_miteco()
        miteco_key = save_bronze("miteco", miteco_data)
        summary["steps"]["bronze_miteco"] = miteco_key

        print("\n--- SILVER ---")
        silver = run_silver_transform(weather_data, miteco_data)
        summary["steps"]["silver"] = {
            k: len(v) for k, v in silver.items() if v is not None
        }

        print("\n--- GOLD ---")
        inserted = load_gold()
        summary["steps"]["gold_inserted"] = inserted
        summary["kpis"] = query_kpis()

        if not skip_ml:
            print("\n--- ML ---")
            ml_result = run_ml_pipeline()
            summary["steps"]["ml"] = "ok" if ml_result else "skipped"

            print("\n--- ALERTAS ---")
            alerts = run_alerts()
            summary["steps"]["alerts"] = len(alerts)

        if not skip_llm:
            print("\n--- RESUMEN LLM ---")
            report_path = generate_daily_report()
            summary["steps"]["llm_report"] = str(report_path) if report_path else None

    except Exception as exc:
        summary["status"] = "error"
        summary["errors"].append(str(exc))
        print(f"\n[Pipeline] ERROR: {exc}")
        traceback.print_exc()

    finished = datetime.now(timezone.utc)
    summary["finished_at"] = finished.isoformat()
    summary["duration_seconds"] = (finished - started).total_seconds()

    print("\n" + "=" * 70)
    print(f"Pipeline finalizado: {summary['status']} ({summary['duration_seconds']:.1f}s)")
    print("=" * 70)

    return summary


if __name__ == "__main__":
    result = run_full_pipeline()
    print(result)
