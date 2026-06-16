"""
Dashboard Streamlit - Home ejecutivo
Plataforma Inteligente de Monitoreo Ambiental
"""

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent / "bootstrap.py"))

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from src.dashboard.components.filters import render_sidebar_filters
from src.dashboard.components.kpi_cards import render_kpi_row
from src.dashboard.components.status_bar import render_status_bar
from src.dashboard.components.styles import inject_styles
from src.dashboard.services.data import load_filtered_facts, load_filtered_kpis
from src.utils.maps import build_station_summary, create_station_map, load_latest_alerts


st.set_page_config(
    page_title="Monitoreo Ambiental Inteligente",
    page_icon="🌍",
    layout="wide",
)

inject_styles()
render_sidebar_filters()

df = load_filtered_facts()
kpis = load_filtered_kpis()

st.markdown("<div class='main-title'>Visión ejecutiva</div>", unsafe_allow_html=True)
render_status_bar()

if kpis.get("error"):
    st.error(f"Error cargando KPIs: {kpis['error']}")
else:
    render_kpi_row(kpis)

st.markdown("---")
left, right = st.columns(2)

with left:
    st.subheader("Distribución AQI")
    dist = kpis.get("aqi_distribution", {})
    if any(dist.values()):
        dist_df = pd.DataFrame(
            {"categoria": list(dist.keys()), "registros": list(dist.values())}
        )
        fig = px.bar(
            dist_df,
            x="categoria",
            y="registros",
            color="categoria",
            title="Registros por categoría AQI",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sin datos de AQI en la ventana seleccionada.")

with right:
    st.subheader("Alertas críticas recientes")
    alerts = load_latest_alerts()
    critical = [a for a in alerts if a.get("severity") == "critical"][:5]
    if critical:
        st.dataframe(pd.DataFrame(critical), use_container_width=True, hide_index=True)
        st.page_link("pages/5_Alertas.py", label="Ver todas las alertas", icon="🚨")
    else:
        st.success("No hay alertas críticas activas.")

st.subheader("Mapa resumen de estaciones")
if df.empty:
    st.warning("Sin datos en la ventana seleccionada. Ejecuta el pipeline ETL primero.")
else:
    summary = build_station_summary(df)
    if summary.empty:
        st.info("No hay estaciones con coordenadas en el filtro actual.")
    else:
        st_folium(create_station_map(summary), height=420, use_container_width=True)
