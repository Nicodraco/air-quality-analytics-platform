"""
Clustering de estaciones de monitoreo por perfil de contaminación.

Agrupa ubicaciones según sus patrones de contaminantes
para identificar zonas con características similares.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import joblib


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


def ensure_dirs():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)


def load_data():
    """Carga datos preprocesados."""
    filepath = PROCESSED_DIR / "air_quality_merged.parquet"
    if filepath.exists():
        return pd.read_parquet(filepath)
    csv_path = PROCESSED_DIR / "air_quality_merged.csv"
    if csv_path.exists():
        return pd.read_csv(csv_path, parse_dates=["timestamp"])
    return None


def create_station_profiles(df):
    """
    Crea perfiles promedio por ubicación/estación.

    Returns: DataFrame con features aggregated por ubicación
    """
    if "location" not in df.columns:
        print("[Cluster] No se encontró columna 'location'")
        return None

    pollutant_cols = [c for c in df.columns if c in [
        "pm2_5", "pm10", "no2", "o3", "so2", "co", "european_aqi"
    ]]

    if not pollutant_cols:
        print("[Cluster] No se encontraron columnas de contaminantes")
        return None

    profiles = (
        df.groupby("location")
        .agg(
            **{
                f"{col}_mean": (col, "mean")
                if col in df.columns
                else ("location", "first")
                for col in pollutant_cols
            }
        )
        .reset_index()
    )

    for col in pollutant_cols:
        profiles[f"{col}_max"] = df.groupby("location")[col].max().values
        profiles[f"{col}_std"] = df.groupby("location")[col].std().values

    lat_lon = df.groupby("location")[["latitude", "longitude"]].mean().reset_index()
    profiles = profiles.merge(lat_lon, on="location", how="left")

    return profiles


def cluster_stations(profiles, n_clusters=4):
    """
    Agrupa estaciones por perfil de contaminación usando K-Means.

    Args:
        profiles: DataFrame con perfiles por estación
        n_clusters: Número de clusters

    Returns: (modelo, profiles con cluster asignado)
    """
    exclude = ["location", "latitude", "longitude"]
    feature_cols = [c for c in profiles.columns if c not in exclude]

    feature_cols = [c for c in feature_cols if profiles[c].dtype in [
        np.float64, np.int64, np.float32
    ]]

    X = profiles[feature_cols].fillna(profiles[feature_cols].mean())

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    profiles["cluster"] = model.fit_predict(X_scaled)

    pca = PCA(n_components=2, random_state=42)
    coords = pca.fit_transform(X_scaled)
    profiles["pca_x"] = coords[:, 0]
    profiles["pca_y"] = coords[:, 1]

    cluster_labels = {}
    for c in range(n_clusters):
        mask = profiles["cluster"] == c
        cluster_profiles = profiles[mask]
        top_pollutants = (
            cluster_profiles[[c for c in feature_cols if "mean" in c]]
            .mean()
            .sort_values(ascending=False)
            .index[:2]
            .tolist()
        )
        labels = [p.replace("_mean", "") for p in top_pollutants]
        cluster_labels[c] = f"Cluster {c} ({', '.join(labels)})"

    profiles["cluster_label"] = profiles["cluster"].map(cluster_labels)
    profiles["pca_variance_ratio"] = pca.explained_variance_ratio_.sum()

    inertia = model.inertia_
    print(f"[Cluster] {n_clusters} clusters generados (inercia: {inertia:.2f})")
    print(f"[Cluster] Variance explained by 2 PCA components: {pca.explained_variance_ratio_.sum():.2%}")

    for c in range(n_clusters):
        count = (profiles["cluster"] == c).sum()
        print(f"  {cluster_labels[c]}: {count} estaciones")

    return model, profiles


def save_cluster_model(model, profiles):
    """Guarda modelo de clustering."""
    ensure_dirs()
    model_path = MODELS_DIR / "station_clusters.joblib"
    joblib.dump(model, model_path)
    csv_path = MODELS_DIR / "station_clusters.csv"
    profiles.to_csv(csv_path, index=False)
    print(f"[Cluster] Modelo guardado: {model_path}")
    return model_path


def run_clustering():
    """Ejecuta pipeline de clustering."""
    print("=" * 60)
    print("CLUSTERING - Perfiles de Contaminación por Estación")
    print("=" * 60)

    df = load_data()
    if df is None:
        print("[Cluster] No hay datos disponibles")
        return None, None

    print(f"[Cluster] Datos cargados: {len(df)} registros")

    profiles = create_station_profiles(df)
    if profiles is None or len(profiles) < 2:
        print("[Cluster] No hay suficientes estaciones para clustering")
        return None, None

    n_clusters = min(4, len(profiles) // 2)
    n_clusters = max(2, n_clusters)

    model, clustered = cluster_stations(profiles, n_clusters=n_clusters)
    save_cluster_model(model, clustered)

    return model, clustered


if __name__ == "__main__":
    run_clustering()
