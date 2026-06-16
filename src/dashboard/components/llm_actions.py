"""Acciones de generación de resúmenes con LLM en el dashboard."""

from __future__ import annotations

import streamlit as st

from src.config import LLM_API_URL, LLM_MODEL, LLM_PROVIDER
from src.llm.summaries import generate_daily_report


def render_llm_generate_panel() -> None:
    """Muestra el panel para generar resúmenes con el LLM configurado."""
    provider_labels = {
        "ollama": "Ollama",
        "openai": "OpenAI",
        "narrativo": "Generador narrativo",
    }
    provider_name = provider_labels.get(LLM_PROVIDER.lower(), LLM_PROVIDER)

    st.markdown("#### Generar nuevo resumen")
    if flash := st.session_state.pop("llm_report_flash", None):
        st.success(f"Resumen generado correctamente: `{flash}`")

    col_btn, col_meta = st.columns([1, 2])
    with col_btn:
        clicked = st.button(
            "Generar resumen con IA",
            type="primary",
            use_container_width=True,
            help=f"Usa {provider_name} ({LLM_MODEL}) para redactar el informe del día.",
        )
    with col_meta:
        st.caption(
            f"Proveedor: **{provider_name}** · Modelo: **{LLM_MODEL}** · "
            f"Endpoint: `{LLM_API_URL}`"
        )
        if LLM_PROVIDER.lower() == "ollama":
            st.caption("Asegúrate de que Ollama esté en ejecución en tu máquina.")

    if not clicked:
        return

    try:
        with st.spinner(f"Generando informe con {LLM_MODEL}… (puede tardar 1–2 min)"):
            path = generate_daily_report()
    except Exception as exc:
        st.error(f"No se pudo generar el resumen: {exc}")
        return

    if path is None:
        st.error(
            "No se pudo generar el informe. Comprueba que haya datos en Gold/Silver "
            "y que el servicio LLM esté disponible."
        )
        return

    st.session_state["selected_report"] = str(path)
    st.session_state["llm_report_flash"] = path.name
    st.rerun()
