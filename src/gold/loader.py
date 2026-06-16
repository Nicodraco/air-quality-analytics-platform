"""
Capa Gold: carga al Data Warehouse PostgreSQL (Modelo Estrella).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.config import SILVER_DIR, postgres_url
from src.utils.maps import aqi_category


POLLUTANT_SEED = [
    ("pm10", "µg/m³", 45.0),
    ("pm25", "µg/m³", 15.0),
    ("no2", "µg/m³", 25.0),
    ("so2", "µg/m³", 40.0),
    ("o3", "µg/m³", 100.0),
    ("co", "µg/m³", 4000.0),
]


def get_engine() -> Engine:
    return create_engine(postgres_url(), pool_pre_ping=True)


def init_schema(engine: Engine | None = None) -> None:
    """Aplica schema SQL si las tablas no existen."""
    from pathlib import Path

    engine = engine or get_engine()
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path, encoding="utf-8") as f:
        sql = f.read()
    with engine.begin() as conn:
        for statement in sql.split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))


def _upsert_date(conn, dt: datetime) -> int:
    full_date = dt.date()
    result = conn.execute(
        text("SELECT date_key FROM dim_date WHERE full_date = :d"),
        {"d": full_date},
    ).fetchone()
    if result:
        return result[0]

    quarter = (dt.month - 1) // 3 + 1
    week = dt.isocalendar()[1]
    result = conn.execute(
        text("""
            INSERT INTO dim_date (full_date, day, month, year, quarter, week)
            VALUES (:full_date, :day, :month, :year, :quarter, :week)
            RETURNING date_key
        """),
        {
            "full_date": full_date,
            "day": dt.day,
            "month": dt.month,
            "year": dt.year,
            "quarter": quarter,
            "week": week,
        },
    )
    return result.fetchone()[0]


def _upsert_station(conn, row: pd.Series) -> int:
    result = conn.execute(
        text("""
            SELECT station_key FROM dim_station
            WHERE station_id = :sid AND source = :src
        """),
        {"sid": str(row["station_id"]), "src": row["source"]},
    ).fetchone()
    if result:
        return result[0]

    result = conn.execute(
        text("""
            INSERT INTO dim_station (station_id, station_name, source, station_type)
            VALUES (:sid, :name, :src, :stype)
            RETURNING station_key
        """),
        {
            "sid": str(row["station_id"]),
            "name": row.get("station_name"),
            "src": row["source"],
            "stype": row.get("station_type"),
        },
    )
    return result.fetchone()[0]


def _upsert_location(conn, row: pd.Series) -> int:
    result = conn.execute(
        text("""
            SELECT location_key FROM dim_location
            WHERE country = :country AND region = :region
              AND municipality = :municipality
              AND latitude = :lat AND longitude = :lon
        """),
        {
            "country": row.get("country", "España"),
            "region": row.get("region"),
            "municipality": row.get("municipality"),
            "lat": float(row["latitude"]) if pd.notna(row.get("latitude")) else None,
            "lon": float(row["longitude"]) if pd.notna(row.get("longitude")) else None,
        },
    ).fetchone()
    if result:
        return result[0]

    result = conn.execute(
        text("""
            INSERT INTO dim_location
                (country, region, province, municipality, latitude, longitude)
            VALUES (:country, :region, :region, :municipality, :lat, :lon)
            RETURNING location_key
        """),
        {
            "country": row.get("country", "España"),
            "region": row.get("region"),
            "municipality": row.get("municipality"),
            "lat": float(row["latitude"]) if pd.notna(row.get("latitude")) else None,
            "lon": float(row["longitude"]) if pd.notna(row.get("longitude")) else None,
        },
    )
    return result.fetchone()[0]


def _load_silver_tables() -> dict[str, pd.DataFrame]:
    tables = {}
    for name in ["silver_weather", "silver_air_quality", "silver_stations"]:
        path = SILVER_DIR / f"{name}.parquet"
        if path.exists():
            tables[name] = pd.read_parquet(path)
        else:
            tables[name] = pd.DataFrame()
    return tables


def load_gold() -> int:
    """
    Carga datos Silver al Data Warehouse Gold.

    Returns:
        Número de filas insertadas en fact_environmental_measures
    """
    print("=" * 60)
    print("GOLD LAYER - Data Warehouse (Modelo Estrella)")
    print("=" * 60)

    silver = _load_silver_tables()
    weather = silver.get("silver_weather", pd.DataFrame())
    air_quality = silver.get("silver_air_quality", pd.DataFrame())

    if weather.empty and air_quality.empty:
        print("[Gold] No hay datos Silver para cargar")
        return 0

    engine = get_engine()
    init_schema(engine)
    inserted = 0

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM fact_environmental_measures"))
        print("[Gold] Tabla de hechos limpiada para recarga incremental")

        for _, row in weather.iterrows():
            ts = pd.to_datetime(row["timestamp"], utc=True)
            date_key = _upsert_date(conn, ts.to_pydatetime())
            station_key = _upsert_station(conn, row)
            location_key = _upsert_location(conn, row)

            conn.execute(
                text("""
                    INSERT INTO fact_environmental_measures
                        (date_key, station_key, location_key, measured_at,
                         temperature, humidity, precipitation, wind_speed)
                    VALUES
                        (:date_key, :station_key, :location_key, :measured_at,
                         :temperature, :humidity, :precipitation, :wind_speed)
                """),
                {
                    "date_key": date_key,
                    "station_key": station_key,
                    "location_key": location_key,
                    "measured_at": ts,
                    "temperature": row.get("temperature"),
                    "humidity": row.get("humidity"),
                    "precipitation": row.get("precipitation"),
                    "wind_speed": row.get("wind_speed"),
                },
            )
            inserted += 1

        for _, row in air_quality.iterrows():
            ts = pd.to_datetime(row["timestamp"], utc=True)
            date_key = _upsert_date(conn, ts.to_pydatetime())
            station_key = _upsert_station(conn, row)
            location_key = _upsert_location(conn, row)

            conn.execute(
                text("""
                    INSERT INTO fact_environmental_measures
                        (date_key, station_key, location_key, measured_at,
                         pm10, pm25, no2, so2, o3, co, aqi_index)
                    VALUES
                        (:date_key, :station_key, :location_key, :measured_at,
                         :pm10, :pm25, :no2, :so2, :o3, :co, :aqi_index)
                """),
                {
                    "date_key": date_key,
                    "station_key": station_key,
                    "location_key": location_key,
                    "measured_at": ts,
                    "pm10": row.get("pm10"),
                    "pm25": row.get("pm25"),
                    "no2": row.get("no2"),
                    "so2": row.get("so2"),
                    "o3": row.get("o3"),
                    "co": row.get("co"),
                    "aqi_index": row.get("aqi_index"),
                },
            )
            inserted += 1

    print(f"[Gold] {inserted} registros cargados en fact_environmental_measures")
    return inserted


@dataclass
class QueryFilters:
    since: datetime | None = None
    until: datetime | None = None
    regions: list[str] | None = None
    station_types: list[str] | None = None


_FACTS_SELECT = """
    SELECT
        f.measured_at,
        f.temperature, f.humidity, f.precipitation, f.wind_speed,
        f.pm10, f.pm25, f.no2, f.so2, f.o3, f.co, f.aqi_index,
        ds.station_id, ds.station_name, ds.source, ds.station_type,
        dl.region, dl.municipality, dl.latitude, dl.longitude
    FROM fact_environmental_measures f
    JOIN dim_station ds ON f.station_key = ds.station_key
    JOIN dim_location dl ON f.location_key = dl.location_key
"""


def _default_window(days: int = 7) -> tuple[datetime, datetime]:
    until = datetime.now(timezone.utc)
    since = until - timedelta(days=days)
    return since, until


def _build_filter_clause(filters: QueryFilters | None) -> tuple[str, dict]:
    """Construye cláusula WHERE y parámetros para filtros opcionales."""
    clauses: list[str] = []
    params: dict = {}

    if not filters:
        return "", params

    if filters.since is not None:
        clauses.append("f.measured_at >= :since")
        params["since"] = filters.since
    if filters.until is not None:
        clauses.append("f.measured_at <= :until")
        params["until"] = filters.until
    if filters.regions:
        placeholders = ", ".join(f":region_{i}" for i in range(len(filters.regions)))
        clauses.append(f"dl.region IN ({placeholders})")
        for i, region in enumerate(filters.regions):
            params[f"region_{i}"] = region
    if filters.station_types:
        placeholders = ", ".join(f":stype_{i}" for i in range(len(filters.station_types)))
        clauses.append(f"ds.station_type IN ({placeholders})")
        for i, stype in enumerate(filters.station_types):
            params[f"stype_{i}"] = stype

    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def check_db_connection(engine: Engine | None = None) -> bool:
    engine = engine or get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def get_available_regions(engine: Engine | None = None) -> list[str]:
    engine = engine or get_engine()
    sql = text("""
        SELECT DISTINCT dl.region
        FROM dim_location dl
        WHERE dl.region IS NOT NULL
        ORDER BY dl.region
    """)
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [r[0] for r in rows if r[0]]
    except Exception as exc:
        print(f"[Gold] Error get_available_regions: {exc}")
        return []


def _scalar_avg(
    conn,
    column: str,
    extra_where: str,
    params: dict,
) -> float | None:
    sql = f"""
        SELECT AVG(f.{column})
        FROM fact_environmental_measures f
        JOIN dim_station ds ON f.station_key = ds.station_key
        JOIN dim_location dl ON f.location_key = dl.location_key
        WHERE f.{column} IS NOT NULL {extra_where}
    """
    val = conn.execute(text(sql), params).scalar()
    return round(float(val), 2) if val is not None else None


def _period_metrics(conn, filter_clause: str, params: dict) -> dict:
    return {
        "avg_temperature": _scalar_avg(conn, "temperature", filter_clause, params),
        "avg_humidity": _scalar_avg(conn, "humidity", filter_clause, params),
        "avg_pm10": _scalar_avg(conn, "pm10", filter_clause, params),
        "avg_pm25": _scalar_avg(conn, "pm25", filter_clause, params),
        "avg_no2": _scalar_avg(conn, "no2", filter_clause, params),
        "avg_aqi": _scalar_avg(conn, "aqi_index", filter_clause, params),
    }


def _critical_stations(conn, filter_clause: str, params: dict) -> list[dict]:
    sql = f"""
        SELECT ds.station_name, AVG(f.aqi_index) AS avg_aqi
        FROM fact_environmental_measures f
        JOIN dim_station ds ON f.station_key = ds.station_key
        JOIN dim_location dl ON f.location_key = dl.location_key
        WHERE f.aqi_index IS NOT NULL {filter_clause}
        GROUP BY ds.station_name
        HAVING AVG(f.aqi_index) > 50
        ORDER BY avg_aqi DESC
        LIMIT 10
    """
    rows = conn.execute(text(sql), params).fetchall()
    return [{"station": r[0], "avg_aqi": float(r[1])} for r in rows]


def _aqi_distribution(conn, filter_clause: str, params: dict) -> dict:
    sql = f"""
        SELECT f.aqi_index
        FROM fact_environmental_measures f
        JOIN dim_station ds ON f.station_key = ds.station_key
        JOIN dim_location dl ON f.location_key = dl.location_key
        WHERE f.aqi_index IS NOT NULL {filter_clause}
    """
    rows = conn.execute(text(sql), params).fetchall()
    dist = {"bueno": 0, "moderado": 0, "critico": 0}
    for (val,) in rows:
        cat = aqi_category(float(val))
        if cat in dist:
            dist[cat] += 1
    return dist


def _compute_delta(current: dict, previous: dict) -> dict:
    delta = {}
    for key in current:
        cur = current.get(key)
        prev = previous.get(key)
        if cur is not None and prev is not None:
            delta[key] = round(cur - prev, 2)
        else:
            delta[key] = None
    return delta


def query_kpis(
    engine: Engine | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    regions: list[str] | None = None,
    station_types: list[str] | None = None,
    enriched: bool = False,
) -> dict:
    """Consulta KPIs desde el Data Warehouse."""
    engine = engine or get_engine()
    filters = QueryFilters(since=since, until=until, regions=regions, station_types=station_types)

    if enriched and since is None and until is None:
        since, until = _default_window(days=7)
        filters = QueryFilters(since=since, until=until, regions=regions, station_types=station_types)

    base_clause, base_params = _build_filter_clause(filters)
    period_clause = base_clause.replace(" WHERE ", " AND ") if base_clause else ""

    try:
        with engine.connect() as conn:
            current = _period_metrics(conn, period_clause, base_params)
            critical = _critical_stations(conn, period_clause, base_params)
            aqi_dist = _aqi_distribution(conn, period_clause, base_params)

            last_sql = f"""
                SELECT MAX(f.measured_at)
                FROM fact_environmental_measures f
                JOIN dim_station ds ON f.station_key = ds.station_key
                JOIN dim_location dl ON f.location_key = dl.location_key
                {base_clause}
            """
            last_measured = conn.execute(text(last_sql), base_params).scalar()

            previous = {k: None for k in current}
            delta = {k: None for k in current}
            if since is not None and until is not None:
                duration = until - since
                prev_until = since
                prev_since = since - duration
                prev_filters = QueryFilters(
                    since=prev_since,
                    until=prev_until,
                    regions=regions,
                    station_types=station_types,
                )
                prev_clause, prev_params = _build_filter_clause(prev_filters)
                prev_period = prev_clause.replace(" WHERE ", " AND ") if prev_clause else ""
                previous = _period_metrics(conn, prev_period, prev_params)
                delta = _compute_delta(current, previous)

            if not enriched:
                current["critical_stations"] = critical
                return current

            return {
                "window": {"since": since, "until": until},
                "current": current,
                "previous": previous,
                "delta": delta,
                "critical_stations": critical,
                "last_measured_at": last_measured,
                "aqi_distribution": aqi_dist,
            }
    except Exception as exc:
        print(f"[Gold] Error consultando KPIs: {exc}")
        if enriched:
            return {"error": str(exc)}
        return {}


def query_facts(
    limit: int = 5000,
    since: datetime | None = None,
    until: datetime | None = None,
    regions: list[str] | None = None,
    station_types: list[str] | None = None,
) -> pd.DataFrame:
    """Obtiene hechos con dimensiones para dashboard/ML."""
    engine = get_engine()
    filters = QueryFilters(since=since, until=until, regions=regions, station_types=station_types)
    where_clause, params = _build_filter_clause(filters)
    params["limit"] = limit
    sql = text(
        _FACTS_SELECT
        + where_clause
        + " ORDER BY f.measured_at DESC LIMIT :limit"
    )
    try:
        return pd.read_sql(sql, engine, params=params)
    except Exception as exc:
        print(f"[Gold] Error query_facts: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    load_gold()
