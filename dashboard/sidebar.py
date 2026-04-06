import pandas as pd
import streamlit as st


PAGES = ["Dashboard", "Eksplorasi Data", "Profil Provinsi"]


def build_sidebar(
    dashboard_data: pd.DataFrame,
    rls_data: pd.DataFrame,
) -> tuple[str, list[str], pd.DataFrame, pd.DataFrame]:
    st.sidebar.title("Navigasi")
    page = st.sidebar.radio("Pilih halaman", PAGES)

    st.sidebar.divider()
    st.sidebar.subheader("Filter Provinsi")

    province_options: list[str] = []
    if not dashboard_data.empty and "wilayah" in dashboard_data.columns:
        province_options = sorted(dashboard_data["wilayah"].unique())

    if page == "Profil Provinsi":
        if province_options:
            selected_region = st.sidebar.selectbox(
                "Pilih provinsi",
                options=province_options,
                index=0,
            )
            selected_regions = [selected_region]
        else:
            selected_regions = []
    else:
        selected_regions = st.sidebar.multiselect(
            "Provinsi fokus",
            options=province_options,
            default=province_options,
        )

    year_options: list[int] = []
    if not dashboard_data.empty and "tahun" in dashboard_data.columns:
        year_options = sorted(dashboard_data["tahun"].unique())

    selected_years = st.sidebar.multiselect("Tahun", options=year_options, default=year_options)

    filtered_dashboard = dashboard_data.copy()
    filtered_rls = rls_data.copy()

    if selected_years:
        if not filtered_dashboard.empty and "tahun" in filtered_dashboard.columns:
            filtered_dashboard = filtered_dashboard[filtered_dashboard["tahun"].isin(selected_years)]
        if not filtered_rls.empty and "tahun" in filtered_rls.columns:
            filtered_rls = filtered_rls[filtered_rls["tahun"].isin(selected_years)]

    if selected_regions:
        if not filtered_dashboard.empty and "wilayah" in filtered_dashboard.columns:
            filtered_dashboard = filtered_dashboard[filtered_dashboard["wilayah"].isin(selected_regions)]
        if not filtered_rls.empty and "provinsi" in filtered_rls.columns:
            filtered_rls = filtered_rls[filtered_rls["provinsi"].isin(selected_regions)]

    return page, selected_regions, filtered_dashboard, filtered_rls
