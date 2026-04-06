import os

import pandas as pd
import streamlit as st
from dashboard.bps_client import load_remote_pdrb_data, load_remote_rls_data
from dashboard.sample_data import build_sample_pdrb_data, build_sample_rls_data


def get_bps_api_key() -> str | None:
    try:
        secret_key = st.secrets.get("bps_api_key")
    except Exception:
        secret_key = None
    return secret_key or os.getenv("BPS_API_KEY")


def prepare_dashboard_dataset(
    pdrb_data: pd.DataFrame,
    rls_data: pd.DataFrame,
) -> pd.DataFrame:
    rls_provinsi = rls_data[rls_data["level_wilayah"] == "Provinsi"].copy()
    merged = pdrb_data.merge(
        rls_provinsi[["kode_wilayah", "tahun", "rata_lama_sekolah"]],
        on=["kode_wilayah", "tahun"],
        how="inner",
    )
    merged["pertumbuhan_pdrb_pct"] = (
        merged.sort_values(["wilayah", "tahun"])
        .groupby("wilayah")["pdrb_berlaku_miliar"]
        .pct_change()
        .mul(100)
    )
    return merged


def log_load_notices(notices: list[str]) -> None:
    for notice in notices:
        print(f"[data-load] {notice}")


def load_datasets() -> tuple[pd.DataFrame, pd.DataFrame]:
    notices: list[str] = []
    api_key = get_bps_api_key()

    pdrb_data = pd.DataFrame()
    rls_data = pd.DataFrame()

    if api_key:
        pdrb_data, pdrb_notices = load_remote_pdrb_data(api_key)
        rls_data, rls_notices = load_remote_rls_data(api_key)
        notices.extend(pdrb_notices)
        notices.extend(rls_notices)
    else:
        notices.append("API key BPS belum ditemukan, jadi app memakai data contoh lokal.")

    if pdrb_data.empty:
        pdrb_data = build_sample_pdrb_data()
        notices.append("Dataset PDRB fallback ke contoh lokal.")

    if rls_data.empty:
        rls_data = build_sample_rls_data()
        notices.append("Dataset RLS fallback ke contoh lokal.")

    log_load_notices(notices)
    dashboard_data = prepare_dashboard_dataset(pdrb_data, rls_data)
    return dashboard_data, rls_data
