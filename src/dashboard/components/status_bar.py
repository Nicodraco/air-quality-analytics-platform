"""Barra de estado de datos y alertas."""

import streamlit as st

from src.dashboard.services.data import get_data_status
from src.utils.maps import load_latest_alerts


def render_status_bar() -> None:
    status = get_data_status()
    alerts = load_latest_alerts()
    critical_count = sum(1 for a in alerts if a.get("severity") == "critical")

    source = "PostgreSQL (Gold)" if status.get("source") == "gold" else "Parquet (Silver)"
    if not status.get("db_ok"):
        st.warning("PostgreSQL no disponible. Mostrando datos desde capa Silver.")

    last = status.get("last_measured_at")
    if last is not None and not isinstance(last, str):
        if hasattr(last, "strftime"):
            last_str = last.strftime("%Y-%m-%d %H:%M UTC")
        else:
            last_str = str(last)
    else:
        last_str = "N/A"

    st.markdown(
        f"""
<div class="status-bar">
Última medición: <b>{last_str}</b> |
Fuente: <b>{source}</b> |
Registros en ventana: <b>{status.get('record_count', 0):,}</b> |
Alertas críticas: <b>{critical_count}</b>
</div>
""",
        unsafe_allow_html=True,
    )
