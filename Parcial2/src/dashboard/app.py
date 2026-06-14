"""
Dashboard interactivo de Calidad del Aire - Grupo 6
Monitor de Calidad del Aire y Datos Ambientales

Ejecutar con: streamlit run src/dashboard/app.py
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from streamlit_folium import folium_static


st.set_page_config(
    page_title="Monitor de Calidad del Aire",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
<style>
    .main-header {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-top: 0;
    }
    .metric-card {
        background: #f0f2f6;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
    }
    .aqi-good { color: #00e400; }
    .aqi-fair { color: #ffff00; }
    .aqi-moderate { color: #ff7e00; }
    .aqi-poor { color: #ff0000; }
    .aqi-very-poor { color: #8f3f97; }
</style>
""",
    unsafe_allow_html=True,
)


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PROCESSED_DIR = DATA_DIR / "processed"
RAW_DIR = DATA_DIR / "raw"
EXTERNAL_DIR = DATA_DIR / "external"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"


def load_data():
    """Carga datos procesados con fallback."""
    parquet_path = PROCESSED_DIR / "air_quality_merged.parquet"
    csv_path = PROCESSED_DIR / "air_quality_merged.csv"

    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    if csv_path.exists():
        return pd.read_csv(csv_path, parse_dates=["timestamp"])
    return None


def get_latest_report():
    """Obtiene el reporte diario más reciente."""
    if REPORTS_DIR.exists():
        reports = sorted(REPORTS_DIR.glob("resumen_calidad_aire_*.md"))
        if reports:
            with open(reports[-1], "r", encoding="utf-8") as f:
                return f.read()
    return "No hay resúmenes disponibles. Ejecuta src/llm/summaries.py para generar uno."


def main():
    df = load_data()

    st.sidebar.markdown(
        "<div class='main-header'>🌍 Monitor de Calidad del Aire</div>",
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(
        "<div class='sub-header'>Grupo 6 - Datos de España (BSC/UPC)</div>",
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("---")

    page = st.sidebar.radio(
        "Navegación",
        [
            "📊 Visión General",
            "🗺️ Mapas Interactivos",
            "📈 Tendencias",
            "🤖 Predicciones ML",
            "📄 Resúmenes IA",
            "ℹ️ Acerca del Proyecto",
        ],
    )

    if df is not None:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 📋 Datos cargados")
        st.sidebar.write(f"Registros: {len(df):,}")
        if "source" in df.columns:
            sources = df["source"].unique()
            st.sidebar.write(f"Fuentes: {', '.join(sources)}")
        if "timestamp" in df.columns:
            ts_col = pd.to_datetime(df["timestamp"])
            st.sidebar.write(f"Desde: {ts_col.min().strftime('%Y-%m-%d')}")
            st.sidebar.write(f"Hasta: {ts_col.max().strftime('%Y-%m-%d')}")
    else:
        st.sidebar.warning(
            "⚠️ No hay datos cargados. Ejecuta el pipeline primero:\n"
            "```\npython src/pipeline/ingest_bsc.py\n"
            "python src/pipeline/ingest_openmeteo.py\n"
            "python src/pipeline/preprocess.py\n```"
        )

    if page == "📊 Visión General":
        show_overview(df)
    elif page == "🗺️ Mapas Interactivos":
        show_maps(df)
    elif page == "📈 Tendencias":
        show_trends(df)
    elif page == "🤖 Predicciones ML":
        show_predictions(df)
    elif page == "📄 Resúmenes IA":
        show_llm_summary()
    elif page == "ℹ️ Acerca del Proyecto":
        show_about()


def show_overview(df):
    """Página de visión general con KPIs."""
    st.markdown("<div class='main-header'>📊 Visión General</div>", unsafe_allow_html=True)
    st.markdown("---")

    if df is None or len(df) == 0:
        st.warning("No hay datos disponibles. Ejecuta el pipeline de ingesta y preprocesamiento.")
        return

    cols = st.columns(4)

    pollutant_cols = {
        "pm2_5": "PM2.5 (µg/m³)",
        "pm10": "PM10 (µg/m³)",
        "no2": "NO₂ (µg/m³)",
        "european_aqi": "Índice AQI",
    }

    for i, (col, label) in enumerate(pollutant_cols.items()):
        if col in df.columns:
            val = df[col].dropna()
            if len(val) > 0:
                avg = val.mean()
                max_val = val.max()
                with cols[i]:
                    st.markdown(
                        f"""
                        <div class="metric-card">
                            <h3>{label}</h3>
                            <h2>{avg:.1f}</h2>
                            <p>Máx: {max_val:.1f}</p>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

    st.markdown("---")

    if "location" in df.columns and "no2" in df.columns:
        st.subheader("NO₂ promedio por ubicación (BSC/UPC - Barcelona)")
        loc_no2 = df.groupby("location")["no2"].mean().sort_values(ascending=False)
        fig = px.bar(
            loc_no2,
            title="NO₂ promedio por ubicación",
            labels={"value": "NO₂ (µg/m³)", "location": "Ubicación"},
            color=loc_no2.values,
            color_continuous_scale="RdYlGn_r",
        )
        st.plotly_chart(fig, use_container_width=True)

    if "timestamp" in df.columns:
        st.subheader("Distribución temporal de datos")
        df["date_only"] = pd.to_datetime(df["timestamp"]).dt.date
        daily_count = df.groupby("date_only").size().reset_index(name="count")
        fig = px.line(
            daily_count,
            x="date_only",
            y="count",
            title="Registros por día",
            labels={"date_only": "Fecha", "count": "Registros"},
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    if "source" in df.columns:
        src_counts = df["source"].value_counts()
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Distribución por fuente")
            fig = px.pie(
                values=src_counts.values,
                names=src_counts.index,
                title="Fuentes de datos",
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Resumen estadístico")
            st.dataframe(
                df.describe().round(2),
                use_container_width=True,
            )


def show_maps(df):
    """Página de mapas interactivos con Folium."""
    st.markdown("<div class='main-header'>🗺️ Mapas Interactivos</div>", unsafe_allow_html=True)
    st.markdown("---")

    from src.utils.maps import create_barcelona_map, create_madrid_map

    city = st.selectbox("Selecciona ciudad", ["Barcelona", "Madrid"])

    if city == "Barcelona":
        m = create_barcelona_map()
    else:
        m = create_madrid_map()

    folium_static(m, width=1000, height=600)

    if df is not None and "latitude" in df.columns and "longitude" in df.columns:
        st.subheader("Mapa de calor de contaminación")

        pollutant = st.selectbox(
            "Contaminante",
            [c for c in ["no2", "pm2_5", "pm10", "o3", "european_aqi"] if c in df.columns],
        )

        map_data = df[["latitude", "longitude", pollutant]].dropna().sample(
            min(500, len(df)), random_state=42
        )

        fig = px.density_mapbox(
            map_data,
            lat="latitude",
            lon="longitude",
            z=pollutant,
            radius=15,
            center={"lat": 41.3874, "lon": 2.1686},
            zoom=9,
            mapbox_style="open-street-map",
            title=f"Mapa de calor - {pollutant}",
        )
        st.plotly_chart(fig, use_container_width=True)


def show_trends(df):
    """Gráficos de tendencias temporales."""
    st.markdown("<div class='main-header'>📈 Tendencias</div>", unsafe_allow_html=True)
    st.markdown("---")

    if df is None or len(df) == 0:
        st.warning("No hay datos disponibles.")
        return

    df["date"] = pd.to_datetime(df["timestamp"]).dt.date

    pollutant_cols = [c for c in ["no2", "pm2_5", "pm10", "o3", "so2", "co", "european_aqi"] if c in df.columns]

    if not pollutant_cols:
        st.warning("No se encontraron columnas de contaminantes.")
        return

    col1, col2 = st.columns([2, 1])

    with col1:
        pollutant = st.selectbox("Selecciona contaminante", pollutant_cols)
    with col2:
        freq = st.selectbox("Frecuencia", ["Diario", "Semanal", "Mensual"])

    freq_map = {"Diario": "D", "Semanal": "W", "Mensual": "M"}
    freq_key = freq_map[freq]

    if "location" in df.columns:
        locations = df["location"].unique().tolist()
        selected_locs = st.multiselect(
            "Ubicaciones", locations, default=locations[:2] if len(locations) > 1 else locations
        )
    else:
        selected_locs = ["all"]
        df["location"] = "all"

    filtered = df[df["location"].isin(selected_locs)].copy()

    filtered["period"] = pd.to_datetime(filtered["timestamp"]).dt.to_period(freq_key).astype(str)

    trend = (
        filtered.groupby(["period", "location"])[pollutant]
        .mean()
        .reset_index()
    )

    fig = px.line(
        trend,
        x="period",
        y=pollutant,
        color="location",
        title=f"{pollutant} - {freq}",
        markers=True,
    )
    fig.update_xaxes(tickangle=45)
    st.plotly_chart(fig, use_container_width=True)

    if len(selected_locs) > 0:
        st.subheader("Comparación de contaminantes")
        recent = filtered.groupby("location")[pollutant_cols].mean().reset_index()
        fig = px.bar(
            recent.melt(id_vars=["location"], value_vars=pollutant_cols),
            x="location",
            y="value",
            color="variable",
            barmode="group",
            title="Comparación por ubicación",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Matriz de correlación entre contaminantes")
    corr = df[pollutant_cols].corr()
    fig = px.imshow(
        corr,
        text_auto=".2f",
        color_continuous_scale="RdBu_r",
        title="Correlación de contaminantes",
    )
    st.plotly_chart(fig, use_container_width=True)


def show_predictions(df):
    """Predicciones del modelo ML."""
    st.markdown("<div class='main-header'>🤖 Predicciones ML</div>", unsafe_allow_html=True)
    st.markdown("---")

    st.info(
        "El modelo de predicción utiliza Random Forest con features temporales "
        "(medias móviles, lags, componentes estacionales) para predecir "
        "concentraciones de contaminantes."
    )

    from src.ml.predict import load_processed_data, prepare_features, train_model, predict_future

    target = st.selectbox(
        "Contaminante a predecir",
        [c for c in ["no2", "pm2_5", "pm10", "o3"] if df is not None and c in df.columns],
    ) if df is not None else "no2"

    if df is not None and len(df) > 100:
        with st.spinner("Entrenando modelo..."):
            featured = prepare_features(df, target_col=target)
            model, scaler, metrics, y_test, y_pred = train_model(
                featured, target_col=target, test_size=0.2
            )

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("MAE", f"{metrics['mae']:.2f}")
        with col2:
            st.metric("RMSE", f"{metrics['rmse']:.2f}")
        with col3:
            st.metric("R²", f"{metrics['r2']:.3f}")

        fig = go.Figure()
        fig.add_trace(go.Scatter(y=y_test.values, mode="lines", name="Real", line=dict(color="blue")))
        fig.add_trace(go.Scatter(y=y_pred, mode="lines", name="Predicción", line=dict(color="red", dash="dash")))
        fig.update_layout(
            title=f"Predicción vs Real - {target}",
            xaxis_title="Muestras",
            yaxis_title=f"{target} (µg/m³)",
        )
        st.plotly_chart(fig, use_container_width=True)

        if "feature_importance" in metrics:
            st.subheader("Importancia de características")
            fi = metrics["feature_importance"]
            fi_df = pd.DataFrame(
                list(fi.items()), columns=["Feature", "Importancia"]
            ).sort_values("Importancia", ascending=True)

            fig = px.bar(
                fi_df.tail(15),
                x="Importancia",
                y="Feature",
                orientation="h",
                title="Top 15 características más importantes",
            )
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Pronóstico")
        periods = st.slider("Días a pronosticar", 1, 30, 7)
        forecast = predict_future(model, scaler, featured, periods=periods)

        fig = px.line(
            forecast,
            x="date",
            y="predicted_value",
            title=f"Pronóstico de {target} para {periods} días",
            markers=True,
        )
        fig.update_layout(
            xaxis_title="Fecha",
            yaxis_title=f"{target} (µg/m³)",
        )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(forecast, use_container_width=True)
    else:
        st.warning(
            "Se necesitan al menos 100 registros para entrenar el modelo. "
            "Ejecuta primero el pipeline de ingesta y preprocesamiento."
        )


def show_llm_summary():
    """Resúmenes generados por IA."""
    st.markdown("<div class='main-header'>📄 Resúmenes generados por IA</div>", unsafe_allow_html=True)
    st.markdown("---")

    report = get_latest_report()
    st.markdown(report)

    reports_dir = Path(__file__).resolve().parents[2] / "reports"
    if reports_dir.exists():
        report_files = sorted(reports_dir.glob("*.md"))
        if report_files:
            st.markdown("---")
            st.subheader("Historial de resúmenes")
            selected = st.selectbox(
                "Selecciona un resumen",
                report_files,
                format_func=lambda x: x.stem,
            )
            if selected:
                with open(selected, "r", encoding="utf-8") as f:
                    st.markdown(f.read())
        else:
            st.info(
                "No hay resúmenes guardados. Ejecuta:\n"
                "```\npython src/llm/summaries.py\n```"
            )


def show_about():
    """Información del proyecto."""
    st.markdown("<div class='main-header'>ℹ️ Acerca del Proyecto</div>", unsafe_allow_html=True)
    st.markdown("---")

    st.markdown(
        """
### Monitor de Calidad del Aire y Datos Ambientales
**Grupo 6** - Gestión de la Información - I Semestre 2026
Universidad Tecnológica de Panamá

#### 📌 Objetivo
Sistema de monitoreo de calidad del aire que integra datos de múltiples fuentes,
aplica aprendizaje automático para predicciones, y visualiza resultados en un
dashboard interactivo con mapas.

#### 🔗 Fuentes de Datos

| Fuente | Descripción | Tipo |
|---|---|---|
| **BSC/UPC (Barcelona)** | Datos NO₂ 2019-2024 (Nature Scientific Data) | Histórico |
| **Open-Meteo** | CAMS/Copernicus - PM2.5, PM10, NO₂, O₃, etc. | Tiempo real |
| **OpenAQ** | Estaciones de monitoreo globales | Tiempo real |

#### 🏛️ Universidad de España
Los datos provienen del **Barcelona Supercomputing Center (BSC-CNS)**,
centro de investigación asociado a la **Universitat Politècnica de Catalunya (UPC)**,
publicados en Nature Scientific Data (2026) con DOI: 10.1038/s41597-026-06592-x.

#### 🛠️ Tecnologías
- **Pipeline:** Python, Pandas, NumPy
- **ML:** Scikit-learn (Random Forest, K-Means)
- **Dashboard:** Streamlit, Plotly, Folium
- **LLM:** OpenAI API (resúmenes automáticos)
- **Mapas:** Folium, Mapbox

#### ✅ Requisitos del Parcial 2
- [x] Pipeline de datos (≥2 fuentes)
- [x] Preprocesamiento y transformación
- [x] Técnica de ML (clasificación/clustering/regresión)
- [x] Dashboard interactivo (Streamlit)
- [x] Visualización en mapas (Folium)
- [x] Documentación del proyecto
""",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
