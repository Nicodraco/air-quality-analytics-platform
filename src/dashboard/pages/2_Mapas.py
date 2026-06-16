import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent.parent / "bootstrap.py"))

import streamlit as st
from streamlit_folium import st_folium

from src.dashboard.components.filters import render_sidebar_filters
from src.dashboard.components.status_bar import render_status_bar
from src.dashboard.components.styles import inject_styles, render_aqi_legend
from src.dashboard.services.data import load_filtered_facts
from src.utils.maps import (
    build_station_summary,
    create_alerts_map,
    create_heatmap,
    create_station_map,
    load_latest_alerts,
)


inject_styles()
render_sidebar_filters()

df = load_filtered_facts()

st.markdown("<div class='main-title'>Mapas geográficos</div>", unsafe_allow_html=True)
render_status_bar()
render_aqi_legend()

if df.empty:
    st.warning("Sin datos. Ejecuta el pipeline ETL primero.")
    st.stop()

summary = build_station_summary(df)
layer = st.selectbox(
    "Capa",
    ["Estaciones", "Heatmap AQI", "Heatmap NO2", "Alertas geográficas"],
)

if layer == "Estaciones":
    st_folium(create_station_map(summary), height=550, use_container_width=True)
elif layer.startswith("Heatmap"):
    col = "aqi_index" if "AQI" in layer else "no2"
    st_folium(create_heatmap(summary, value_col=col), height=550, use_container_width=True)
else:
    alerts = load_latest_alerts()
    if alerts:
        st_folium(create_alerts_map(alerts), height=550, use_container_width=True)
    else:
        st.info("No hay alertas activas.")
