import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent.parent / "bootstrap.py"))

import streamlit as st

from src.config import REPORTS_DIR
from src.dashboard.components.filters import render_sidebar_filters
from src.dashboard.components.llm_actions import render_llm_generate_panel
from src.dashboard.components.status_bar import render_status_bar
from src.dashboard.components.styles import inject_styles


inject_styles()
render_sidebar_filters()

st.markdown("<div class='main-title'>Resúmenes IA</div>", unsafe_allow_html=True)
render_status_bar()

render_llm_generate_panel()

st.markdown("---")
st.markdown("#### Informes generados")

report_patterns = ["resumen_ambiental_*.md", "resumen_calidad_aire_*.md"]
reports: list[Path] = []
for pattern in report_patterns:
    reports.extend(REPORTS_DIR.glob(pattern))
reports = sorted(set(reports), key=lambda p: p.stat().st_mtime, reverse=True)

if not reports:
    st.info(
        "Aún no hay resúmenes guardados. Pulsa **Generar resumen con IA** "
        "para crear el primero."
    )
    st.stop()

selected_path = st.session_state.get("selected_report")
default_index = 0
if selected_path:
    selected = Path(selected_path)
    if selected in reports:
        default_index = reports.index(selected)

selected_report = st.selectbox(
    "Seleccionar informe",
    options=reports,
    index=default_index,
    format_func=lambda p: p.stem.replace("_", " ").title(),
)
st.session_state["selected_report"] = str(selected_report)

st.markdown(selected_report.read_text(encoding="utf-8"), unsafe_allow_html=False)
