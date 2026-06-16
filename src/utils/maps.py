"""
Mapas Folium para la plataforma de monitoreo ambiental.

Capas: estaciones meteorológicas, calidad del aire, heatmaps, alertas.
Colores: Verde = Bueno, Amarillo = Moderado, Rojo = Crítico
"""

import json
from pathlib import Path

import folium
import pandas as pd
from folium.plugins import HeatMap

from src.config import REPORTS_DIR, WHO_LIMITS

AQI_LEGEND = [
    {"label": "Bueno", "range": "≤ 25", "color": "green"},
    {"label": "Moderado", "range": "26–50", "color": "yellow"},
    {"label": "Elevado", "range": "51–75", "color": "orange"},
    {"label": "Crítico", "range": "> 75", "color": "red"},
]


def aqi_category(value: float | None) -> str:
    """Clasifica AQI en bueno, moderado o critico."""
    if value is None or pd.isna(value):
        return "sin_datos"
    if value <= 25:
        return "bueno"
    if value <= 50:
        return "moderado"
    return "critico"


def aqi_color(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "gray"
    if value <= 25:
        return "green"
    if value <= 50:
        return "yellow"
    if value <= 75:
        return "orange"
    return "red"


def aqi_label(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "Sin datos"
    if value <= 25:
        return "Bueno"
    if value <= 50:
        return "Moderado"
    return "Crítico"


def create_station_map(
    stations_df: pd.DataFrame,
    center_lat: float = 40.4,
    center_lon: float = -3.7,
    zoom: int = 6,
    value_col: str = "aqi_index",
) -> folium.Map:
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom, tiles="OpenStreetMap")

    for _, row in stations_df.iterrows():
        val = row.get(value_col)
        color = aqi_color(val)
        popup = folium.Popup(
            f"""
            <b>{row.get('station_name', 'Estación')}</b><br>
            Tipo: {row.get('station_type', 'N/A')}<br>
            Región: {row.get('region', 'N/A')}<br>
            Municipio: {row.get('municipality', 'N/A')}<br>
            AQI: {val if pd.notna(val) else 'N/A'} ({aqi_label(val)})<br>
            PM2.5: {row.get('pm25', 'N/A')} | NO2: {row.get('no2', 'N/A')}<br>
            Temp: {row.get('temperature', 'N/A')} °C
            """,
            max_width=280,
        )
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=9,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.75,
            popup=popup,
        ).add_to(m)

    return m


def create_heatmap(df: pd.DataFrame, value_col: str = "aqi_index") -> folium.Map:
    center_lat = df["latitude"].mean() if not df.empty else 40.4
    center_lon = df["longitude"].mean() if not df.empty else -3.7
    m = folium.Map(location=[center_lat, center_lon], zoom_start=6)

    heat_data = []
    for _, row in df.dropna(subset=["latitude", "longitude", value_col]).iterrows():
        intensity = min(1.0, float(row[value_col]) / 100)
        heat_data.append([row["latitude"], row["longitude"], intensity])

    if heat_data:
        HeatMap(
            heat_data,
            radius=18,
            blur=12,
            gradient={0.2: "green", 0.5: "yellow", 0.8: "orange", 1.0: "red"},
        ).add_to(m)

    return m


def create_alerts_map(alerts: list[dict]) -> folium.Map:
    m = folium.Map(location=[40.4, -3.7], zoom_start=6)
    for alert in alerts:
        lat = alert.get("latitude")
        lon = alert.get("longitude")
        if lat is None or lon is None:
            continue
        color = "red" if alert.get("severity") == "critical" else "orange"
        folium.Marker(
            location=[lat, lon],
            icon=folium.Icon(color="red" if color == "red" else "orange", icon="warning-sign"),
            popup=(
                f"{alert.get('station')}<br>"
                f"{alert.get('pollutant')}: {alert.get('value')} "
                f"(límite {alert.get('limit')})"
            ),
        ).add_to(m)
    return m


def load_latest_alerts() -> list[dict]:
    path = REPORTS_DIR / "alerts_latest.json"
    if not path.exists():
        files = sorted(REPORTS_DIR.glob("alerts_*.json"))
        if not files:
            return []
        path = files[-1]
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("alerts", [])


def build_station_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    agg = {}
    for col in ["aqi_index", "pm25", "pm10", "no2", "temperature", "humidity"]:
        if col in df.columns:
            agg[col] = "mean"

    summary = (
        df.groupby(
            ["station_id", "station_name", "station_type", "region", "municipality", "latitude", "longitude"],
            dropna=False,
        )
        .agg(agg)
        .reset_index()
    )
    return summary
