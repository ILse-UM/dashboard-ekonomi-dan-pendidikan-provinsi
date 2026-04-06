from pathlib import Path


CACHE_TTL_SECONDS = 6 * 60 * 60
CACHE_DIR = Path(".cache/bps")
REFRESH_LOCK_TIMEOUT_SECONDS = 10 * 60
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
