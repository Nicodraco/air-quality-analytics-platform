"""
Capa Gold: carga al Data Warehouse PostgreSQL (Modelo Estrella).
"""

from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.config import SILVER_DIR, postgres_url


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


def query_kpis(engine: Engine | None = None) -> dict:
    """Consulta KPIs desde el Data Warehouse."""
    engine = engine or get_engine()
    kpis = {}

    queries = {
        "avg_temperature": "SELECT AVG(temperature) FROM fact_environmental_measures WHERE temperature IS NOT NULL",
        "avg_humidity": "SELECT AVG(humidity) FROM fact_environmental_measures WHERE humidity IS NOT NULL",
        "avg_pm10": "SELECT AVG(pm10) FROM fact_environmental_measures WHERE pm10 IS NOT NULL",
        "avg_pm25": "SELECT AVG(pm25) FROM fact_environmental_measures WHERE pm25 IS NOT NULL",
        "avg_no2": "SELECT AVG(no2) FROM fact_environmental_measures WHERE no2 IS NOT NULL",
        "avg_aqi": "SELECT AVG(aqi_index) FROM fact_environmental_measures WHERE aqi_index IS NOT NULL",
        "critical_stations": """
            SELECT ds.station_name, AVG(f.aqi_index) AS avg_aqi
            FROM fact_environmental_measures f
            JOIN dim_station ds ON f.station_key = ds.station_key
            WHERE f.aqi_index IS NOT NULL
            GROUP BY ds.station_name
            HAVING AVG(f.aqi_index) > 50
            ORDER BY avg_aqi DESC
            LIMIT 10
        """,
    }

    try:
        with engine.connect() as conn:
            for key, sql in queries.items():
                if key == "critical_stations":
                    rows = conn.execute(text(sql)).fetchall()
                    kpis[key] = [{"station": r[0], "avg_aqi": float(r[1])} for r in rows]
                else:
                    val = conn.execute(text(sql)).scalar()
                    kpis[key] = round(float(val), 2) if val is not None else None
    except Exception as exc:
        print(f"[Gold] Error consultando KPIs: {exc}")

    return kpis


def query_facts(limit: int = 5000) -> pd.DataFrame:
    """Obtiene hechos con dimensiones para dashboard/ML."""
    engine = get_engine()
    sql = text("""
        SELECT
            f.measured_at,
            f.temperature, f.humidity, f.precipitation, f.wind_speed,
            f.pm10, f.pm25, f.no2, f.so2, f.o3, f.co, f.aqi_index,
            ds.station_id, ds.station_name, ds.source, ds.station_type,
            dl.region, dl.municipality, dl.latitude, dl.longitude
        FROM fact_environmental_measures f
        JOIN dim_station ds ON f.station_key = ds.station_key
        JOIN dim_location dl ON f.location_key = dl.location_key
        ORDER BY f.measured_at DESC
        LIMIT :limit
    """)
    try:
        return pd.read_sql(sql, engine, params={"limit": limit})
    except Exception as exc:
        print(f"[Gold] Error query_facts: {exc}")
        return pd.DataFrame()


if __name__ == "__main__":
    load_gold()
