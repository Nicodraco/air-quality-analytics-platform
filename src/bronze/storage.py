"""
Capa Bronze: almacenamiento de datos crudos en MinIO (JSON).

Estructura: bronze/{source}/yyyy/mm/dd/{timestamp}.json
Fallback local: data/bronze/{source}/yyyy/mm/dd/
"""

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from src.config import (
    BRONZE_LOCAL_DIR,
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
    USE_LOCAL_BRONZE_FALLBACK,
    ensure_dirs,
)


def _object_key(source: str, timestamp: datetime | None = None) -> str:
    ts = timestamp or datetime.now(timezone.utc)
    return (
        f"bronze/{source}/{ts.year:04d}/{ts.month:02d}/{ts.day:02d}/"
        f"{ts.strftime('%Y%m%d_%H%M%S')}.json"
    )


def _local_path(object_key: str) -> Path:
    return BRONZE_LOCAL_DIR / object_key


def _get_minio_client():
    try:
        from minio import Minio

        return Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE,
        )
    except Exception as exc:
        print(f"[Bronze] MinIO no disponible: {exc}")
        return None


def _ensure_bucket(client) -> bool:
    try:
        if not client.bucket_exists(MINIO_BUCKET):
            client.make_bucket(MINIO_BUCKET)
            print(f"[Bronze] Bucket creado: {MINIO_BUCKET}")
        return True
    except Exception as exc:
        print(f"[Bronze] Error bucket: {exc}")
        return False


def save_bronze(source: str, data: dict[str, Any]) -> str:
    """
    Guarda payload JSON en Bronze (MinIO + fallback local).

    Returns:
        object_key del archivo guardado
    """
    ensure_dirs()
    ts = datetime.now(timezone.utc)
    key = _object_key(source, ts)
    body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")

    saved_to = []

    client = _get_minio_client()
    if client and _ensure_bucket(client):
        try:
            client.put_object(
                MINIO_BUCKET,
                key,
                BytesIO(body),
                length=len(body),
                content_type="application/json",
            )
            saved_to.append(f"minio://{MINIO_BUCKET}/{key}")
            print(f"[Bronze] MinIO: {key}")
        except Exception as exc:
            print(f"[Bronze] Error MinIO: {exc}")

    if USE_LOCAL_BRONZE_FALLBACK:
        local = _local_path(key)
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(body)
        saved_to.append(str(local))
        print(f"[Bronze] Local: {local}")

    if not saved_to:
        raise RuntimeError("No se pudo guardar en Bronze")

    return key


def load_latest_bronze(source: str) -> dict[str, Any] | None:
    """Carga el JSON Bronze más reciente de una fuente."""
    pattern = f"bronze/{source}/*/*/*/*.json"
    local_files = sorted(BRONZE_LOCAL_DIR.glob(pattern))
    if local_files:
        latest = local_files[-1]
        print(f"[Bronze] Cargando local: {latest}")
        return json.loads(latest.read_text(encoding="utf-8"))

    client = _get_minio_client()
    if not client:
        return None

    try:
        objects = list(
            client.list_objects(MINIO_BUCKET, prefix=f"bronze/{source}/", recursive=True)
        )
        if not objects:
            return None
        latest_obj = sorted(objects, key=lambda o: o.last_modified)[-1]
        response = client.get_object(MINIO_BUCKET, latest_obj.object_name)
        data = json.loads(response.read().decode("utf-8"))
        response.close()
        response.release_conn()
        return data
    except Exception as exc:
        print(f"[Bronze] Error cargando MinIO: {exc}")
        return None
