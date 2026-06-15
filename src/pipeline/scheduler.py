"""
Scheduler: ejecuta el pipeline ETL cada hora (configurable).
"""

import sys
import time
from datetime import datetime
from pathlib import Path

import schedule

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.config import PIPELINE_INTERVAL_MINUTES
from src.pipeline.run_pipeline import run_full_pipeline


def job():
    print(f"\n[Scheduler] Ejecución programada: {datetime.now().isoformat()}")
    run_full_pipeline()


def main():
    interval = max(1, PIPELINE_INTERVAL_MINUTES)
    print(f"[Scheduler] Pipeline cada {interval} minutos. Ctrl+C para detener.")

    schedule.every(interval).minutes.do(job)
    job()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
