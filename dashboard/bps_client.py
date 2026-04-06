import json
import re
import threading
import time
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from dashboard.config import (
    BPS_PDRB_BASE_URL,
    BPS_RLS_BASE_URL,
    CACHE_DIR,
    CACHE_TTL_SECONDS,
    PDRB_CONFIGS,
    REFRESH_LOCK_TIMEOUT_SECONDS,
    RLS_CONFIGS,
)


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


def read_cache_record(cache_path: Path) -> dict[str, Any] | None:
    if not cache_path.exists():
        return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_cache_record(cache_path: Path, payload: dict[str, Any], fetched_at: float | None = None) -> None:
    cache_path.write_text(
        json.dumps(
            {"fetched_at": fetched_at if fetched_at is not None else time.time(), "payload": payload},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def refresh_lock_path(cache_key: str) -> Path:
    return CACHE_DIR / f"{cache_key}.lock"


def is_refresh_in_progress(lock_path: Path, now: float) -> bool:
    if not lock_path.exists():
        return False
    try:
        age = now - lock_path.stat().st_mtime
    except OSError:
        return False
    if age < REFRESH_LOCK_TIMEOUT_SECONDS:
        return True
    try:
        lock_path.unlink()
    except OSError:
        pass
    return False


def refresh_cache_file(url: str, cache_path: Path, lock_path: Path, cache_key: str) -> None:
    try:
        payload = fetch_json(url)
        write_cache_record(cache_path, payload)
        print(f"[data-refresh] cache `{cache_key}` berhasil diperbarui di background.")
    except Exception as exc:
        print(f"[data-refresh] cache `{cache_key}` gagal diperbarui di background: {exc}")
    finally:
        try:
            lock_path.unlink()
        except OSError:
            pass


def trigger_background_refresh(url: str, cache_key: str, cache_path: Path) -> bool:
    ensure_cache_dir()
    lock_path = refresh_lock_path(cache_key)
    now = time.time()
    if is_refresh_in_progress(lock_path, now):
        return False

    try:
        lock_path.write_text(str(now), encoding="utf-8")
    except OSError:
        return False

    thread = threading.Thread(
        target=refresh_cache_file,
        args=(url, cache_path, lock_path, cache_key),
        daemon=True,
    )
    thread.start()
    return True


def load_cached_or_remote_json(url: str, cache_key: str) -> tuple[dict[str, Any], str]:
    ensure_cache_dir()
    cache_path = CACHE_DIR / f"{cache_key}.json"
    now = time.time()
    cached = read_cache_record(cache_path)

    if cached is not None:
        fetched_at = float(cached.get("fetched_at", 0))
        if now - fetched_at < CACHE_TTL_SECONDS:
            return cached["payload"], "cache"
        refresh_started = trigger_background_refresh(url, cache_key, cache_path)
        source = "stale-cache-refreshing" if refresh_started else "stale-cache"
        return cached["payload"], source

    try:
        payload = fetch_json(url)
        write_cache_record(cache_path, payload, fetched_at=now)
        return payload, "live"
    except Exception:
        cached = read_cache_record(cache_path)
        if cached is not None:
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
