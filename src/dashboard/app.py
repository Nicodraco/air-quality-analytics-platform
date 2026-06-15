"""
Dashboard Streamlit - Plataforma Inteligente de Monitoreo Ambiental
Arquitectura Medallion | Modelo Estrella | AEMET + MITECO
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

from src.config import REPORTS_DIR, WHO_LIMITS
from src.gold.loader import query_facts, query_kpis
from src.ml.predict import load_training_data, train_and_predict
from src.utils.maps import (
    build_station_summary,
    create_alerts_map,
    create_heatmap,
    create_station_map,
    load_latest_alerts,
)


st.set_page_config(
    page_title="Monitoreo Ambiental Inteligente",
    page_icon="🌍",
    layout="wide",
)

st.markdown(
    """
<style>
.main-title { font-size: 2rem; font-weight: 700; }
.kpi-box { background: #f0f2f6; border-radius: 10px; padding: 16px; text-align: center; }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=300)
def load_facts():
    return query_facts(limit=5000)


@st.cache_data(ttl=300)
def load_kpis():
    return query_kpis()


def show_overview(kpis: dict, df: pd.DataFrame):
    st.markdown("<div class='main-title'>📊 Visión General - KPIs</div>", unsafe_allow_html=True)
    st.markdown("---")

    cols = st.columns(6)
    metrics = [
        ("Temp. media", kpis.get("avg_temperature"), "°C"),
        ("Humedad", kpis.get("avg_humidity"), "%"),
        ("PM10", kpis.get("avg_pm10"), "µg/m³"),
        ("PM2.5", kpis.get("avg_pm25"), "µg/m³"),
        ("NO2", kpis.get("avg_no2"), "µg/m³"),
        ("AQI", kpis.get("avg_aqi"), ""),
    ]
    for col, (label, val, unit) in zip(cols, metrics):
        with col:
            display = f"{val:.1f}{unit}" if val is not None else "N/A"
            st.markdown(
                f"<div class='kpi-box'><h4>{label}</h4><h2>{display}</h2></div>",
                unsafe_allow_html=True,
            )

    if not df.empty and "station_type" in df.columns:
        st.subheader("Registros por tipo de estación")
        fig = px.pie(df, names="station_type", title="Distribución de fuentes")
        st.plotly_chart(fig, use_container_width=True)

    critical = kpis.get("critical_stations", [])
    if critical:
        st.subheader("⚠️ Estaciones críticas (AQI > 50)")
        st.dataframe(pd.DataFrame(critical), use_container_width=True)


def show_maps(df: pd.DataFrame):
    st.markdown("<div class='main-title'>🗺️ Mapas Folium</div>", unsafe_allow_html=True)
    st.markdown("---")

    if df.empty:
        st.warning("Sin datos. Ejecuta el pipeline ETL primero.")
        return

    summary = build_station_summary(df)
    layer = st.selectbox(
        "Capa",
        ["Estaciones", "Heatmap AQI", "Heatmap NO2", "Alertas geográficas"],
    )

    if layer == "Estaciones":
        st_folium(create_station_map(summary), width=1000, height=550)
    elif layer.startswith("Heatmap"):
        col = "aqi_index" if "AQI" in layer else "no2"
        st_folium(create_heatmap(summary, value_col=col), width=1000, height=550)
    else:
        alerts = load_latest_alerts()
        if alerts:
            st_folium(create_alerts_map(alerts), width=1000, height=550)
        else:
            st.info("No hay alertas activas.")


def show_trends(df: pd.DataFrame):
    st.markdown("<div class='main-title'>📈 Tendencias</div>", unsafe_allow_html=True)
    st.markdown("---")

    if df.empty:
        st.warning("Sin datos.")
        return

    df = df.copy()
    df["measured_at"] = pd.to_datetime(df["measured_at"], utc=True)
    pollutant = st.selectbox(
        "Indicador",
        [c for c in ["pm25", "pm10", "no2", "temperature", "humidity", "aqi_index"] if c in df.columns],
    )

    daily = (
        df.groupby(df["measured_at"].dt.date)[pollutant]
        .mean()
        .reset_index()
    )
    daily.columns = ["fecha", pollutant]

    fig = px.line(daily, x="fecha", y=pollutant, markers=True, title=f"Tendencia diaria - {pollutant}")
    st.plotly_chart(fig, use_container_width=True)

    if "region" in df.columns:
        regional = df.groupby("region")[pollutant].mean().sort_values(ascending=False)
        fig2 = px.bar(regional, title=f"{pollutant} promedio por región")
        st.plotly_chart(fig2, use_container_width=True)


def show_ml():
    st.markdown("<div class='main-title'>🤖 Predicciones ML</div>", unsafe_allow_html=True)
    st.markdown("---")
    st.info("Random Forest - Horizontes: 24 h, 48 h, 7 días")

    df = load_training_data()
    if df.empty or len(df) < 50:
        st.warning("Datos insuficientes. Ejecuta el pipeline completo.")
        return

    with st.spinner("Entrenando modelo..."):
        result = train_and_predict(df)

    if not result:
        st.warning("No se pudo entrenar el modelo.")
        return

    m = result["metrics"]
    c1, c2, c3 = st.columns(3)
    c1.metric("MAE", f"{m['mae']:.2f}")
    c2.metric("RMSE", f"{m['rmse']:.2f}")
    c3.metric("R²", f"{m['r2']:.3f}")

    forecast_df = pd.DataFrame(result["forecasts"].values())
    fig = px.bar(
        forecast_df,
        x="hours",
        y="predicted_value",
        title=f"Pronóstico {m['target']} (µg/m³)",
        labels={"hours": "Horas", "predicted_value": m["target"]},
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(forecast_df, use_container_width=True)


def show_alerts():
    st.markdown("<div class='main-title'>🚨 Sistema de Alertas (OMS)</div>", unsafe_allow_html=True)
    st.markdown("---")

    st.write("Límites OMS aplicados:", WHO_LIMITS)
    alerts = load_latest_alerts()

    if not alerts:
        st.success("No hay alertas activas.")
        return

    alert_df = pd.DataFrame(alerts)
    st.dataframe(alert_df, use_container_width=True)

    critical = [a for a in alerts if a.get("severity") == "critical"]
    st.metric("Alertas críticas", len(critical))
    st.metric("Total alertas", len(alerts))


def show_llm():
    st.markdown("<div class='main-title'>📄 Resúmenes IA</div>", unsafe_allow_html=True)
    st.markdown("---")

    reports = sorted(REPORTS_DIR.glob("resumen_ambiental_*.md"))
    if not reports:
        st.info("Ejecuta: `python src/llm/summaries.py` o el pipeline completo.")
        return

    selected = st.selectbox("Reporte", reports, format_func=lambda p: p.stem)
    st.markdown(selected.read_text(encoding="utf-8"), unsafe_allow_html=False)


def main():
    st.sidebar.markdown("## 🌍 Monitoreo Ambiental")
    st.sidebar.caption("Medallion | Estrella | AEMET + MITECO")

    page = st.sidebar.radio(
        "Navegación",
        [
            "📊 KPIs",
            "🗺️ Mapas",
            "📈 Tendencias",
            "🤖 ML",
            "🚨 Alertas",
            "📄 Resúmenes IA",
        ],
    )

    df = load_facts()
    kpis = load_kpis()

    st.sidebar.markdown("---")
    st.sidebar.write(f"Registros DW: {len(df):,}")

    if page == "📊 KPIs":
        show_overview(kpis, df)
    elif page == "🗺️ Mapas":
        show_maps(df)
    elif page == "📈 Tendencias":
        show_trends(df)
    elif page == "🤖 ML":
        show_ml()
    elif page == "🚨 Alertas":
        show_alerts()
    elif page == "📄 Resúmenes IA":
        show_llm()


if __name__ == "__main__":
    main()
