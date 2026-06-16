"""
Resúmenes diarios generados con LLM a partir del Data Warehouse.

Soporta Ollama (local), OpenAI y generación narrativa automática como respaldo.
"""

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

from src.config import (
    LLM_API_KEY,
    LLM_API_URL,
    LLM_MODEL,
    LLM_PROVIDER,
    LLM_TIMEOUT_SECONDS,
    REPORTS_DIR,
    WHO_LIMITS,
    ensure_dirs,
)
from src.gold.loader import query_facts, query_kpis
from src.ml.alerts import run_alerts


def _build_prompt(kpis: dict, alerts: list, df: pd.DataFrame) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    alert_lines = [
        f"- {a['station']} ({a['municipality']}): {a['pollutant']} = "
        f"{a['value']} µg/m³ (límite OMS {a['limit']})"
        for a in alerts[:8]
    ]
    alert_text = "\n".join(alert_lines) if alert_lines else "Sin alertas activas."

    critical = kpis.get("critical_stations") or []
    critical_text = ", ".join(
        f"{s['station']} (AQI {s['avg_aqi']:.1f})" for s in critical[:5]
    ) or "Ninguna"

    return f"""Eres un analista ambiental. Redacta un informe ejecutivo diario sobre calidad del aire y clima en España.

Fecha: {today}
Registros analizados: {len(df)}

Indicadores:
- Temperatura media: {kpis.get('avg_temperature', 'N/A')} °C
- Humedad media: {kpis.get('avg_humidity', 'N/A')} %
- PM10 media: {kpis.get('avg_pm10', 'N/A')} µg/m³ (límite OMS: {WHO_LIMITS['pm10']})
- PM2.5 media: {kpis.get('avg_pm25', 'N/A')} µg/m³ (límite OMS: {WHO_LIMITS['pm25']})
- NO2 media: {kpis.get('avg_no2', 'N/A')} µg/m³ (límite OMS: {WHO_LIMITS['no2']})
- Índice AQI medio: {kpis.get('avg_aqi', 'N/A')}
- Estaciones críticas: {critical_text}

Alertas:
{alert_text}

Escribe 3-4 párrafos en español, tono profesional y claro. Incluye:
1. Evaluación general del día
2. Contaminante más preocupante y zonas afectadas
3. Relación con temperatura/humedad si es relevante
4. Recomendaciones para población general y grupos sensibles

No uses encabezados markdown ni listas numeradas. Solo párrafos.
No uses notación LaTeX ni fórmulas matemáticas; escribe los contaminantes en texto plano (PM2.5, NO2, etc.)."""


def _aqi_category(value: float | None) -> str:
    if value is None:
        return "desconocida"
    if value <= 25:
        return "buena"
    if value <= 50:
        return "moderada"
    return "mala"


def _worst_pollutant(kpis: dict) -> tuple[str, float | None, float]:
    candidates = [
        ("PM2.5", kpis.get("avg_pm25"), WHO_LIMITS["pm25"]),
        ("NO2", kpis.get("avg_no2"), WHO_LIMITS["no2"]),
        ("PM10", kpis.get("avg_pm10"), WHO_LIMITS["pm10"]),
    ]
    scored = [
        (name, val, limit, val / limit)
        for name, val, limit in candidates
        if val is not None and limit
    ]
    if not scored:
        return "PM2.5", None, WHO_LIMITS["pm25"]
    worst = max(scored, key=lambda x: x[3])
    return worst[0], worst[1], worst[2]


def generate_narrative_summary(kpis: dict, alerts: list) -> str:
    """Genera un informe narrativo completo sin depender de API externa."""
    temp = kpis.get("avg_temperature")
    humidity = kpis.get("avg_humidity")
    pm25 = kpis.get("avg_pm25")
    pm10 = kpis.get("avg_pm10")
    no2 = kpis.get("avg_no2")
    aqi = kpis.get("avg_aqi")
    critical = kpis.get("critical_stations") or []

    worst_name, worst_val, worst_limit = _worst_pollutant(kpis)
    quality = _aqi_category(aqi)

    p1 = (
        f"Durante las últimas 24 horas, la calidad del aire registrada en las estaciones "
        f"monitorizadas se clasifica como **{quality}**, con un índice AQI medio de "
        f"**{aqi:.1f}** puntos"
        if aqi is not None
        else "Durante las últimas 24 horas, la calidad del aire en las estaciones monitorizadas "
        "presenta niveles variables"
    )
    if temp is not None:
        p1 += (
            f". Las condiciones meteorológicas muestran una temperatura media de "
            f"**{temp:.1f} °C**"
        )
        if humidity is not None:
            p1 += f" y una humedad relativa del **{humidity:.1f}%**"
    p1 += "."

    p2_parts = []
    if worst_val is not None:
        ratio = worst_val / worst_limit
        p2_parts.append(
            f"El contaminante más relevante del periodo es **{worst_name}**, "
            f"con una concentración media de **{worst_val:.1f} µg/m³**, "
            f"{'superior' if ratio > 1 else 'cercano'} al límite diario recomendado "
            f"por la OMS (**{worst_limit:.0f} µg/m³**)."
        )
    if pm25 is not None and no2 is not None:
        p2_parts.append(
            f"En conjunto, PM2.5 alcanzó **{pm25:.1f} µg/m³** y NO2 **{no2:.1f} µg/m³**, "
            f"valores que {'exceden' if pm25 > WHO_LIMITS['pm25'] or no2 > WHO_LIMITS['no2'] else 'se mantienen cerca de'} "
            f"los umbrales de referencia internacional."
        )
    if critical:
        stations = ", ".join(s["station"] for s in critical[:3])
        p2_parts.append(
            f"Destacan estaciones con mayor presión ambiental: **{stations}**."
        )
    p2 = " ".join(p2_parts)

    p3 = ""
    if temp is not None and temp > 25 and humidity is not None and humidity < 55:
        p3 = (
            "La combinación de temperaturas elevadas y baja humedad favorece la acumulación "
            "de partículas en capas bajas de la atmósfera, lo que puede mantener "
            "concentraciones de contaminantes por encima de lo habitual en áreas urbanas."
        )
    elif alerts:
        p3 = (
            f"Se han detectado **{len(alerts)} alerta(s)** por superación de límites OMS, "
            "principalmente en zonas urbanas con tráfico intenso y actividad industrial."
        )
    else:
        p3 = (
            "No se registraron alertas críticas en el periodo, aunque conviene mantener "
            "seguimiento en las estaciones con AQI más elevado."
        )

    if pm10 is not None:
        p4 = (
            "Se recomienda que personas con enfermedades respiratorias, niños y adultos mayores "
            "limiten actividades prolongadas al aire libre en horas centrales del día. "
            f"La población general puede realizar actividades normales, prestando atención "
            f"a los picos de {worst_name} en las estaciones señaladas."
        )
    else:
        p4 = (
            "Se recomienda consultar el mapa de estaciones y las predicciones del dashboard "
            "para planificar actividades al aire libre, especialmente para grupos sensibles."
        )

    return "\n\n".join(filter(None, [p1, p2, p3, p4]))


def _ollama_chat_url() -> str:
    base = LLM_API_URL.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    if base.endswith("/api"):
        return f"{base}/chat"
    return f"{base}/api/chat"


def _call_ollama(prompt: str) -> str:
    url = _ollama_chat_url()
    messages = [
        {
            "role": "system",
            "content": (
                "Eres un analista ambiental experto en calidad del aire y meteorología en España. "
                "Respondes siempre en español, con tono profesional y claro."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    if url.endswith("/chat/completions"):
        payload = {
            "model": LLM_MODEL,
            "messages": messages,
            "stream": False,
            "temperature": 0.6,
        }
        with httpx.Client(timeout=LLM_TIMEOUT_SECONDS) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()

    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.6, "num_predict": 1500},
    }
    with httpx.Client(timeout=LLM_TIMEOUT_SECONDS) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "")
        if not content:
            raise RuntimeError(f"Ollama devolvió respuesta vacía: {data}")
        return content.strip()


def _call_openai(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "Experto en calidad del aire y meteorología en España."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 900,
        "temperature": 0.7,
    }
    base = LLM_API_URL.rstrip("/")
    url = f"{base}/chat/completions"
    with httpx.Client(timeout=60) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


def generate_report_text(kpis: dict, alerts: list, df: pd.DataFrame) -> tuple[str, str]:
    """
    Genera el cuerpo del informe.

    Returns:
        (texto_informe, origen) donde origen es 'ollama', 'openai' o 'narrativo'
    """
    prompt = _build_prompt(kpis, alerts, df)
    provider = LLM_PROVIDER.lower()

    if provider == "ollama":
        try:
            return _call_ollama(prompt), "ollama"
        except Exception as exc:
            print(f"[LLM] Ollama no disponible ({exc}), usando generador narrativo")

    if provider == "openai" and LLM_API_KEY and not LLM_API_KEY.startswith("your_"):
        try:
            return _call_openai(prompt), "openai"
        except Exception as exc:
            print(f"[LLM] OpenAI error ({exc}), usando generador narrativo")

    return generate_narrative_summary(kpis, alerts), "narrativo"


def _format_kpi_footer(kpis: dict) -> str:
    rows = [
        ("Temperatura media", f"{kpis['avg_temperature']:.1f} °C" if kpis.get("avg_temperature") else "—"),
        ("Humedad media", f"{kpis['avg_humidity']:.1f} %" if kpis.get("avg_humidity") else "—"),
        ("PM10 media", f"{kpis['avg_pm10']:.1f} µg/m³" if kpis.get("avg_pm10") else "—"),
        ("PM2.5 media", f"{kpis['avg_pm25']:.1f} µg/m³" if kpis.get("avg_pm25") else "—"),
        ("NO2 media", f"{kpis['avg_no2']:.1f} µg/m³" if kpis.get("avg_no2") else "—"),
        ("AQI medio", f"{kpis['avg_aqi']:.1f}" if kpis.get("avg_aqi") else "—"),
    ]
    lines = "| Indicador | Valor |\n|---|---|\n"
    lines += "\n".join(f"| {k} | {v} |" for k, v in rows)
    return lines


def generate_daily_report() -> Path | None:
    ensure_dirs()
    df = query_facts(limit=3000)
    kpis = query_kpis()
    alerts = run_alerts()

    if not kpis:
        print("[LLM] No hay KPIs disponibles")
        return None

    report, source = generate_report_text(kpis, alerts, df)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    path = REPORTS_DIR / f"resumen_ambiental_{date_str}.md"
    content = (
        f"# Resumen Ambiental Diario — {date_str}\n\n"
        f"{report}\n\n"
        f"---\n\n"
        f"### Indicadores del día\n\n"
        f"{_format_kpi_footer(kpis)}\n\n"
        f"*Generado: {generated} · Fuente: {source} · AEMET + MITECO*\n"
    )
    path.write_text(content, encoding="utf-8")
    print(f"[LLM] Resumen ({source}): {path}")
    return path


if __name__ == "__main__":
    generate_daily_report()
