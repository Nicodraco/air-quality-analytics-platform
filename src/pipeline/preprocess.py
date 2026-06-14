"""
Preprocesamiento y transformación de datos de calidad del aire.

Unifica los datos de BSC/UPC, Open-Meteo y OpenAQ en un formato común
listo para análisis, ML y visualización.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
EXTERNAL_DIR = DATA_DIR / "external"


def ensure_dirs():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def load_bsc_data():
    """Carga y preprocesa datos de BSC/UPC."""
    filepath = EXTERNAL_DIR / "Barcelona_NO2_2019_2024_census_daily.csv"
    if not filepath.exists():
        print("[Preprocess] No hay datos BSC. Ejecuta ingest_bsc.py primero.")
        return None

    df = pd.read_csv(filepath, parse_dates=["date"])
    df.rename(
        columns={
            "date": "timestamp",
            "no2_concentration_ugm3": "no2",
            "no2_uncertainty_ugm3": "no2_uncertainty",
        },
        inplace=True,
    )
    df["source"] = "bsc_upc"

    df = df.sort_values(["census_tract_id", "timestamp"])
    print(f"[Preprocess] BSC: {len(df)} registros ({df['timestamp'].min()} a {df['timestamp'].max()})")
    return df


def load_openmeteo_data():
    """Carga y preprocesa datos de Open-Meteo."""
    files = sorted(RAW_DIR.glob("openmeteo_aq_*.csv"))
    if not files:
        print("[Preprocess] No hay datos Open-Meteo. Ejecuta ingest_openmeteo.py primero.")
        return None

    dfs = []
    for f in files:
        df = pd.read_csv(f, parse_dates=["timestamp"])
        dfs.append(df)

    df = pd.concat(dfs, ignore_index=True).drop_duplicates(
        subset=["timestamp", "location"]
    )
    df["source"] = "openmeteo"
    print(f"[Preprocess] Open-Meteo: {len(df)} registros")
    return df


def load_openaq_data():
    """Carga y preprocesa datos de OpenAQ."""
    files = sorted(RAW_DIR.glob("openaq_spain_*.csv"))
    if not files:
        print("[Preprocess] No hay datos OpenAQ. Ejecuta ingest_openaq.py primero.")
        return None

    dfs = []
    for f in files:
        df = pd.read_csv(f, parse_dates=["timestamp"])
        dfs.append(df)

    df = pd.concat(dfs, ignore_index=True).drop_duplicates()
    df["source"] = "openaq"
    print(f"[Preprocess] OpenAQ: {len(df)} registros")
    return df


def pivot_openaq_data(df):
    """
    Convierte OpenAQ de formato largo (un contaminante por fila)
    a formato ancho (columnas por contaminante).
    """
    if df is None or len(df) == 0:
        return None

    if "parameter" not in df.columns:
        return df

    pivot = df.pivot_table(
        index=["timestamp", "location_name", "latitude", "longitude", "source"],
        columns="parameter",
        values="value",
        aggfunc="first",
    ).reset_index()

    pivot.columns.name = None

    param_rename = {
        "PM2.5": "pm2_5",
        "PM10": "pm10",
        "NO2": "no2",
        "O3": "o3",
        "CO": "co",
        "SO2": "so2",
    }
    pivot.rename(columns=param_rename, inplace=True)
    return pivot


def merge_data_sources():
    """
    Unifica todas las fuentes de datos en un solo DataFrame.
    """
    bsc_df = load_bsc_data()
    om_df = load_openmeteo_data()
    oaq_df = load_openaq_data()

    oaq_df = pivot_openaq_data(oaq_df)

    all_sources = []
    if bsc_df is not None:
        all_sources.append(bsc_df)
    if om_df is not None:
        all_sources.append(om_df)

    if oaq_df is not None:
        oaq_df.rename(
            columns={"location_name": "location", "latitude": "lat", "longitude": "lon"},
            inplace=True,
        )
        if "lat" in oaq_df.columns:
            oaq_df["latitude"] = oaq_df["lat"]
            oaq_df["longitude"] = oaq_df["lon"]
        all_sources.append(oaq_df)

    if not all_sources:
        print("[Preprocess] No hay datos de ninguna fuente")
        return None

    merged = pd.concat(all_sources, ignore_index=True, sort=False)
    return merged


def clean_data(df):
    """
    Limpieza general de datos:
    - Eliminar duplicados exactos
    - Manejar valores faltantes
    - Tipos de datos correctos
    """
    if df is None:
        return None

    df = df.drop_duplicates()
    df = df.sort_values("timestamp")

    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["year"] = df["timestamp"].dt.year
    df["month"] = df["timestamp"].dt.month
    df["day"] = df["timestamp"].dt.day
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["hour"] = df["timestamp"].dt.hour

    return df


def create_daily_summary(df):
    """
    Crea resúmenes diarios a partir de datos horarios.
    """
    if df is None or len(df) == 0:
        return None

    pollutant_cols = ["pm2_5", "pm10", "no2", "o3", "so2", "co", "european_aqi"]

    available = [c for c in pollutant_cols if c in df.columns]

    if not available:
        return df

    daily = (
        df.groupby([df["timestamp"].dt.date, "location"])
        .agg(
            **{
                f"{col}_mean": (col, "mean")
                if col in df.columns
                else (df.columns[0], "first")
                for col in available
            }
        )
        .reset_index()
    )

    for col in available:
        daily[f"{col}_max"] = df.groupby(
            [df["timestamp"].dt.date, "location"]
        )[col].max().values

    daily.rename(columns={"timestamp": "date"}, inplace=True)
    return daily


def run_pipeline():
    """Ejecuta el pipeline completo de preprocesamiento."""
    ensure_dirs()
    print("=" * 60)
    print("PIPELINE DE PREPROCESAMIENTO - Calidad del Aire")
    print("=" * 60)

    df = merge_data_sources()
    df = clean_data(df)

    if df is not None and len(df) > 0:
        output_path = PROCESSED_DIR / "air_quality_merged.parquet"
        df.to_parquet(output_path, index=False)
        print(f"\n[Preprocess] Datos unificados guardados: {output_path}")
        print(f"[Preprocess] Total registros: {len(df)}")
        print(f"[Preprocess] Fuentes: {df['source'].unique()}")

        csv_path = PROCESSED_DIR / "air_quality_merged.csv"
        df.to_csv(csv_path, index=False)
        print(f"[Preprocess] CSV guardado: {csv_path}")

        daily = create_daily_summary(df)
        if daily is not None:
            daily_path = PROCESSED_DIR / "air_quality_daily.csv"
            daily.to_csv(daily_path, index=False)
            print(f"[Preprocess] Resumen diario: {daily_path}")
    else:
        print("[Preprocess] No se generaron datos")

    return df


if __name__ == "__main__":
    df = run_pipeline()
    if df is not None:
        print(f"\nColumnas: {list(df.columns)}")
        print(f"\nPrimeras filas:\n{df.head()}")
