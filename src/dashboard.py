"""Dashboard Simulasi Pengawasan Distribusi BBM Bersubsidi.

Jalankan dari root proyek:
    .venv/Scripts/python.exe -m streamlit run src/dashboard.py

Halaman:
  1. Ringkasan Eksekutif  - KPI, temuan utama, rekomendasi
  2. Kualitas Data        - noise lapangan & skor reliabilitas verifikator
  3. Anomali Distribusi   - SPBU terindikasi penyimpangan & fitur risiko
  4. Tren & Wilayah       - tren penjualan harian dan capaian per wilayah
"""

import json

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import config

st.set_page_config(page_title="Dashboard Pengawasan BBM Bersubsidi",
                   page_icon="⛽", layout="wide")

PRODUCT_COLORS = {"Premium": "#e05c3a", "Solar": "#2a6f97"}


@st.cache_data
def load_data() -> dict:
    clean = pd.read_csv(config.DATA_PROCESSED / "inspeksi_clean.csv",
                        parse_dates=["date"])
    feat = pd.read_csv(config.DATA_PROCESSED / "anomali_spbu.csv")
    region = pd.read_csv(config.DATA_PROCESSED / "distribusi_wilayah.csv")
    trend = pd.read_csv(config.DATA_PROCESSED / "tren_harian.csv",
                        parse_dates=["date"])
    rel = pd.read_csv(config.DATA_PROCESSED / "kualitas_pelaporan.csv")
    validasi = json.loads((config.DATA_PROCESSED / "validasi_ringkasan.json").read_text(encoding="utf-8"))
    evaluasi = json.loads((config.DATA_PROCESSED / "evaluasi_deteksi.json").read_text(encoding="utf-8"))
    return {"clean": clean, "feat": feat, "region": region, "trend": trend,
            "rel": rel, "validasi": validasi, "evaluasi": evaluasi}


def fmt_pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%".replace(".", ",")


def fmt_num(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def main() -> None:
    d = load_data()
    feat, validasi = d["feat"], d["validasi"]

    st.title("⛽ Dashboard Pengawasan Distribusi BBM Bersubsidi")
    st.caption(
        "Simulasi pekerjaan analis pengawasan: data inspeksi SPBU sintetis dari "
        f"{validasi['n_verificators']} verifikator → validasi → analisis anomali → laporan. "
        "Seluruh data adalah simulasi (lihat catatan metodologi di bawah).")

    anom_spbu = feat.groupby("spbu_id")["indicated_anomaly"].max()
    n_anom = int(anom_spbu.sum())
    n_spbu = anom_spbu.shape[0]
    anom_feat = feat[feat["indicated_anomaly"]]

    tab1, tab2, tab3, tab4 = st.tabs(
        ["📋 Ringkasan Eksekutif", "🧹 Kualitas Data & Verifikator",
         "🚨 Anomali Distribusi", "📈 Tren & Wilayah"])

    # ------------------------------------------------------------------ Tab 1
    with tab1:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("SPBU diawasi", f"{n_spbu}")
        c2.metric("Terindikasi anomali", f"{n_anom}",
                  f"{fmt_pct(n_anom / n_spbu)} dari total",
                  delta_color="inverse")
        c3.metric("Verifikator reliabel",
                  f"{validasi['n_reliable_verificators']}/{validasi['n_verificators']}",
                  f"skor rata-rata {validasi['mean_reliability']:.3f}")
        c4.metric("Laporan bersih", fmt_num(validasi["n_clean"]),
                  f"{fmt_num(validasi['n_duplicates_removed'])} duplikat dihapus")

        loss = (anom_feat.assign(gap=(anom_feat["quota_liters"] - anom_feat["mean_sales_liters"]).clip(lower=0))
                ["gap"].sum() * config.N_DAYS)
        # Estimasi nilai finansial: volume gap dikonversi ke rupiah memakai harga
        # bersubsidi per produk (asumsi terdokumentasi di src/config.py)
        gap_by_product = (anom_feat.assign(
            gap=(anom_feat["quota_liters"] - anom_feat["mean_sales_liters"]).clip(lower=0))
            .groupby("product")["gap"].sum() * config.N_DAYS)
        loss_value = sum(gap_by_product.get(p, 0.0) * spec["price_per_liter"]
                         for p, spec in config.PRODUCTS.items())
        c5, c6 = st.columns(2)
        c5.metric("Estimasi volume tidak tercatat",
                  f"{fmt_num(loss)} L",
                  "selama 90 hari")
        c6.metric("Estimasi nilai subsidi berisiko",
                  f"Rp {fmt_num(loss_value)}",
                  "harga bersubsidi per produk")
        st.info(
            f"**Intisari:** {n_anom} SPBU terindikasi penyimpangan (utilitas kuota rendah + pola penjualan "
            f"flat + klaim stok habis). Potensi volume bersubsidi yang tidak tercatat ≈ "
            f"**{fmt_num(loss)} liter (≈ Rp {fmt_num(loss_value)})** selama 90 hari. Rekomendasi: inspeksi ulang "
            f"prioritas pada SPBU dengan utilitas terendah dan pembinaan verifikator berskor rendah.", icon="🎯")

        left, right = st.columns([2, 3])
        with left:
            st.markdown("#### Deteksi anomali per metode")
            ev = d["evaluasi"]
            comp = pd.DataFrame({
                "Metode": ["Rule-based (ambang batas)", "Isolation Forest"],
                "Presisi": [ev["rule_based"]["precision"], ev["isolation_forest"]["precision"]],
                "Recall": [ev["rule_based"]["recall"], ev["isolation_forest"]["recall"]],
            }).melt(id_vars="Metode", var_name="Metrik", value_name="Nilai")
            fig = px.bar(comp, x="Metode", y="Nilai", color="Metrik", barmode="group",
                         color_discrete_sequence=["#2a6f97", "#e0a13a"])
            fig.update_layout(height=300, yaxis_ticksuffix="", yaxis_tickformat=".0%",
                              legend_title=None, margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        with right:
            st.markdown("#### Sebaran SPBU terindikasi anomali per wilayah")
            by_region = (anom_feat.groupby("region")["spbu_id"].nunique()
                         .reindex(list(config.REGIONS), fill_value=0)
                         .reset_index(name="Jumlah SPBU"))
            fig = px.bar(by_region, x="region", y="Jumlah SPBU", text="Jumlah SPBU",
                         color="Jumlah SPBU", color_continuous_scale="Reds")
            fig.update_layout(height=300, coloraxis_showscale=False,
                              margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

    # ------------------------------------------------------------------ Tab 2
    with tab2:
        st.markdown("#### Skor reliabilitas verifikator")
        st.caption("Kelengkapan form & ketepatan waktu (60%) + konsistensi kiriman (25%) "
                   "+ kewajaran utilitas kuota (15%). Ambang reliabilitas: "
                   f"{config.THRESHOLDS['verificator_reliability_min']:.2f}.")
        c1, c2 = st.columns([3, 2])
        with c1:
            rel_sorted = d["rel"].sort_values("reliability_score")
            fig = px.histogram(d["rel"], x="reliability_score", nbins=25,
                               color="reliable",
                               color_discrete_map={True: "#2a6f97", False: "#e05c3a"})
            fig.add_vline(x=config.THRESHOLDS["verificator_reliability_min"],
                          line_dash="dash", line_color="#e05c3a",
                          annotation_text="ambang")
            fig.update_layout(height=320, showlegend=False,
                              xaxis_title="Skor reliabilitas", yaxis_title="Jumlah verifikator",
                              margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            worst = rel_sorted.head(10)
            fig = px.bar(worst, x="reliability_score", y="verifikator_id",
                         orientation="h", color="reliability_score",
                         color_continuous_scale="Reds",
                         hover_data=["completeness_score", "duplicate_rate", "unit_issue_rate"])
            fig.update_layout(height=320, coloraxis_showscale=False,
                              yaxis=dict(autorange="max"),
                              xaxis_title="Skor", yaxis_title=None,
                              margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### Detail per verifikator")
        show_cols = ["verifikator_id", "n_reports_raw", "n_spbu", "completeness_score",
                     "duplicate_rate", "unit_issue_rate", "reliability_score", "reliable"]
        st.dataframe(d["rel"][show_cols].sort_values("reliability_score"),
                     use_container_width=True, height=320)

    # ------------------------------------------------------------------ Tab 3
    with tab3:
        st.markdown(f"#### {n_anom} SPBU terindikasi penyimpangan "
                    f"(≥2 dari 4 aturan deteksi)")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Underreporting", fmt_num(int(feat["flag_underreporting"].sum())) + " (SPBU×produk)")
        c2.metric("Pola flat", fmt_num(int(feat["flag_flat_pattern"].sum())) + " (SPBU×produk)")
        c3.metric("Melebihi kuota", fmt_num(int(feat["flag_over_quota"].sum())) + " (SPBU×produk)")
        c4.metric("Klaim stok habis", fmt_num(int(feat["flag_stock_out"].sum())) + " (SPBU×produk)")

        fig = px.scatter(
            feat, x="mean_utilization", y="sales_cv", color="indicated_anomaly",
            color_discrete_map={True: "#e05c3a", False: "#8fa8bf"},
            hover_data=["spbu_id", "region", "product", "anomaly_score"],
            labels={"mean_utilization": "Rata-rata utilitas kuota",
                    "sales_cv": "Volatilitas penjualan (CV)"})
        fig.add_vline(x=config.THRESHOLDS["quota_util_min"], line_dash="dash",
                      line_color="#e05c3a", annotation_text="ambang bawah utilitas")
        fig.add_hline(y=config.THRESHOLDS["flat_cv"], line_dash="dash",
                      line_color="#e0a13a", annotation_text="ambang pola flat")
        fig.update_layout(height=420, yaxis_tickformat=".0%", xaxis_tickformat=".0%",
                          legend_title="Terindikasi anomali", margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### Daftar SPBU prioritas inspeksi ulang")
        prio_cols = ["spbu_id", "region", "product", "mean_utilization", "sales_cv",
                     "stock_out_rate", "anomaly_score", "iforest_score"]
        prio = feat[feat["indicated_anomaly"]][prio_cols].sort_values("mean_utilization")
        st.dataframe(prio.style.format({
            "mean_utilization": lambda x: fmt_pct(x),
            "sales_cv": lambda x: fmt_pct(x),
            "stock_out_rate": lambda x: fmt_pct(x),
            "iforest_score": lambda x: f"{x:.3f}",
        }), use_container_width=True, height=300)

    # ------------------------------------------------------------------ Tab 4
    with tab4:
        left, right = st.columns(2)
        with left:
            st.markdown("#### Tren penjualan harian nasional")
            fig = px.line(d["trend"], x="date", y="total_sales_liters", color="product",
                          color_discrete_map=PRODUCT_COLORS)
            fig.update_layout(height=340, yaxis_title="Liter/hari", xaxis_title=None,
                              legend_title=None, margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        with right:
            st.markdown("#### Utilitas kuota per wilayah & produk")
            fig = px.bar(d["region"], x="region", y="utilization", color="product",
                         barmode="group", color_discrete_map=PRODUCT_COLORS)
            fig.add_hline(y=1.0, line_dash="dash", line_color="#888888",
                          annotation_text="kuota 100%")
            fig.update_layout(height=340, yaxis_tickformat=".0%",
                              yaxis_title="Utilitas", xaxis_title=None,
                              legend_title=None, margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### Volume penjualan & kuota per wilayah")
        show = d["region"].copy()
        show["total_sales_liters"] = show["total_sales_liters"].map(fmt_num)
        show["total_quota_liters"] = show["total_quota_liters"].map(fmt_num)
        show["utilization"] = show["utilization"].map(lambda x: fmt_pct(x))
        show = show.rename(columns={
            "region": "Wilayah", "product": "Produk",
            "total_sales_liters": "Total penjualan (L)",
            "total_quota_liters": "Total kuota (L)", "utilization": "Utilitas",
            "n_spbu": "Jumlah SPBU"})
        st.dataframe(show, use_container_width=True, hide_index=True)

    st.divider()
    st.caption(
        "**Catatan metodologi** — Seluruh data adalah simulasi dengan ground truth yang ditanamkan "
        "(parameter di `src/config.py`); business logic mengacu pada pemberitaan publik BPH Migas/"
        "Pertamina. Angka pada dashboard ini bukan data resmi.")
    st.caption(
        "**Kualitas proyek** — 33 automated test (pytest + Streamlit AppTest) · pipeline "
        "deterministik dengan seed · seluruh asumsi terdokumentasi di `src/config.py` · "
        "laporan eksekutif otomatis (MD + PDF).")


if __name__ == "__main__":
    main()
