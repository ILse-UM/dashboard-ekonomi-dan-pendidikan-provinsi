import pandas as pd
import streamlit as st
import re

from dashboard.charts import format_miliar, render_connected_scatter
# from dashboard.config import GEMINI_API_KEY


def _resolve_gemini_api_key(input_key: str) -> str:
    if input_key.strip():
        return input_key.strip()

    secrets_key = st.secrets.get("GEMINI_API_KEY", "")
    if isinstance(secrets_key, str) and secrets_key.strip():
        return secrets_key.strip()

    # if isinstance(GEMINI_API_KEY, str) and GEMINI_API_KEY.strip():
    #     return GEMINI_API_KEY.strip()

    return ""


def _build_scatter_context(data: pd.DataFrame) -> str:
    if data.empty:
        return "Data kosong."

    cleaned = data[["wilayah", "tahun", "rata_lama_sekolah", "pdrb_berlaku_miliar"]].dropna()
    if cleaned.empty:
        return "Data scatter kosong setelah pembersihan."

    per_region = (
        cleaned.sort_values(["wilayah", "tahun"])
        .groupby("wilayah", as_index=False)
        .agg(
            tahun_awal=("tahun", "min"),
            tahun_akhir=("tahun", "max"),
            rls_awal=("rata_lama_sekolah", "first"),
            rls_akhir=("rata_lama_sekolah", "last"),
            pdrb_awal=("pdrb_berlaku_miliar", "first"),
            pdrb_akhir=("pdrb_berlaku_miliar", "last"),
        )
    )
    per_region["delta_rls"] = per_region["rls_akhir"] - per_region["rls_awal"]
    per_region["delta_pdrb"] = per_region["pdrb_akhir"] - per_region["pdrb_awal"]

    latest_year = int(cleaned["tahun"].max())
    latest_slice = cleaned[cleaned["tahun"] == latest_year]
    top_latest = latest_slice.sort_values("pdrb_berlaku_miliar", ascending=False).head(8)

    summary_block = per_region[["wilayah", "tahun_awal", "tahun_akhir", "delta_rls", "delta_pdrb"]].to_csv(index=False)
    latest_block = top_latest[["wilayah", "rata_lama_sekolah", "pdrb_berlaku_miliar"]].to_csv(index=False)

    return (
        f"Jumlah baris: {len(cleaned)}\n"
        f"Jumlah provinsi: {cleaned['wilayah'].nunique()}\n"
        f"Rentang tahun: {int(cleaned['tahun'].min())} - {int(cleaned['tahun'].max())}\n"
        "\nRingkasan perubahan per provinsi (CSV):\n"
        f"{summary_block}\n"
        f"Top PDRB di tahun {latest_year} (CSV):\n"
        f"{latest_block}"
    )


def _generate_gemini_insight(data: pd.DataFrame, api_key: str) -> tuple[str | None, str | None]:
    if not api_key:
        return None, "API key Gemini belum diisi."

    prompt = (
        "Kamu adalah analis data ekonomi-pendidikan Indonesia. "
        "Berikan insight ringkas dari scatter plot hubungan RLS dan PDRB. "
        "Format jawaban: \n"
        "1) 3 insight utama berbasis data,\n"
        "2) 2 anomali/hal yang perlu dicek,\n"
        "3) 2 rekomendasi aksi kebijakan atau analisis lanjutan.\n"
        "Gunakan bahasa Indonesia yang jelas dan tidak bertele-tele.\n\n"
        "Data ringkasan:\n"
        f"{_build_scatter_context(data)}"
    )

    def _friendly_gemini_error(exc: Exception) -> str:
        raw = str(exc)
        lower = raw.lower()
        if "resource_exhausted" in lower or "quota exceeded" in lower or "429" in lower:
            retry_match = re.search(r"retry in ([0-9.]+)s", raw, flags=re.IGNORECASE)
            retry_note = ""
            if retry_match:
                retry_note = f" Coba ulang sekitar {retry_match.group(1)} detik lagi."
            return (
                "Quota Gemini kamu sedang habis / belum aktif (429 RESOURCE_EXHAUSTED). "
                "Cek billing dan quota project di Google AI Studio / Google Cloud."
                f"{retry_note}"
            )
        if "api key" in lower and ("invalid" in lower or "not valid" in lower):
            return "API key Gemini tidak valid. Cek lagi nilai `GEMINI_API_KEY`."
        return f"Gagal memanggil Gemini: {raw}"

    # Coba SDK terbaru dulu, lalu fallback model jika diperlukan.
    try:
        from google import genai  # type: ignore

        client = genai.Client(api_key=api_key)
        last_error: Exception | None = None
        for model_name in ("gemini-3-flash", "gemini-3-flash-lite", "gemini-2.5-flash"):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                return (response.text or "Tidak ada respons dari Gemini."), None
            except Exception as exc:
                last_error = exc
                continue
        if last_error is not None:
            return None, _friendly_gemini_error(last_error)
        return None, "Gagal memanggil Gemini: tidak ada model yang tersedia."
    except ModuleNotFoundError:
        try:
            import google.generativeai as genai  # type: ignore

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            text = getattr(response, "text", None)
            return (text or "Tidak ada respons dari Gemini."), None
        except ModuleNotFoundError:
            return None, "Library Gemini belum terpasang. Jalankan: pip install google-genai"
        except Exception as exc:
            return None, _friendly_gemini_error(exc)
    except Exception as exc:
        return None, _friendly_gemini_error(exc)


def dashboard_page(data: pd.DataFrame, selected_regions: list[str]) -> None:
    st.title("Dashboard Ekonomi dan Pendidikan Provinsi")
    st.caption("Dashboard visualisasi data ini berfungsi untuk membantu pengguna memahami hubungan antara PDRB (Produk Domestik Regional Bruto) dan rata-rata lama sekolah antar provinsi secara interaktif, ")
    st.caption("untuk memudahkan analisis tren, perbandingan, dan pengambilan keputusan berbasis data.")

    st.caption(f"Baris data provinsi aktif: {len(data)}")

    latest_year = int(data["tahun"].max())
    latest_data = data[data["tahun"] == latest_year]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Jumlah Provinsi", f"{latest_data['wilayah'].nunique()}")
    col2.metric("Tahun Terbaru", f"{latest_year}")
    col3.metric("RLS Provinsi Rata-rata", f"{latest_data['rata_lama_sekolah'].mean():.2f} tahun")
    col4.metric("Total PDRB", format_miliar(latest_data["pdrb_berlaku_miliar"].sum()))

    st.subheader("Scatter Plot Terhubung per Tahun")
    st.write("Setiap titik adalah satu provinsi pada satu tahun, lalu dihubungkan menurut urutan tahun.")
    render_connected_scatter(data)

    st.subheader("Insight AI (Gemini)")
    st.caption("Klik tombol untuk generate insight otomatis dari data scatter plot yang sedang aktif.")
    button_col, _ = st.columns([1, 7])
    if button_col.button("Generate"):
        resolved_api_key = _resolve_gemini_api_key(st.secrets.get("GEMINI_API_KEY", ""))
        if not resolved_api_key:
            st.warning(
                "API key belum ada. Set `GEMINI_API_KEY` di `.streamlit/secrets.toml` atau `dashboard/config.py`."
            )
        else:
            with st.spinner("Gemini sedang menganalisis pola scatter plot..."):
                insight_text, error_text = _generate_gemini_insight(data, resolved_api_key)

            if error_text:
                st.error(error_text)
            else:
                st.success("Insight AI berhasil dibuat")
                with st.container(border=True):
                    st.markdown("**Hasil Insight AI**")
                    st.markdown(insight_text)

    left_col, right_col = st.columns([1.2, 1])

    with left_col:
        st.subheader("Insight Cepat")
        if len(selected_regions) == 1:
            selected_region = selected_regions[0]
            region_slice = data[data["wilayah"] == selected_region].sort_values("tahun")
            if not region_slice.empty:
                first_row = region_slice.iloc[0]
                last_row = region_slice.iloc[-1]
                delta_school = last_row["rata_lama_sekolah"] - first_row["rata_lama_sekolah"]
                delta_pdrb = last_row["pdrb_berlaku_miliar"] - first_row["pdrb_berlaku_miliar"]
                st.info(
                    f"Provinsi `{selected_region}` berubah dari {first_row['tahun']} ke {last_row['tahun']} "
                    f"dengan kenaikan RLS {delta_school:.2f} tahun dan PDRB {format_miliar(delta_pdrb)}."
                )
        else:
            st.info("Pilih tepat satu provinsi di sidebar kalau mau fokus ke narasi perubahan satu wilayah.")

        trend_data = data.groupby("tahun", as_index=False)[["pdrb_berlaku_miliar", "rata_lama_sekolah"]].mean()
        st.line_chart(trend_data.set_index("tahun")[["pdrb_berlaku_miliar", "rata_lama_sekolah"]])

    with right_col:
        st.subheader(f"Peringkat Provinsi {latest_year}")
        ranking = latest_data.sort_values("pdrb_berlaku_miliar", ascending=False)[
            ["wilayah", "rata_lama_sekolah", "pdrb_berlaku_miliar"]
        ]
        st.dataframe(
            ranking,
            use_container_width=True,
            hide_index=True,
            column_config={
                "rata_lama_sekolah": st.column_config.NumberColumn("RLS", format="%.2f tahun"),
                "pdrb_berlaku_miliar": st.column_config.NumberColumn("PDRB", format="%.2f"),
            },
        )


def data_table_page(dashboard_data: pd.DataFrame, rls_data: pd.DataFrame) -> None:
    st.title("Eksplorasi Data")
    # st.caption("Grafik tetap provinsi, tapi detail kabupaten/kota untuk lama sekolah ditampilkan di halaman tabel.")
    st.caption(f"Baris merge provinsi: {len(dashboard_data)} | Baris RLS terfilter: {len(rls_data)}")

    tab1, tab2 = st.tabs(["Tabel Merge Provinsi", "Tabel RLS Kabupaten/Kota"])

    with tab1:
        prov_df = dashboard_data.sort_values(["tahun", "wilayah"]).reset_index(drop=True)
        prov_df_display = prov_df.copy()
        prov_df_display["wilayah_provinsi"] = prov_df_display["wilayah"]
        prov_df_display["pertumbuhan_pdrb"] = prov_df_display["pertumbuhan_pdrb_pct"].apply(
            lambda value: f"{value:.2f}%" if pd.notna(value) else "Butuh minimal 2 tahun data"
        )
        if prov_df_display["pertumbuhan_pdrb_pct"].notna().sum() == 0:
            st.info(
                "Kolom pertumbuhan PDRB masih kosong secara perhitungan karena data PDRB yang aktif baru 1 tahun. "
                "Minimal perlu 2 tahun untuk menghitung pertumbuhan."
            )
        prov_df_table = prov_df_display.drop(columns=["provinsi", "wilayah", "pertumbuhan_pdrb_pct"])
        ordered_columns = [
            "wilayah_provinsi",
            "kode_wilayah",
            "tahun",
            "pdrb_berlaku_miliar",
            "level_wilayah",
            "rata_lama_sekolah",
            "pertumbuhan_pdrb",
        ]
        prov_df_table = prov_df_table[[column for column in ordered_columns if column in prov_df_table.columns]]
        st.dataframe(
            prov_df_table,
            use_container_width=True,
            hide_index=True,
            column_config={
                "wilayah_provinsi": "Wilayah",
                "pdrb_berlaku_miliar": st.column_config.NumberColumn("PDRB ADHB (miliar Rp)", format="%.2f"),
                "rata_lama_sekolah": st.column_config.NumberColumn("RLS", format="%.2f"),
                "pertumbuhan_pdrb": st.column_config.TextColumn("Pertumbuhan PDRB"),
            },
        )
        st.download_button(
            "Unduh CSV Merge Provinsi",
            data=prov_df_table.to_csv(index=False).encode("utf-8"),
            file_name="merge_provinsi_pdrb_rls.csv",
            mime="text/csv",
        )

    with tab2:
        detail_df = rls_data[rls_data["level_wilayah"] == "Kabupaten/Kota"].copy()
        national_df = rls_data[rls_data["level_wilayah"] == "Nasional"].copy()
        detail_df = detail_df.sort_values(["tahun", "provinsi", "wilayah"]).reset_index(drop=True)
        if not national_df.empty:
            latest_national = national_df.sort_values("tahun").iloc[-1]
            metric_col1, metric_col2, metric_col3 = st.columns(3)
            metric_col1.metric("Cakupan Nasional", "Indonesia")
            metric_col2.metric(
                "RLS Nasional Terbaru",
                f"{latest_national['rata_lama_sekolah']:.2f} tahun",
            )
            metric_col3.metric("Tahun Nasional Terbaru", f"{int(latest_national['tahun'])}")
            st.caption("Baris agregat nasional tidak ditampilkan di tabel detail kabupaten/kota.")
        st.dataframe(
            detail_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "rata_lama_sekolah": st.column_config.NumberColumn("RLS", format="%.2f tahun"),
            },
        )
        st.download_button(
            "Unduh CSV RLS Kabupaten/Kota",
            data=detail_df.to_csv(index=False).encode("utf-8"),
            file_name="rls_kabupaten_kota.csv",
            mime="text/csv",
        )


def profile_page(data: pd.DataFrame, selected_regions: list[str]) -> None:
    st.title("Profil Provinsi")
    # st.caption("Halaman profil juga dibatasi ke provinsi agar konsisten dengan grafik utama.")
    # st.caption(f"Baris data profil aktif: {len(data)}")

    region = selected_regions[0] if selected_regions else data["wilayah"].iloc[0]
    region_data = data[data["wilayah"] == region].sort_values("tahun")
    latest = region_data.iloc[-1]
    earliest = region_data.iloc[0]

    col1, col2, col3 = st.columns(3)
    col1.metric("Provinsi", latest["wilayah"])
    col2.metric("RLS Terbaru", f"{latest['rata_lama_sekolah']:.2f} tahun")
    col3.metric("PDRB Terbaru", format_miliar(latest["pdrb_berlaku_miliar"]))

    render_connected_scatter(region_data)

    st.write(
        f"Pada `{region}`, nilai RLS berubah dari {earliest['rata_lama_sekolah']:.2f} menjadi "
        f"{latest['rata_lama_sekolah']:.2f}, sedangkan PDRB berubah dari "
        f"{format_miliar(earliest['pdrb_berlaku_miliar'])} menjadi {format_miliar(latest['pdrb_berlaku_miliar'])}."
    )

    st.dataframe(region_data, use_container_width=True, hide_index=True)

    st.caption("Keterangan Data:")
    st.caption("`...` : Data tidak tersedia")
    st.caption("`-` : Tidak ada atau nol")
    st.caption("`NA` : Data tidak dapat ditampilkan")
    st.caption("`e` : Angka estimasi")
    st.caption("`r` : Angka diperbaiki")
    st.caption("`~0` : Data dapat diabaikan")
    st.caption("`*` : Angka sementara")
    st.caption("`**` : Angka sangat sementara")
    st.caption("`***` : Angka sangat sangat sementara")
    st.caption("`a` : 25% < RSE <= 50%")
    st.caption("`b` : RSE < 50%")
    st.caption("`c` : Penjumlahan tidak sama dengan wilayah diatasnya")


def build_about_dialog_content() -> str:
    return """

**Hal-hal yang perlu diperhatikan :**

1. `Cache file 6 jam`
   Respons endpoint disimpan ke folder cache lokal server supaya tidak memukul API terus-menerus.
2. `Grafik level provinsi`
   Scatter plot hanya memakai PDRB provinsi dan RLS provinsi.
3. `Detail kabupaten/kota di tabel`
   RLS kabupaten/kota tetap tersedia untuk eksplorasi tabel.

**Referensi Sumber Data dari BPS**

- [Tabel BPS untuk PDRB Atas Dasar Harga Berlaku per Provinsi](https://www.bps.go.id/id/statistics-table/3/WkdVMWRYVnBkMnBvVEhKSVkyWXhNblZtTjJSbmR6MDkjMw==/produk-domestik-regional-bruto-atas-dasar-harga-berlaku-menurut-provinsi--miliar-rupiah-2022.html?year=2025)
- [Tabel BPS untuk Rata-rata Lama Sekolah Metode Baru](https://www.bps.go.id/id/statistics-table/2/NDE1IzI=/-metode-baru-rata-rata-lama-sekolah.html)
"""
