"""Filtros globales del sidebar."""

import streamlit as st

from src.dashboard.services.data import WINDOW_PRESET_LABELS, WINDOW_PRESETS, load_region_options


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

    preset_keys = list(WINDOW_PRESETS.keys())
    current = st.session_state.window_preset
    preset = st.sidebar.selectbox(
        "Ventana temporal",
        options=preset_keys,
        index=preset_keys.index(current) if current in preset_keys else preset_keys.index("7d"),
        format_func=lambda k: WINDOW_PRESET_LABELS[k],
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
