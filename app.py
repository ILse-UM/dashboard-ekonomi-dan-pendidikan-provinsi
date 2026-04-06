import streamlit as st

from dashboard.sidebar import build_sidebar
from dashboard.datasets import load_datasets
from dashboard.pages import build_about_dialog_content, dashboard_page, data_table_page, profile_page


st.set_page_config(
    page_title="Dashboard Ekonomi & Pendidikan",
    page_icon=":bar_chart:",
    layout="wide",
    menu_items={
        "About": build_about_dialog_content(),
    },
)


def main() -> None:
    dashboard_data, rls_data = load_datasets()
    page, selected_regions, filtered_dashboard, filtered_rls = build_sidebar(dashboard_data, rls_data)

    if filtered_dashboard.empty:
        st.warning("Data provinsi untuk filter ini kosong, jadi halaman analitik belum bisa ditampilkan.")
        st.caption("Coba pilih provinsi atau tahun lain. Informasi dataset sekarang ada di menu kanan atas > About.")
        return

    if page == "Dashboard":
        dashboard_page(filtered_dashboard, selected_regions)
    elif page == "Eksplorasi Data":
        data_table_page(filtered_dashboard, filtered_rls)
    else:
        profile_page(filtered_dashboard, selected_regions)


if __name__ == "__main__":
    main()
