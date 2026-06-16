"""Estilos compartidos del dashboard."""

import streamlit as st


def inject_styles() -> None:
    st.markdown(
        """
<style>
.main-title { font-size: 2rem; font-weight: 700; margin-bottom: 0.25rem; }
.status-bar { color: #6b7280; font-size: 0.9rem; margin-bottom: 1rem; }
.kpi-ok [data-testid="stMetricDelta"] { color: #16a34a; }
.kpi-warn [data-testid="stMetricValue"] { color: #ca8a04; }
.kpi-crit [data-testid="stMetricValue"] { color: #dc2626; }
.aqi-legend { display: flex; gap: 12px; flex-wrap: wrap; margin: 8px 0 16px; }
.aqi-legend span { padding: 4px 10px; border-radius: 6px; font-size: 0.85rem; }
.legend-green { background: #dcfce7; color: #166534; }
.legend-yellow { background: #fef9c3; color: #854d0e; }
.legend-orange { background: #ffedd5; color: #9a3412; }
.legend-red { background: #fee2e2; color: #991b1b; }
</style>
""",
        unsafe_allow_html=True,
    )


def render_aqi_legend() -> None:
    st.markdown(
        """
<div class="aqi-legend">
  <span class="legend-green">Bueno ≤ 25</span>
  <span class="legend-yellow">Moderado 26–50</span>
  <span class="legend-orange">Elevado 51–75</span>
  <span class="legend-red">Crítico &gt; 75</span>
</div>
""",
        unsafe_allow_html=True,
    )
