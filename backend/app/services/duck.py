import os
import duckdb


def _bool_env(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).lower() in ("1", "true", "yes", "on")


def _required(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Environment variable {name} is required for MinIO/DuckDB access.")
    return val


def get_connection() -> duckdb.DuckDBPyConnection:
    """
    Return a fresh DuckDB connection configured to read S3/MinIO via httpfs.
    Keep per-request connections to avoid cross-thread reuse issues.
    """
    endpoint = _required("MINIO_ENDPOINT")
    access_key = _required("MINIO_ACCESS_KEY")
    secret_key = _required("MINIO_SECRET_KEY")
    use_ssl = _bool_env("MINIO_USE_SSL", False)
    region = os.getenv("MINIO_REGION", "")

    con = duckdb.connect()
    # Ensure httpfs is available for S3/MinIO access.
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_url_style='path';")
    con.execute("SET s3_endpoint=$1;", [endpoint])
    con.execute("SET s3_access_key_id=$1;", [access_key])
    con.execute("SET s3_secret_access_key=$1;", [secret_key])
    con.execute("SET s3_use_ssl=$1;", ["true" if use_ssl else "false"])
    if region:
        con.execute("SET s3_region=$1;", [region])
    return con


def bucket_name() -> str:
    return os.getenv("MINIO_BUCKET", "rf-lake")

