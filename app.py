import json
import os
import re
import time
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Dashboard Ekonomi & Pendidikan",
    page_icon=":bar_chart:",
    layout="wide",
)

# Konfigurasi API dan cache
#TTL cache selama 6 jam
CACHE_TTL_SECONDS = 6 * 60 * 60
CACHE_DIR = Path(".cache/bps")
BPS_PDRB_BASE_URL = "https://webapi.bps.go.id/v1/api/interoperabilitas/datasource/simdasi"
BPS_RLS_BASE_URL = "https://webapi.bps.go.id/v1/api/list/model/data/lang/ind/domain/0000"

PDRB_CONFIGS = [
    {
        "tahun": tahun,
        "id_tabel": "ZGU1dXVpd2poTHJIY2YxMnVmN2Rndz09",
        "wilayah": "0000000",
        "level_wilayah": "Provinsi",
    }
    for tahun in range(2025, 2013, -1)
]

RLS_CONFIGS = [
    {
        "tahun": tahun,
        "var_id": 415,
        "th_code": tahun - 1900,
    }
    for tahun in range(2025, 2009, -1)
]


def get_bps_api_key() -> str | None:
    try:
        secret_key = st.secrets.get("bps_api_key")
    except Exception:
        secret_key = None
    return secret_key or os.getenv("BPS_API_KEY")


def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def clean_text(value: str | None) -> str:
    if value is None:
        return ""
    text = re.sub(r"<[^>]+>", "", unescape(str(value)))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_wilayah_name(name: str) -> str:
    normalized = clean_text(name)
    special_cases = {
        "ACEH": "Aceh",
        "SUMATERA UTARA": "Sumatera Utara",
        "SUMATERA BARAT": "Sumatera Barat",
        "RIAU": "Riau",
        "JAMBI": "Jambi",
        "SUMATERA SELATAN": "Sumatera Selatan",
        "BENGKULU": "Bengkulu",
        "LAMPUNG": "Lampung",
        "KEP. BANGKA BELITUNG": "Kepulauan Bangka Belitung",
        "KEPULAUAN RIAU": "Kepulauan Riau",
        "DKI JAKARTA": "DKI Jakarta",
        "JAWA BARAT": "Jawa Barat",
        "JAWA TENGAH": "Jawa Tengah",
        "D I YOGYAKARTA": "DI Yogyakarta",
        "JAWA TIMUR": "Jawa Timur",
        "BANTEN": "Banten",
        "BALI": "Bali",
        "NUSA TENGGARA BARAT": "Nusa Tenggara Barat",
        "NUSA TENGGARA TIMUR": "Nusa Tenggara Timur",
        "KALIMANTAN BARAT": "Kalimantan Barat",
        "KALIMANTAN TENGAH": "Kalimantan Tengah",
        "KALIMANTAN SELATAN": "Kalimantan Selatan",
        "KALIMANTAN TIMUR": "Kalimantan Timur",
        "KALIMANTAN UTARA": "Kalimantan Utara",
        "SULAWESI UTARA": "Sulawesi Utara",
        "SULAWESI TENGAH": "Sulawesi Tengah",
        "SULAWESI SELATAN": "Sulawesi Selatan",
        "SULAWESI TENGGARA": "Sulawesi Tenggara",
        "GORONTALO": "Gorontalo",
        "SULAWESI BARAT": "Sulawesi Barat",
        "MALUKU": "Maluku",
        "MALUKU UTARA": "Maluku Utara",
        "PAPUA BARAT": "Papua Barat",
        "PAPUA BARAT DAYA": "Papua Barat Daya",
        "PAPUA": "Papua",
        "PAPUA SELATAN": "Papua Selatan",
        "PAPUA TENGAH": "Papua Tengah",
        "PAPUA PEGUNUNGAN": "Papua Pegunungan",
        "INDONESIA": "Indonesia",
        "KOTA MAKASAR": "Kota Makassar",
        "KEP. SERIBU": "Kepulauan Seribu",
    }
    return special_cases.get(normalized.upper(), normalized.title())


def format_kode_wilayah(raw_code: int | str | None) -> str:
    code = str(raw_code or "").strip()
    digits = re.sub(r"\D", "", code)
    if not digits:
        return ""
    if len(digits) == 4:
        return f"{digits}000"
    if len(digits) == 7:
        return digits
    return digits


def parse_bps_number(raw_value: str | None) -> float | None:
    if not raw_value:
        return None
    cleaned = raw_value.replace(".", "").replace(",", ".").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def build_pdrb_url(config: dict[str, Any], api_key: str) -> str:
    path = (
        f"{BPS_PDRB_BASE_URL}/id/25/tahun/{config['tahun']}"
        f"/id_tabel/{config['id_tabel']}/wilayah/{config['wilayah']}"
    )
    return f"{path}/key/{api_key}"


def build_rls_url(config: dict[str, Any], api_key: str) -> str:
    return (
        f"{BPS_RLS_BASE_URL}/var/{config['var_id']}/th/{config['th_code']}"
        f"/key/{api_key}"
    )


def fetch_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.bps.go.id/",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def load_cached_or_remote_json(url: str, cache_key: str) -> tuple[dict[str, Any], str]:
    ensure_cache_dir()
    cache_path = CACHE_DIR / f"{cache_key}.json"
    now = time.time()

    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        fetched_at = float(cached.get("fetched_at", 0))
        if now - fetched_at < CACHE_TTL_SECONDS:
            return cached["payload"], "cache"

    try:
        payload = fetch_json(url)
        cache_path.write_text(
            json.dumps({"fetched_at": now, "payload": payload}, ensure_ascii=False),
            encoding="utf-8",
        )
        return payload, "live"
    except Exception:
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return cached["payload"], "stale-cache"
        raise


def extract_payload_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    top_level_data = payload.get("data", [])
    if not isinstance(top_level_data, list):
        return []
    for item in top_level_data:
        if isinstance(item, dict) and isinstance(item.get("data"), list):
            return item["data"]
    return []


def parse_pdrb_payload(payload: dict[str, Any], config: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for item in extract_payload_rows(payload):
        variables = item.get("variables", {})
        if not variables:
            continue
        first_variable = next(iter(variables.values()))
        wilayah = normalize_wilayah_name(item.get("label_raw"))
        rows.append(
            {
                "level_wilayah": config["level_wilayah"],
                "provinsi": wilayah,
                "wilayah": wilayah,
                "kode_wilayah": format_kode_wilayah(item.get("kode_wilayah")),
                "tahun": config["tahun"],
                "pdrb_berlaku_miliar": parse_bps_number(first_variable.get("value_raw")),
                "status_data": first_variable.get("value_code") or "-",
            }
        )
    return pd.DataFrame(rows)


def parse_rls_payload(payload: dict[str, Any], config: dict[str, Any]) -> pd.DataFrame:
    vervar = payload.get("vervar", [])
    datacontent = payload.get("datacontent", {})
    province_lookup: dict[str, str] = {}
    rows = []

    for item in vervar:
        code = str(item.get("val", ""))
        label = clean_text(item.get("label"))
        normalized_name = normalize_wilayah_name(label)
        kode_wilayah = format_kode_wilayah(code)
        is_national = code == "9999"
        is_province = len(code) == 4 and code.endswith("00") and code != "9999"

        if is_province:
            province_lookup[code[:2]] = normalized_name

        key = f"{code}{config['var_id']}{int(config['th_code']):04d}0"
        value = datacontent.get(key)
        if value is None:
            continue

        if is_national:
            level_wilayah = "Nasional"
            province_name = "Indonesia"
        elif is_province:
            level_wilayah = "Provinsi"
            province_name = normalized_name
        else:
            level_wilayah = "Kabupaten/Kota"
            province_name = province_lookup.get(code[:2], "")

        rows.append(
            {
                "level_wilayah": level_wilayah,
                "provinsi": province_name,
                "wilayah": normalized_name,
                "kode_wilayah": kode_wilayah,
                "tahun": config["tahun"],
                "rata_lama_sekolah": float(value),
            }
        )

    return pd.DataFrame(rows)


def load_remote_pdrb_data(api_key: str) -> tuple[pd.DataFrame, list[str]]:
    frames: list[pd.DataFrame] = []
    notices: list[str] = []

    for config in PDRB_CONFIGS:
        url = build_pdrb_url(config, api_key)
        cache_key = f"pdrb_{config['tahun']}_{config['id_tabel']}"
        try:
            payload, source = load_cached_or_remote_json(url, cache_key)
            frame = parse_pdrb_payload(payload, config)
            if frame.empty:
                notices.append(f"PDRB {config['tahun']} kosong.")
            else:
                frames.append(frame)
                notices.append(f"PDRB {config['tahun']} dimuat dari {source}.")
        except HTTPError as exc:
            if exc.code == 403:
                notices.append(
                    f"PDRB {config['tahun']} gagal: HTTP 403. Kemungkinan API key ditolak atau request tanpa akses yang diizinkan oleh BPS."
                )
            else:
                notices.append(f"PDRB {config['tahun']} gagal: HTTP {exc.code}.")
        except URLError as exc:
            notices.append(f"PDRB {config['tahun']} gagal konek: {exc.reason}.")
        except Exception as exc:
            notices.append(f"PDRB {config['tahun']} gagal: {exc}.")

    if not frames:
        return pd.DataFrame(), notices
    return pd.concat(frames, ignore_index=True), notices


def load_remote_rls_data(api_key: str) -> tuple[pd.DataFrame, list[str]]:
    frames: list[pd.DataFrame] = []
    notices: list[str] = []

    for config in RLS_CONFIGS:
        url = build_rls_url(config, api_key)
        cache_key = f"rls_{config['tahun']}_{config['var_id']}_{config['th_code']}"
        try:
            payload, source = load_cached_or_remote_json(url, cache_key)
            frame = parse_rls_payload(payload, config)
            if frame.empty:
                notices.append(f"RLS {config['tahun']} kosong.")
            else:
                frames.append(frame)
                notices.append(f"RLS {config['tahun']} dimuat dari {source}.")
        except HTTPError as exc:
            if exc.code == 403:
                notices.append(
                    f"RLS {config['tahun']} gagal: HTTP 403. Kemungkinan API key ditolak atau request tanpa akses yang diizinkan oleh BPS."
                )
            else:
                notices.append(f"RLS {config['tahun']} gagal: HTTP {exc.code}.")
        except URLError as exc:
            notices.append(f"RLS {config['tahun']} gagal konek: {exc.reason}.")
        except Exception as exc:
            notices.append(f"RLS {config['tahun']} gagal: {exc}.")

    if not frames:
        return pd.DataFrame(), notices
    return pd.concat(frames, ignore_index=True), notices


def build_sample_pdrb_data() -> pd.DataFrame:
    rows = [
        ("Aceh", "1100000", 2021, 214_000.00, "-"),
        ("Aceh", "1100000", 2022, 229_500.00, "-"),
        ("Aceh", "1100000", 2023, 244_000.00, "-"),
        ("Aceh", "1100000", 2025, 257_502.43, "**"),
        ("Sumatera Utara", "1200000", 2021, 1_060_000.00, "-"),
        ("Sumatera Utara", "1200000", 2022, 1_134_500.00, "-"),
        ("Sumatera Utara", "1200000", 2023, 1_190_600.00, "-"),
        ("Sumatera Utara", "1200000", 2025, 1_236_193.57, "**"),
        ("Sumatera Barat", "1300000", 2021, 245_400.00, "-"),
        ("Sumatera Barat", "1300000", 2022, 261_700.00, "-"),
        ("Sumatera Barat", "1300000", 2023, 278_200.00, "-"),
        ("Sumatera Barat", "1300000", 2025, 352_189.40, "**"),
        ("DKI Jakarta", "3100000", 2021, 3_401_200.00, "-"),
        ("DKI Jakarta", "3100000", 2022, 3_588_900.00, "-"),
        ("DKI Jakarta", "3100000", 2023, 3_756_400.00, "-"),
        ("DKI Jakarta", "3100000", 2025, 3_926_153.30, "**"),
        ("Jawa Barat", "3200000", 2021, 2_601_000.00, "-"),
        ("Jawa Barat", "3200000", 2022, 2_742_200.00, "-"),
        ("Jawa Barat", "3200000", 2023, 2_887_100.00, "-"),
        ("Jawa Barat", "3200000", 2025, 3_038_667.95, "**"),
        ("Jawa Timur", "3500000", 2021, 2_958_600.00, "-"),
        ("Jawa Timur", "3500000", 2022, 3_122_700.00, "-"),
        ("Jawa Timur", "3500000", 2023, 3_266_800.00, "-"),
        ("Jawa Timur", "3500000", 2025, 3_403_166.85, "**"),
    ]
    return pd.DataFrame(
        rows,
        columns=["wilayah", "kode_wilayah", "tahun", "pdrb_berlaku_miliar", "status_data"],
    ).assign(level_wilayah="Provinsi", provinsi=lambda df: df["wilayah"])


def build_sample_rls_data() -> pd.DataFrame:
    rows = [
        ("Provinsi", "Aceh", "Aceh", "1100000", 2021, 9.62),
        ("Provinsi", "Aceh", "Aceh", "1100000", 2022, 9.71),
        ("Provinsi", "Aceh", "Aceh", "1100000", 2023, 9.83),
        ("Provinsi", "Aceh", "Aceh", "1100000", 2025, 9.95),
        ("Kabupaten/Kota", "Aceh", "Simeulue", "1101000", 2025, 10.09),
        ("Kabupaten/Kota", "Aceh", "Aceh Singkil", "1102000", 2025, 9.05),
        ("Kabupaten/Kota", "Aceh", "Aceh Selatan", "1103000", 2025, 9.25),
        ("Provinsi", "Sumatera Utara", "Sumatera Utara", "1200000", 2021, 9.45),
        ("Provinsi", "Sumatera Utara", "Sumatera Utara", "1200000", 2022, 9.56),
        ("Provinsi", "Sumatera Utara", "Sumatera Utara", "1200000", 2023, 9.68),
        ("Provinsi", "Sumatera Utara", "Sumatera Utara", "1200000", 2025, 10.08),
        ("Kabupaten/Kota", "Sumatera Utara", "Kota Medan", "1275000", 2025, 11.80),
        ("Kabupaten/Kota", "Sumatera Utara", "Kota Pematang Siantar", "1273000", 2025, 11.83),
        ("Provinsi", "Sumatera Barat", "Sumatera Barat", "1300000", 2021, 9.18),
        ("Provinsi", "Sumatera Barat", "Sumatera Barat", "1300000", 2022, 9.31),
        ("Provinsi", "Sumatera Barat", "Sumatera Barat", "1300000", 2023, 9.42),
        ("Provinsi", "Sumatera Barat", "Sumatera Barat", "1300000", 2025, 9.77),
        ("Kabupaten/Kota", "Sumatera Barat", "Kota Padang", "1371000", 2025, 11.64),
        ("Provinsi", "DKI Jakarta", "DKI Jakarta", "3100000", 2021, 11.08),
        ("Provinsi", "DKI Jakarta", "DKI Jakarta", "3100000", 2022, 11.16),
        ("Provinsi", "DKI Jakarta", "DKI Jakarta", "3100000", 2023, 11.24),
        ("Provinsi", "DKI Jakarta", "DKI Jakarta", "3100000", 2025, 11.59),
        ("Kabupaten/Kota", "DKI Jakarta", "Kota Jakarta Selatan", "3171000", 2025, 12.06),
        ("Kabupaten/Kota", "DKI Jakarta", "Kota Jakarta Timur", "3172000", 2025, 12.01),
        ("Provinsi", "Jawa Barat", "Jawa Barat", "3200000", 2021, 8.61),
        ("Provinsi", "Jawa Barat", "Jawa Barat", "3200000", 2022, 8.73),
        ("Provinsi", "Jawa Barat", "Jawa Barat", "3200000", 2023, 8.86),
        ("Provinsi", "Jawa Barat", "Jawa Barat", "3200000", 2025, 9.14),
        ("Kabupaten/Kota", "Jawa Barat", "Kota Bandung", "3273000", 2025, 11.41),
        ("Kabupaten/Kota", "Jawa Barat", "Kota Bekasi", "3275000", 2025, 12.11),
        ("Provinsi", "Jawa Timur", "Jawa Timur", "3500000", 2021, 8.28),
        ("Provinsi", "Jawa Timur", "Jawa Timur", "3500000", 2022, 8.39),
        ("Provinsi", "Jawa Timur", "Jawa Timur", "3500000", 2023, 8.51),
        ("Provinsi", "Jawa Timur", "Jawa Timur", "3500000", 2025, 8.39),
        ("Kabupaten/Kota", "Jawa Timur", "Kota Surabaya", "3578000", 2025, 11.15),
        ("Kabupaten/Kota", "Jawa Timur", "Kota Malang", "3573000", 2025, 11.36),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "level_wilayah",
            "provinsi",
            "wilayah",
            "kode_wilayah",
            "tahun",
            "rata_lama_sekolah",
        ],
    )


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


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_datasets() -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
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

    dashboard_data = prepare_dashboard_dataset(pdrb_data, rls_data)
    return dashboard_data, rls_data, notices


def format_miliar(value: float) -> str:
    return f"Rp {value:,.2f} miliar"


def render_connected_scatter(data: pd.DataFrame) -> None:
    chart_data = data.sort_values(["wilayah", "tahun"]).copy()
    spec = {
        "height": 460,
        "layer": [
            {
                "mark": {"type": "line", "strokeWidth": 2},
                "encoding": {
                    "x": {
                        "field": "rata_lama_sekolah",
                        "type": "quantitative",
                        "title": "Rata-rata lama sekolah provinsi (tahun)",
                        "scale": {"zero": False},
                    },
                    "y": {
                        "field": "pdrb_berlaku_miliar",
                        "type": "quantitative",
                        "title": "PDRB ADHB provinsi (miliar rupiah)",
                        "scale": {"zero": False},
                    },
                    "color": {"field": "wilayah", "type": "nominal", "title": "Provinsi"},
                    "detail": [{"field": "wilayah"}],
                    "order": {"field": "tahun", "type": "quantitative"},
                    "tooltip": [
                        {"field": "wilayah", "type": "nominal", "title": "Provinsi"},
                        {"field": "tahun", "type": "ordinal", "title": "Tahun"},
                        {"field": "rata_lama_sekolah", "type": "quantitative", "title": "RLS", "format": ".2f"},
                        {"field": "pdrb_berlaku_miliar", "type": "quantitative", "title": "PDRB ADHB", "format": ",.2f"},
                    ],
                },
            },
            {
                "mark": {"type": "point", "filled": True, "size": 100},
                "encoding": {
                    "x": {"field": "rata_lama_sekolah", "type": "quantitative", "scale": {"zero": False}},
                    "y": {"field": "pdrb_berlaku_miliar", "type": "quantitative", "scale": {"zero": False}},
                    "color": {"field": "wilayah", "type": "nominal", "title": "Provinsi"},
                },
            },
            {
                "mark": {"type": "text", "dx": 10, "dy": -8, "fontSize": 11},
                "encoding": {
                    "x": {"field": "rata_lama_sekolah", "type": "quantitative", "scale": {"zero": False}},
                    "y": {"field": "pdrb_berlaku_miliar", "type": "quantitative", "scale": {"zero": False}},
                    "text": {"field": "tahun", "type": "ordinal"},
                    "color": {"field": "wilayah", "type": "nominal", "legend": None},
                },
            },
        ],
    }
    try:
        st.vega_lite_chart(chart_data, spec, use_container_width=True)
    except Exception as exc:
        st.warning(f"Grafik tidak berhasil dirender di browser, jadi ditampilkan sebagai tabel ringkas. Detail: {exc}")
        st.dataframe(
            chart_data[["wilayah", "tahun", "rata_lama_sekolah", "pdrb_berlaku_miliar"]],
            use_container_width=True,
            hide_index=True,
        )


def dashboard_page(data: pd.DataFrame, selected_regions: list[str]) -> None:
    st.title("Dashboard Ekonomi dan Pendidikan Provinsi")
    st.caption(
        "Grafik utama hanya menampilkan level provinsi agar hubungan PDRB dan rata-rata lama sekolah tetap jelas dibaca."
    )
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
    st.caption("Grafik tetap provinsi, tapi detail kabupaten/kota untuk lama sekolah ditampilkan di halaman tabel.")
    st.caption(f"Baris merge provinsi: {len(dashboard_data)} | Baris RLS terfilter: {len(rls_data)}")

    with st.expander("Deskripsi Data dan Sumber", expanded=False):
        st.markdown("**Sumber Data**")
        st.write(
            "Data berasal dari BPS dan disusun dari berbagai sensus, survei, serta sumber statistik resmi lainnya."
        )
        st.markdown(
            "- [Tabel BPS untuk PDRB Atas Dasar Harga Berlaku per Provinsi](https://www.bps.go.id/id/statistics-table/3/WkdVMWRYVnBkMnBvVEhKSVkyWXhNblZtTjJSbmR6MDkjMw==/produk-domestik-regional-bruto-atas-dasar-harga-berlaku-menurut-provinsi--miliar-rupiah-2022.html?year=2025)"
        )
        st.markdown(
            "- [Tabel BPS untuk Rata-rata Lama Sekolah Metode Baru](https://www.bps.go.id/id/statistics-table/2/NDE1IzI=/-metode-baru-rata-rata-lama-sekolah.html)"
        )
        st.markdown("**Keterangan Kode Data**")
        kode_col1, kode_col2 = st.columns(2)
        with kode_col1:
            st.markdown(
                """
                `...`  Data tidak tersedia  
                `–`  Tidak ada atau nol  
                `NA`  Data tidak dapat ditampilkan  
                `e`  Angka estimasi  
                `r`  Angka diperbaiki
                """
            )
        with kode_col2:
            st.markdown(
                """
                `~0`  Data dapat diabaikan  
                `*`  Angka sementara  
                `**`  Angka sangat sementara  
                `***`  Angka sangat sangat sementara  
                `a`  25% < RSE <= 50%
                """
            )

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
    st.caption("Halaman profil juga dibatasi ke provinsi agar konsisten dengan grafik utama.")
    st.caption(f"Baris data profil aktif: {len(data)}")

    available_regions = sorted(data["wilayah"].unique())
    preferred_region = selected_regions[0] if selected_regions else None
    default_region = preferred_region if preferred_region in available_regions else available_regions[0]
    region = st.selectbox("Pilih provinsi", available_regions, index=available_regions.index(default_region))

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


def about_page(notices: list[str]) -> None:
    st.title("Tentang Dataset")
    st.caption("Status integrasi endpoint BPS dan strategi cache lokal server.")

    st.markdown(
        """
        **Yang sudah diterapkan:**

        1. `Cache file 6 jam`
           Respons endpoint disimpan ke folder cache lokal server supaya tidak memukul API terus-menerus.
        2. `Grafik level provinsi`
           Scatter plot hanya memakai PDRB provinsi dan RLS provinsi.
        3. `Detail kabupaten/kota di tabel`
           RLS kabupaten/kota tetap tersedia untuk eksplorasi tabel.
        """
    )


dashboard_data, rls_data, notices = load_datasets()

st.sidebar.title("Navigasi")
page = st.sidebar.radio(
    "Pilih halaman",
    ["Dashboard", "Eksplorasi Data", "Profil Provinsi", "Tentang Dataset"],
)

st.sidebar.divider()
st.sidebar.subheader("Filter Provinsi")

province_options = []
if not dashboard_data.empty and "wilayah" in dashboard_data.columns:
    province_options = sorted(dashboard_data["wilayah"].unique())
selected_regions = st.sidebar.multiselect(
    "Provinsi fokus",
    options=province_options,
    default=province_options,
)

year_options = []
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

if page == "Tentang Dataset":
    about_page(notices)
elif filtered_dashboard.empty:
    st.warning("Data provinsi untuk filter ini kosong, jadi halaman analitik belum bisa ditampilkan.")
    st.caption("Coba pilih provinsi lain atau buka halaman Tentang Dataset untuk melihat status sumber data.")
else:
    if page == "Dashboard":
        dashboard_page(filtered_dashboard, selected_regions)
    elif page == "Eksplorasi Data":
        data_table_page(filtered_dashboard, filtered_rls)
    else:
        profile_page(filtered_dashboard, selected_regions)
