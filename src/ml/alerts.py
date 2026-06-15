"""
Sistema de alertas automáticas basado en límites OMS.

Genera alertas cuando PM10, PM2.5 o NO2 superan umbrales.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.config import REPORTS_DIR, SILVER_DIR, WHO_LIMITS, ensure_dirs
from src.gold.loader import query_facts


def _check_row(row: pd.Series) -> list[dict]:
    alerts = []
    mapping = {"pm10": "PM10", "pm25": "PM2.5", "no2": "NO2", "so2": "SO2", "o3": "O3"}
    for col, label in mapping.items():
        limit = WHO_LIMITS.get(col)
        value = row.get(col)
        if limit and pd.notna(value) and float(value) > limit:
            severity = "critical" if float(value) > limit * 1.5 else "warning"
            alerts.append({
                "pollutant": label,
                "value": round(float(value), 2),
                "limit": limit,
                "severity": severity,
                "station": row.get("station_name", "Desconocida"),
                "municipality": row.get("municipality", ""),
                "region": row.get("region", ""),
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "measured_at": str(row.get("measured_at", "")),
            })
    return alerts


def run_alerts() -> list[dict]:
    """
    Evalúa datos recientes y genera archivo de alertas.

    Returns:
        Lista de alertas detectadas
    """
    ensure_dirs()
    df = query_facts(limit=2000)

    if df.empty:
        aq_path = SILVER_DIR / "silver_air_quality.parquet"
        if aq_path.exists():
            df = pd.read_parquet(aq_path)
            df = df.rename(columns={"timestamp": "measured_at"})

    if df.empty:
        print("[Alertas] Sin datos para evaluar")
        return []

    recent = df.sort_values("measured_at", ascending=False).head(500)
    all_alerts = []
    for _, row in recent.iterrows():
        all_alerts.extend(_check_row(row))

    seen = set()
    unique_alerts = []
    for alert in all_alerts:
        key = (alert["station"], alert["pollutant"], alert["measured_at"])
        if key not in seen:
            seen.add(key)
            unique_alerts.append(alert)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"alerts_{ts}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_alerts": len(unique_alerts),
        "critical_count": sum(1 for a in unique_alerts if a["severity"] == "critical"),
        "alerts": unique_alerts,
    }

    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Alertas] {len(unique_alerts)} alertas -> {report_path}")

    latest = REPORTS_DIR / "alerts_latest.json"
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return unique_alerts


if __name__ == "__main__":
    alerts = run_alerts()
    print(f"Total: {len(alerts)}")
