import os
from minio import Minio


def _bool_env(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).lower() in ("1", "true", "yes", "on")


def _required(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Environment variable {name} is required for MinIO access.")
    return val


def get_minio_client() -> Minio:
    endpoint = _required("MINIO_ENDPOINT")
    access_key = _required("MINIO_ACCESS_KEY")
    secret_key = _required("MINIO_SECRET_KEY")
    secure = _bool_env("MINIO_USE_SSL", False)
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)


def bucket_name() -> str:
    return os.getenv("MINIO_BUCKET", "rf-lake")

