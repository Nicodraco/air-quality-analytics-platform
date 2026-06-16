import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent.parent / "bootstrap.py"))

import pandas as pd
import plotly.express as px
import streamlit as st

from src.config import WHO_LIMITS
from src.dashboard.components.filters import render_sidebar_filters
from src.dashboard.components.status_bar import render_status_bar
from src.dashboard.components.styles import inject_styles
from src.dashboard.services.data import load_filtered_facts


inject_styles()
render_sidebar_filters()

df = load_filtered_facts()

st.markdown("<div class='main-title'>Tendencias temporales</div>", unsafe_allow_html=True)
render_status_bar()

if df.empty:
    st.warning("Sin datos en la ventana seleccionada.")
    st.stop()

df = df.copy()
df["measured_at"] = pd.to_datetime(df["measured_at"], utc=True)
pollutant = st.selectbox(
    "Indicador",
    [c for c in ["pm25", "pm10", "no2", "temperature", "humidity", "aqi_index"] if c in df.columns],
)

daily = df.groupby(df["measured_at"].dt.date)[pollutant].mean().reset_index()
daily.columns = ["fecha", pollutant]

fig = px.line(daily, x="fecha", y=pollutant, markers=True, title=f"Tendencia diaria — {pollutant}")
who_limit = WHO_LIMITS.get(pollutant)
if who_limit is not None:
    fig.add_hline(
        y=who_limit,
        line_dash="dash",
        line_color="red",
        annotation_text="Referencia OMS",
    )
st.plotly_chart(fig, use_container_width=True)

if "region" in df.columns:
    regional = df.groupby("region")[pollutant].mean().sort_values(ascending=False)
    fig2 = px.bar(regional, title=f"{pollutant} promedio por región")
    st.plotly_chart(fig2, use_container_width=True)
