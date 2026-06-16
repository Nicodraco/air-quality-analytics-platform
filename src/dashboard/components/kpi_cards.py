"""Tarjetas KPI reutilizables."""

import streamlit as st

from src.config import WHO_LIMITS


def _who_status(key: str, value: float | None) -> str | None:
    if value is None:
        return None
    limit_key = key.replace("avg_", "")
    limit = WHO_LIMITS.get(limit_key)
    if limit is None:
        return None
    if value <= limit:
        return "ok"
    if value <= limit * 1.5:
        return "warn"
    return "crit"


def render_kpi_row(kpis: dict, compact: bool = False) -> None:
    current = kpis.get("current", kpis)
    delta = kpis.get("delta", {})

    metrics = [
        ("avg_temperature", "Temp. media", "°C"),
        ("avg_humidity", "Humedad", "%"),
        ("avg_pm10", "PM10", "µg/m³"),
        ("avg_pm25", "PM2.5", "µg/m³"),
        ("avg_no2", "NO2", "µg/m³"),
        ("avg_aqi", "AQI", ""),
    ]

    cols = st.columns(6 if not compact else 3)
    display_metrics = metrics if not compact else metrics[:3]

    for col, (key, label, unit) in zip(cols, display_metrics):
        val = current.get(key)
        d = delta.get(key)
        display = f"{val:.1f} {unit}".strip() if val is not None else "N/A"

        with col:
            st.metric(label=label, value=display, delta=d)
            status = _who_status(key, val)
            if status == "crit":
                st.caption("Crítico vs OMS")
            elif status == "warn":
                st.caption("Elevado vs OMS")
