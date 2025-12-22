"""
Streamlit viewer for MinIO-backed feature.parquet and bronze band summaries via DuckDB/httpfs.
"""
import os

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(layout="wide", page_title="Feature viewer (MinIO/DuckDB)")


def _bool_env(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).lower() in ("1", "true", "yes", "on")


def duck_conn():
    endpoint = os.environ["MINIO_ENDPOINT"]
    access = os.environ["MINIO_ACCESS_KEY"]
    secret = os.environ["MINIO_SECRET_KEY"]
    use_ssl = _bool_env("MINIO_USE_SSL", False)
    region = os.getenv("MINIO_REGION", "")
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_url_style='path';")
    con.execute("SET s3_endpoint=$1;", [endpoint])
    con.execute("SET s3_access_key_id=$1;", [access])
    con.execute("SET s3_secret_access_key=$1;", [secret])
    con.execute("SET s3_use_ssl=$1;", ["true" if use_ssl else "false"])
    if region:
        con.execute("SET s3_region=$1;", [region])
    return con


@st.cache_data(show_spinner=False)
def load_feature(location: str, month: str) -> pd.DataFrame:
    obj = f"s3://{os.getenv('MINIO_BUCKET', 'rf-lake')}/gold/survey/{location}/{month}/feature.parquet"
    con = duck_conn()
    return con.execute("SELECT * FROM read_parquet($1)", [obj]).fetch_df()


@st.cache_data(show_spinner=False)
def load_band_summary(band_index: int, mission_type: str, site: str, sensor: str, year: str, month: str) -> pd.DataFrame:
    bucket = os.getenv("MINIO_BUCKET", "rf-lake")
    prefix = f"s3://{bucket}/bronze/mission_type={mission_type}/site={site}/sensor={sensor}/band=*/year={year}/month={month}/**/band{band_index}.parquet"
    con = duck_conn()
    sql = """
    WITH src AS (
      SELECT start_hz, stop_hz, step_hz, power_dbm FROM read_parquet($1)
    )
    SELECT
      idx,
      MIN(val) AS power_min,
      MAX(val) AS power_max,
      AVG(val) AS power_mean,
      ANY_VALUE(start_hz) AS start_hz,
      ANY_VALUE(step_hz) AS step_hz
    FROM src, UNNEST(power_dbm) WITH ORDINALITY AS t(val, idx)
    GROUP BY idx
    ORDER BY idx;
    """
    return con.execute(sql, [prefix]).fetch_df()


st.title("Feature parquet (MinIO)")

col1, col2 = st.columns(2)
with col1:
    location = st.text_input("Location", value="MKAB")
with col2:
    month = st.text_input("Month (YYYY-MM)", value="2025-11")

if st.button("Load feature"):
    try:
        df_feature = load_feature(location, month)
        st.session_state["feature_df"] = df_feature
        st.success(f"Loaded {len(df_feature)} rows from feature.parquet")
    except Exception as exc:  # pragma: no cover - runtime only
        st.error(f"Failed to load feature.parquet: {exc}")

df_feature = st.session_state.get("feature_df")
if df_feature is not None:
    st.dataframe(df_feature, use_container_width=True)

    band_labels = [
        f"{int(row.band_index)} — {row.band_label or ''} ({row.site}/{row.sensor})"
        for _, row in df_feature.iterrows()
    ]
    band_choice = st.selectbox("Select band for bronze summary", band_labels)
    idx = band_labels.index(band_choice) if band_choice in band_labels else 0
    selected = df_feature.iloc[idx]

    if st.button("Load bronze band summary"):
        try:
            df_summary = load_band_summary(
                int(selected.band_index),
                selected.mission_type,
                selected.site,
                selected.sensor,
                selected.year,
                selected.month,
            )
            st.session_state["summary_df"] = df_summary
            st.success(f"Loaded {len(df_summary)} frequency bins for band {int(selected.band_index)}")
        except Exception as exc:
            st.error(f"Failed to load band summary: {exc}")

    df_summary = st.session_state.get("summary_df")
    if df_summary is not None and len(df_summary):
        # Build frequency axis using first row's start/step
        start_hz = float(df_summary.start_hz.iloc[0])
        step_hz = float(df_summary.step_hz.iloc[0])
        df_summary["freq_mhz"] = (start_hz + (df_summary.idx - 1) * step_hz) / 1e6
        fig = px.line(df_summary, x="freq_mhz", y="power_mean", title="Mean power (dBm)")
        fig.add_scatter(x=df_summary["freq_mhz"], y=df_summary["power_min"], name="Min", line=dict(color="orange"))
        fig.add_scatter(x=df_summary["freq_mhz"], y=df_summary["power_max"], name="Max", line=dict(color="red"))
        fig.update_layout(xaxis_title="Frequency (MHz)", yaxis_title="dBm")
        st.plotly_chart(fig, use_container_width=True)
