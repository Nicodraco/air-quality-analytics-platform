"""Filtros globales del sidebar."""

import streamlit as st

from src.dashboard.services.data import WINDOW_PRESETS, load_region_options


def _init_session_state() -> None:
    if "window_preset" not in st.session_state:
        st.session_state.window_preset = "7d"
    if "filter_regions" not in st.session_state:
        st.session_state.filter_regions = []
    if "filter_station_types" not in st.session_state:
        st.session_state.filter_station_types = []


def render_sidebar_filters() -> None:
    _init_session_state()

    st.sidebar.markdown("## Monitoreo Ambiental")
    st.sidebar.caption("Medallion | Estrella | AEMET + MITECO")
    st.sidebar.markdown("---")
    st.sidebar.subheader("Filtros")

    preset = st.sidebar.selectbox(
        "Ventana temporal",
        options=list(WINDOW_PRESETS.keys()),
        index=list(WINDOW_PRESETS.keys()).index(st.session_state.window_preset),
        format_func=lambda k: {"24h": "Últimas 24 h", "7d": "Últimos 7 días", "30d": "Últimos 30 días", "90d": "Últimos 90 días"}[k],
    )
    st.session_state.window_preset = preset

    region_options = load_region_options()
    if region_options:
        selected_regions = st.sidebar.multiselect(
            "Regiones",
            options=region_options,
            default=st.session_state.filter_regions or region_options,
        )
        st.session_state.filter_regions = selected_regions
    else:
        st.sidebar.caption("Sin regiones disponibles")

    selected_types = st.sidebar.multiselect(
        "Tipo de estación",
        options=["meteorological", "air_quality"],
        default=st.session_state.filter_station_types or ["meteorological", "air_quality"],
        format_func=lambda t: "Meteorológica" if t == "meteorological" else "Calidad del aire",
    )
    st.session_state.filter_station_types = selected_types

    if st.sidebar.button("Refrescar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
