import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent.parent / "bootstrap.py"))

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from src.config import WHO_LIMITS
from src.dashboard.components.filters import render_sidebar_filters
from src.dashboard.components.status_bar import render_status_bar
from src.dashboard.components.styles import inject_styles
from src.utils.maps import create_alerts_map, load_latest_alerts


inject_styles()
render_sidebar_filters()

st.markdown("<div class='main-title'>Sistema de alertas (OMS)</div>", unsafe_allow_html=True)
render_status_bar()

alerts = load_latest_alerts()

if not alerts:
    st.success("No hay alertas activas.")
    with st.expander("Límites OMS aplicados"):
        st.json(WHO_LIMITS)
    st.stop()

critical = [a for a in alerts if a.get("severity") == "critical"]
warnings = [a for a in alerts if a.get("severity") == "warning"]

c1, c2, c3 = st.columns(3)
c1.metric("Total alertas", len(alerts))
c2.metric("Críticas", len(critical))
c3.metric("Advertencias", len(warnings))

alert_df = pd.DataFrame(alerts)
if "severity" in alert_df.columns:
    severity_order = {"critical": 0, "warning": 1}
    alert_df["_order"] = alert_df["severity"].map(severity_order).fillna(2)
    alert_df = alert_df.sort_values("_order").drop(columns="_order")

if "pollutant" in alert_df.columns:
    st.subheader("Alertas por contaminante")
    counts = alert_df["pollutant"].value_counts().reset_index()
    counts.columns = ["pollutant", "count"]
    fig = px.bar(counts, x="pollutant", y="count", title="Distribución de alertas")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Detalle de alertas")
st.dataframe(alert_df, use_container_width=True, hide_index=True)

geo_alerts = [a for a in alerts if a.get("latitude") is not None and a.get("longitude") is not None]
if geo_alerts:
    st.subheader("Mapa de alertas")
    st_folium(create_alerts_map(geo_alerts), height=500, use_container_width=True)

with st.expander("Límites OMS aplicados"):
    st.json(WHO_LIMITS)
