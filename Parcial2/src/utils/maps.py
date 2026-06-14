"""
Utilidades de mapas con Folium para visualización de estaciones
de calidad del aire y datos ambientales.
"""

import folium
import pandas as pd
import numpy as np
from folium.plugins import HeatMap, MarkerCluster


AIR_QUALITY_COLORS = {
    "good": "green",
    "fair": "yellow",
    "moderate": "orange",
    "poor": "red",
    "very_poor": "purple",
    "extremely_poor": "maroon",
}


def get_aqi_color(value):
    """Asigna color según el European AQI."""
    if value is None or pd.isna(value):
        return "gray"
    if value <= 20:
        return "green"
    elif value <= 40:
        return "yellow"
    elif value <= 60:
        return "orange"
    elif value <= 80:
        return "red"
    elif value <= 100:
        return "purple"
    else:
        return "maroon"


def get_aqi_category(value):
    """Categoría textual del AQI."""
    if value is None or pd.isna(value):
        return "Sin datos"
    if value <= 20:
        return "Buena"
    elif value <= 40:
        return "Razonable"
    elif value <= 60:
        return "Moderada"
    elif value <= 80:
        return "Mala"
    elif value <= 100:
        return "Muy mala"
    else:
        return "Extremadamente mala"


def create_station_map(
    stations,
    center_lat=41.3874,
    center_lon=2.1686,
    zoom_start=12,
):
    """
    Crea mapa con estaciones de monitoreo.

    Args:
        stations: Lista de dicts con lat, lon, name, aqi_value
        center_lat, center_lon: Centro del mapa
        zoom_start: Nivel de zoom inicial

    Returns: folium.Map
    """
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start)

    for station in stations:
        popup_html = f"""
        <div style="font-family: sans-serif; min-width: 200px;">
            <h4>{station.get('name', 'Estación')}</h4>
            <b>AQI:</b> {station.get('aqi_value', 'N/A')}
            <br><b>Categoría:</b> {station.get('aqi_category', 'N/A')}
            <br><b>PM2.5:</b> {station.get('pm25', 'N/A')} µg/m³
            <br><b>PM10:</b> {station.get('pm10', 'N/A')} µg/m³
            <br><b>NO₂:</b> {station.get('no2', 'N/A')} µg/m³
            <br><b>O₃:</b> {station.get('o3', 'N/A')} µg/m³
        </div>
        """

        color = station.get("color", get_aqi_color(station.get("aqi_value")))

        folium.CircleMarker(
            location=[station["lat"], station["lon"]],
            radius=10,
            popup=folium.Popup(popup_html, max_width=300),
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            weight=2,
        ).add_to(m)

    return m


def create_heatmap(
    data_points,
    center_lat=41.3874,
    center_lon=2.1686,
    zoom_start=11,
    radius=15,
    blur=10,
):
    """
    Crea mapa de calor con datos de contaminación.

    Args:
        data_points: Lista de [lat, lon, intensity]
        center_lat, center_lon: Centro del mapa
        zoom_start: Nivel de zoom
        radius, blur: Parámetros del heatmap

    Returns: folium.Map
    """
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start)

    heat_data = [[p[0], p[1], p[2]] for p in data_points if not any(pd.isna(x) for x in p)]

    HeatMap(
        heat_data,
        radius=radius,
        blur=blur,
        max_zoom=1,
        gradient={
            0.4: "blue",
            0.6: "lime",
            0.8: "orange",
            1.0: "red",
        },
    ).add_to(m)

    return m


def create_barcelona_map():
    """
    Crea mapa interactivo de la red de monitoreo de Barcelona
    con las estaciones del BSC/Ayuntamiento.
    """
    stations = [
        {"name": "Eixample", "lat": 41.389, "lon": 2.165,
         "aqi_value": 35, "pm25": 12, "pm10": 25, "no2": 42, "o3": 55},
        {"name": "Gràcia - S. Gervasi", "lat": 41.402, "lon": 2.157,
         "aqi_value": 30, "pm25": 10, "pm10": 22, "no2": 38, "o3": 60},
        {"name": "Parc de la Ciutadella", "lat": 41.387, "lon": 2.188,
         "aqi_value": 25, "pm25": 8, "pm10": 18, "no2": 30, "o3": 65},
        {"name": "Palau Reial", "lat": 41.387, "lon": 2.117,
         "aqi_value": 40, "pm25": 14, "pm10": 28, "no2": 48, "o3": 50},
        {"name": "Poblenou", "lat": 41.407, "lon": 2.204,
         "aqi_value": 38, "pm25": 13, "pm10": 26, "no2": 45, "o3": 52},
        {"name": "Sants", "lat": 41.375, "lon": 2.136,
         "aqi_value": 42, "pm25": 15, "pm10": 30, "no2": 50, "o3": 48},
        {"name": "Vall d'Hebron", "lat": 41.427, "lon": 2.142,
         "aqi_value": 22, "pm25": 7, "pm10": 16, "no2": 25, "o3": 68},
        {"name": "Zona Universitària (UPC)", "lat": 41.386, "lon": 2.113,
         "aqi_value": 28, "pm25": 9, "pm10": 20, "no2": 32, "o3": 62},
    ]

    for s in stations:
        s["color"] = get_aqi_color(s["aqi_value"])
        s["aqi_category"] = get_aqi_category(s["aqi_value"])

    return create_station_map(
        stations,
        center_lat=41.395,
        center_lon=2.160,
        zoom_start=13,
    )


def create_madrid_map():
    """Crea mapa con estaciones de Madrid."""
    stations = [
        {"name": "Plaza España", "lat": 40.423, "lon": -3.712,
         "aqi_value": 45, "pm25": 16, "pm10": 32, "no2": 52, "o3": 45},
        {"name": "Retiro", "lat": 40.417, "lon": -3.683,
         "aqi_value": 30, "pm25": 10, "pm10": 22, "no2": 35, "o3": 58},
        {"name": "Cuatro Caminos", "lat": 40.446, "lon": -3.707,
         "aqi_value": 48, "pm25": 17, "pm10": 34, "no2": 55, "o3": 42},
        {"name": "Escuelas Aguirre", "lat": 40.421, "lon": -3.683,
         "aqi_value": 35, "pm25": 12, "pm10": 25, "no2": 40, "o3": 50},
        {"name": "Barajas", "lat": 40.472, "lon": -3.561,
         "aqi_value": 32, "pm25": 11, "pm10": 24, "no2": 38, "o3": 55},
    ]

    for s in stations:
        s["color"] = get_aqi_color(s["aqi_value"])
        s["aqi_category"] = get_aqi_category(s["aqi_value"])

    return create_station_map(
        stations, center_lat=40.425, center_lon=-3.690, zoom_start=12
    )


if __name__ == "__main__":
    m = create_barcelona_map()
    m.save("barcelona_air_quality_map.html")
    print("Mapa guardado: barcelona_air_quality_map.html")
