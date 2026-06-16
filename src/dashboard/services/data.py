"""Capa de datos del dashboard con caché, filtros y fallback Silver."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from src.config import INGESTION_LOOKBACK_DAYS, ML_MIN_TRAINING_DAYS, SILVER_DIR
from src.gold.loader import check_db_connection, get_available_regions, query_facts, query_kpis
from src.utils.maps import aqi_category

WINDOW_PRESETS = {
    "24h": 1,
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "6m": 180,
    "1y": 365,
    "2y": 730,
    "3y": 1095,
    "4y": 1460,
    "5y": 1825,
}

WINDOW_PRESET_LABELS = {
    "24h": "Últimas 24 h",
    "7d": "Últimos 7 días",
    "30d": "1 mes",
    "90d": "Últimos 90 días",
    "6m": "6 meses",
    "1y": "1 año",
    "2y": "2 años",
    "3y": "3 años",
    "4y": "4 años",
    "5y": "5 años",
}

_DATA_STATUS: dict = {"source": "gold", "db_ok": True, "record_count": 0, "last_measured_at": None}


def get_window_bounds(preset: str) -> tuple[datetime, datetime]:
    days = WINDOW_PRESETS.get(preset, 7)
    until = datetime.now(timezone.utc)
    since = until - timedelta(days=days)
    return since, until


def get_filter_context() -> dict:
    preset = st.session_state.get("window_preset", "7d")
    since, until = get_window_bounds(preset)
    regions = st.session_state.get("filter_regions") or None
    station_types = st.session_state.get("filter_station_types") or None
    if regions == []:
        regions = None
    if station_types == []:
        station_types = None
    return {
        "since": since,
        "until": until,
        "regions": regions,
        "station_types": station_types,
        "preset": preset,
    }


def _load_silver_facts() -> pd.DataFrame:
    frames = []
    for name in ["silver_weather", "silver_air_quality"]:
        path = SILVER_DIR / f"{name}.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            df = df.rename(columns={"timestamp": "measured_at"})
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["measured_at"] = pd.to_datetime(df["measured_at"], utc=True)
    return df.sort_values("measured_at", ascending=False)


def _apply_pandas_filters(df: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["measured_at"] = pd.to_datetime(out["measured_at"], utc=True)
    if ctx.get("since"):
        out = out[out["measured_at"] >= ctx["since"]]
    if ctx.get("until"):
        out = out[out["measured_at"] <= ctx["until"]]
    if ctx.get("regions"):
        out = out[out["region"].isin(ctx["regions"])]
    if ctx.get("station_types"):
        out = out[out["station_type"].isin(ctx["station_types"])]
    return out


def _silver_kpis(df: pd.DataFrame, ctx: dict) -> dict:
    if df.empty:
        return {"error": "Sin datos Silver"}

    def _metrics(frame: pd.DataFrame) -> dict:
        return {
            "avg_temperature": _safe_mean(frame, "temperature"),
            "avg_humidity": _safe_mean(frame, "humidity"),
            "avg_pm10": _safe_mean(frame, "pm10"),
            "avg_pm25": _safe_mean(frame, "pm25"),
            "avg_no2": _safe_mean(frame, "no2"),
            "avg_aqi": _safe_mean(frame, "aqi_index"),
        }

    current_df = _apply_pandas_filters(df, ctx)
    current = _metrics(current_df)

    since = ctx.get("since")
    until = ctx.get("until")
    previous = {k: None for k in current}
    delta = {k: None for k in current}
    if since and until:
        duration = until - since
        prev_ctx = {**ctx, "since": since - duration, "until": since}
        previous = _metrics(_apply_pandas_filters(df, prev_ctx))
        delta = {
            k: round(current[k] - previous[k], 2)
            if current.get(k) is not None and previous.get(k) is not None
            else None
            for k in current
        }

    critical = []
    if "aqi_index" in current_df.columns and "station_name" in current_df.columns:
        grouped = (
            current_df.dropna(subset=["aqi_index"])
            .groupby("station_name")["aqi_index"]
            .mean()
            .reset_index()
        )
        critical = [
            {"station": r["station_name"], "avg_aqi": round(float(r["aqi_index"]), 2)}
            for _, r in grouped[grouped["aqi_index"] > 50].iterrows()
        ]

    aqi_dist = {"bueno": 0, "moderado": 0, "critico": 0}
    if "aqi_index" in current_df.columns:
        for val in current_df["aqi_index"].dropna():
            cat = aqi_category(float(val))
            if cat in aqi_dist:
                aqi_dist[cat] += 1

    last_measured = current_df["measured_at"].max() if not current_df.empty else None

    return {
        "window": {"since": since, "until": until},
        "current": current,
        "previous": previous,
        "delta": delta,
        "critical_stations": critical,
        "last_measured_at": last_measured,
        "aqi_distribution": aqi_dist,
    }


def _safe_mean(df: pd.DataFrame, col: str) -> float | None:
    if col not in df.columns or df[col].dropna().empty:
        return None
    return round(float(df[col].mean()), 2)


@st.cache_data(ttl=300)
def _cached_facts(
    since_iso: str,
    until_iso: str,
    regions: tuple[str, ...] | None,
    station_types: tuple[str, ...] | None,
    limit: int,
    use_silver: bool,
) -> pd.DataFrame:
    ctx = {
        "since": datetime.fromisoformat(since_iso),
        "until": datetime.fromisoformat(until_iso),
        "regions": list(regions) if regions else None,
        "station_types": list(station_types) if station_types else None,
    }
    if use_silver:
        return _apply_pandas_filters(_load_silver_facts(), ctx).head(limit)
    return query_facts(
        limit=limit,
        since=ctx["since"],
        until=ctx["until"],
        regions=ctx["regions"],
        station_types=ctx["station_types"],
    )


@st.cache_data(ttl=300)
def _cached_kpis(
    since_iso: str,
    until_iso: str,
    regions: tuple[str, ...] | None,
    station_types: tuple[str, ...] | None,
    use_silver: bool,
) -> dict:
    ctx = {
        "since": datetime.fromisoformat(since_iso),
        "until": datetime.fromisoformat(until_iso),
        "regions": list(regions) if regions else None,
        "station_types": list(station_types) if station_types else None,
    }
    if use_silver:
        return _silver_kpis(_load_silver_facts(), ctx)
    return query_kpis(
        since=ctx["since"],
        until=ctx["until"],
        regions=ctx["regions"],
        station_types=ctx["station_types"],
        enriched=True,
    )


def load_filtered_facts(limit: int = 5000) -> pd.DataFrame:
    global _DATA_STATUS
    ctx = get_filter_context()
    db_ok = check_db_connection()
    use_silver = not db_ok
    regions = tuple(ctx["regions"]) if ctx["regions"] else None
    station_types = tuple(ctx["station_types"]) if ctx["station_types"] else None

    df = _cached_facts(
        ctx["since"].isoformat(),
        ctx["until"].isoformat(),
        regions,
        station_types,
        limit,
        use_silver,
    )
    last_measured = None
    if not df.empty and "measured_at" in df.columns:
        last_measured = pd.to_datetime(df["measured_at"], utc=True).max()

    _DATA_STATUS = {
        "source": "silver" if use_silver else "gold",
        "db_ok": db_ok,
        "record_count": len(df),
        "last_measured_at": last_measured,
    }
    return df


def load_filtered_kpis() -> dict:
    global _DATA_STATUS
    ctx = get_filter_context()
    db_ok = check_db_connection()
    use_silver = not db_ok
    regions = tuple(ctx["regions"]) if ctx["regions"] else None
    station_types = tuple(ctx["station_types"]) if ctx["station_types"] else None

    kpis = _cached_kpis(
        ctx["since"].isoformat(),
        ctx["until"].isoformat(),
        regions,
        station_types,
        use_silver,
    )
    if not _DATA_STATUS.get("record_count"):
        _DATA_STATUS = {
            "source": "silver" if use_silver else "gold",
            "db_ok": db_ok,
            "record_count": 0,
            "last_measured_at": kpis.get("last_measured_at"),
        }
    return kpis


def get_data_status() -> dict:
    return dict(_DATA_STATUS)


_SILVER_DATASETS = (
    ("silver_air_quality", "Calidad del aire"),
    ("silver_weather", "Meteorología"),
)


@st.cache_data(ttl=300)
def get_storage_coverage() -> dict:
    """Resumen de datos persistidos en Silver: días cubiertos y volumen."""
    datasets: list[dict] = []

    for filename, label in _SILVER_DATASETS:
        path = SILVER_DIR / f"{filename}.parquet"
        if not path.exists():
            datasets.append({
                "key": filename,
                "label": label,
                "records": 0,
                "days": 0,
                "since": None,
                "until": None,
            })
            continue

        df = pd.read_parquet(path)
        if df.empty or "timestamp" not in df.columns:
            datasets.append({
                "key": filename,
                "label": label,
                "records": 0,
                "days": 0,
                "since": None,
                "until": None,
            })
            continue

        ts = pd.to_datetime(df["timestamp"], utc=True)
        datasets.append({
            "key": filename,
            "label": label,
            "records": len(df),
            "days": int(ts.dt.floor("D").nunique()),
            "since": ts.min().date(),
            "until": ts.max().date(),
        })

    return {
        "datasets": datasets,
        "lookback_days": INGESTION_LOOKBACK_DAYS,
        "ml_min_training_days": ML_MIN_TRAINING_DAYS,
    }


def load_region_options() -> list[str]:
    db_ok = check_db_connection()
    if db_ok:
        regions = get_available_regions()
        if regions:
            return regions
    df = _load_silver_facts()
    if df.empty or "region" not in df.columns:
        return []
    return sorted(df["region"].dropna().unique().tolist())
