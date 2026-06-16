import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent.parent / "bootstrap.py"))

import streamlit as st

from src.config import REPORTS_DIR
from src.dashboard.components.filters import render_sidebar_filters
from src.dashboard.components.status_bar import render_status_bar
from src.dashboard.components.styles import inject_styles


inject_styles()
render_sidebar_filters()

st.markdown("<div class='main-title'>Resúmenes IA</div>", unsafe_allow_html=True)
render_status_bar()

reports = sorted(REPORTS_DIR.glob("resumen_ambiental_*.md"))
if not reports:
    st.info("Ejecuta `python src/llm/summaries.py` o el pipeline completo para generar reportes.")
    st.stop()

selected = st.selectbox("Reporte", reports, format_func=lambda p: p.stem)
st.markdown(selected.read_text(encoding="utf-8"), unsafe_allow_html=False)
