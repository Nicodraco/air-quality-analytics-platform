import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent.parent / "bootstrap.py"))

from datetime import datetime, timezone

import joblib
import pandas as pd
import plotly.express as px
import streamlit as st

from src.config import MODELS_DIR, WHO_LIMITS
from src.dashboard.components.filters import render_sidebar_filters
from src.dashboard.components.status_bar import render_status_bar
from src.dashboard.components.styles import inject_styles
from src.ml.predict import load_training_data, load_zone_forecasts, train_and_predict


inject_styles()
render_sidebar_filters()

st.markdown("<div class='main-title'>Predicciones ML por zona</div>", unsafe_allow_html=True)
render_status_bar()

st.info(
    "Random Forest entrenado con histórico de hasta 90 días. "
    "Los pronósticos se cargan desde el pipeline; usa el botón para reentrenar bajo demanda."
)

forecast_path = MODELS_DIR / "zone_forecasts.csv"
if forecast_path.exists():
    mtime = datetime.fromtimestamp(forecast_path.stat().st_mtime, tz=timezone.utc)
    st.caption(f"Último entrenamiento: {mtime.strftime('%Y-%m-%d %H:%M UTC')}")

metrics_path = MODELS_DIR / "zone_metrics.joblib"
if metrics_path.exists():
    metrics_by_zone = joblib.load(metrics_path)
    if metrics_by_zone:
        st.subheader("Métricas por zona (último entrenamiento)")
        metrics_df = pd.DataFrame(metrics_by_zone).T.reset_index().rename(columns={"index": "region"})
        st.dataframe(metrics_df, use_container_width=True, hide_index=True)

col1, col2 = st.columns([1, 3])
with col1:
    retrain = st.button("Reentrenar modelos", type="primary", use_container_width=True)

if retrain:
    train_df = load_training_data()
    if train_df.empty or len(train_df) < 50:
        st.warning("Datos insuficientes para entrenar. Ejecuta el pipeline completo.")
    else:
        with st.spinner("Entrenando modelos por zona..."):
            result = train_and_predict(train_df)
        if result:
            st.success("Modelos actualizados correctamente.")
            st.cache_data.clear()
            st.rerun()
        else:
            st.warning("No se pudo entrenar el modelo.")

zone_df = load_zone_forecasts()
if zone_df.empty:
    st.warning("No hay pronósticos por zona. Ejecuta el pipeline o reentrena los modelos.")
    st.stop()

regions = sorted(zone_df["region"].unique())
selected_region = st.selectbox("Zona / Región", regions)

region_fc = zone_df[zone_df["region"] == selected_region].sort_values("day_ahead")
target = region_fc["target"].iloc[0] if not region_fc.empty else "pm25"

fig = px.line(
    region_fc,
    x="forecast_date",
    y="predicted_value",
    markers=True,
    title=f"Pronóstico {target} — {selected_region}",
    labels={"forecast_date": "Fecha", "predicted_value": f"{target} (µg/m³)"},
)
fig.add_hline(
    y=WHO_LIMITS.get(target, 25),
    line_dash="dash",
    line_color="red",
    annotation_text="Referencia OMS",
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Comparativa entre zonas")
pivot = zone_df.pivot_table(
    index="forecast_date", columns="region", values="predicted_value", aggfunc="mean"
)
fig2 = px.line(
    pivot.reset_index(),
    x="forecast_date",
    y=pivot.columns.tolist(),
    markers=True,
    title=f"Pronóstico {target} por zona",
)
st.plotly_chart(fig2, use_container_width=True)
st.dataframe(zone_df, use_container_width=True, hide_index=True)
