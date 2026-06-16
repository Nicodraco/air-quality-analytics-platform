import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent.parent / "bootstrap.py"))

import pandas as pd
import plotly.express as px
import streamlit as st

from src.dashboard.components.filters import render_sidebar_filters
from src.dashboard.components.kpi_cards import render_kpi_row
from src.dashboard.components.status_bar import render_status_bar
from src.dashboard.components.styles import inject_styles
from src.dashboard.services.data import load_filtered_facts, load_filtered_kpis


inject_styles()
render_sidebar_filters()

df = load_filtered_facts()
kpis = load_filtered_kpis()

st.markdown("<div class='main-title'>KPIs ambientales</div>", unsafe_allow_html=True)
render_status_bar()

if kpis.get("error"):
    st.error(f"Error cargando KPIs: {kpis['error']}")
else:
    render_kpi_row(kpis)

st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    st.subheader("Distribución AQI")
    dist = kpis.get("aqi_distribution", {})
    if any(dist.values()):
        dist_df = pd.DataFrame(
            {"categoria": list(dist.keys()), "registros": list(dist.values())}
        )
        fig = px.pie(dist_df, names="categoria", values="registros", hole=0.4)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sin datos de AQI.")

with col2:
    st.subheader("Top regiones por PM2.5")
    if not df.empty and "region" in df.columns and "pm25" in df.columns:
        regional = (
            df.dropna(subset=["pm25"])
            .groupby("region")["pm25"]
            .mean()
            .sort_values(ascending=True)
            .tail(10)
        )
        fig2 = px.bar(
            regional,
            orientation="h",
            title="PM2.5 promedio por región",
            labels={"value": "PM2.5 (µg/m³)", "region": "Región"},
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Sin datos de PM2.5 por región.")

critical = kpis.get("critical_stations", [])
if critical:
    st.subheader("Estaciones críticas (AQI > 50)")
    st.dataframe(pd.DataFrame(critical), use_container_width=True, hide_index=True)
