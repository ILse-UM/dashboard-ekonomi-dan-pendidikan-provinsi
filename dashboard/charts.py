import pandas as pd
import streamlit as st


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
