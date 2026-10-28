"""Generator laporan eksekutif otomatis (Markdown + PDF satu halaman).

Meniru output akhir pekerjaan Analis Pengawal Energi: ringkasan temuan untuk
pengambil keputusan — berapa SPBU terindikasi penyimpangan, di wilayah mana,
siapa verifikator yang perlu dibina, dan rekomendasi prioritas inspeksi ulang.

Output:
  reports/laporan_eksekutif.md
  reports/laporan_eksekutif.pdf
"""

import json
from datetime import datetime

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from src import config


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%".replace(".", ",")


def _fmt_num(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def build_findings() -> dict:
    """Kumpulkan semua temuan kunci dari artefak data/processed & data/raw."""
    clean = pd.read_csv(config.DATA_PROCESSED / "inspeksi_clean.csv",
                        parse_dates=["date"])
    feat = pd.read_csv(config.DATA_PROCESSED / "anomali_spbu.csv")
    region = pd.read_csv(config.DATA_PROCESSED / "distribusi_wilayah.csv")
    rel = pd.read_csv(config.DATA_PROCESSED / "kualitas_pelaporan.csv")
    validasi = json.loads((config.DATA_PROCESSED / "validasi_ringkasan.json").read_text(encoding="utf-8"))
    evaluasi = json.loads((config.DATA_PROCESSED / "evaluasi_deteksi.json").read_text(encoding="utf-8"))

    n_spbu = clean["spbu_id"].nunique()
    anom = feat.groupby("spbu_id")["indicated_anomaly"].max()
    n_anom_spbu = int(anom.sum())

    anom_feat = feat[feat["indicated_anomaly"]]
    by_region = (anom_feat.groupby("region")["spbu_id"].nunique()
                 .sort_values(ascending=False))
    worst_region = by_region.index[0] if len(by_region) else "-"

    # Estimasi nilai finansial: volume gap dikonversi ke rupiah memakai harga
    # bersubsidi per produk (asumsi terdokumentasi di src/config.py)
    gap_by_product = (anom_feat.assign(
        est_gap=(anom_feat["quota_liters"] - anom_feat["mean_sales_liters"]).clip(lower=0))
        .groupby("product")["est_gap"].sum() * config.N_DAYS)
    loss_value = sum(gap_by_product.get(p, 0.0) * spec["price_per_liter"]
                     for p, spec in config.PRODUCTS.items())

    bottom_ver = rel.nsmallest(5, "reliability_score")
    top_anom = (feat[feat["indicated_anomaly"]]
                .assign(util=lambda d: d["mean_utilization"])
                .nsmallest(8, "util"))

    rb = evaluasi["rule_based"]
    ifo = evaluasi["isolation_forest"]

    return {
        "clean": clean, "validasi": validasi, "evaluasi": evaluasi,
        "n_spbu": n_spbu, "n_anom_spbu": n_anom_spbu,
        "anom_share": n_anom_spbu / n_spbu,
        "by_region": by_region, "worst_region": worst_region,
        "loss_est_liters": float(sum(gap_by_product)),
        "loss_value_rp": float(loss_value),
        "bottom_ver": bottom_ver, "top_anom": top_anom,
        "region": region, "rb": rb, "ifo": ifo,
    }


def _recommendations(f: dict) -> list[str]:
    recs = []
    if f["n_anom_spbu"]:
        recs.append(
            f"Inspeksi ulang prioritas {f['n_anom_spbu']} SPBU terindikasi penyimpangan, "
            f"dengan konsentrasi tertinggi di {f['worst_region']} "
            f"({int(f['by_region'].iloc[0])} SPBU).")
    recs.append(
        "Terapkan rotasi verifikator untuk SPBU dengan skor reliabilitas di bawah "
        f"{_fmt_pct(config.THRESHOLDS['verificator_reliability_min'])} dan wajibkan "
        "pelatihan pengisian form.")
    recs.append(
        "Aktifkan pemantauan otomatis utilitas kuota harian dengan ambang "
        f"{_fmt_pct(config.THRESHOLDS['quota_util_min'])}–{_fmt_pct(config.THRESHOLDS['quota_util_max'])} "
        "agar penyimpangan terdeteksi sebelum akhir periode pelaporan.")
    recs.append(
        "Verifikasi fisik ketersediaan stok pada SPBU dengan rasio klaim stok habis "
        "tinggi namun penjualan rendah (indikasi distribusi tidak sesuai peruntukan).")
    return recs


def write_markdown(f: dict) -> str:
    v = f["validasi"]
    rb, ifo = f["rb"], f["ifo"]
    lines = [
        "# Laporan Eksekutif — Simulasi Pengawasan Distribusi BBM Bersubsidi",
        f"*Periode pelaporan: {f['clean']['date'].min().date()} s.d. "
        f"{f['clean']['date'].max().date()} · dibuat otomatis "
        f"{datetime.now().strftime('%d %B %Y')}*",
        "",
        "## Ringkasan Eksekutif",
        f"Dari **{f['n_spbu']} SPBU** yang diawasi {v['n_verificators']} verifikator selama 90 hari, "
        f"**{f['n_anom_spbu']} SPBU ({_fmt_pct(f['anom_share'])}) terindikasi penyimpangan** "
        f"— terkonsentrasi di **{f['worst_region']}**. Potensi volume bersubsidi yang tidak "
        f"tercatat diperkirakan **{_fmt_num(f['loss_est_liters'])} liter (≈ Rp "
        f"{_fmt_num(f['loss_value_rp'])} pada harga bersubsidi)** selama periode pelaporan. "
        "Rekomendasi utama: inspeksi ulang prioritas dan penguatan kualitas pelaporan verifikator.",
        "",
        "## Kualitas Data & Pelaporan Verifikator",
        f"- Laporan diterima {v['n_raw']:,} baris; {v['n_duplicates_removed']:,} duplikat dihapus, "
        f"{v['n_unit_corrected']:,} salah satuan dikoreksi, {v['n_missing_sales']:,} nilai penjualan kosong.",
        f"- Keterlambatan pelaporan {_fmt_pct(v['late_rate'])} ({v['n_late_reports']:,} laporan).",
        f"- Skor reliabilitas verifikator: rata-rata {v['mean_reliability']:.3f}, "
        f"{v['n_reliable_verificators']}/{v['n_verificators']} di atas ambang "
        f"{config.THRESHOLDS['verificator_reliability_min']:.2f}.",
        "",
        "### Verifikator dengan skor terendah (kandidat pembinaan)",
        "",
        "| Verifikator | Reliabilitas | Kelengkapan | Kiriman ganda | Salah satuan |",
        "|---|---|---|---|---|",
    ]
    for _, r in f["bottom_ver"].iterrows():
        lines.append(
            f"| {r['verifikator_id']} | {r['reliability_score']:.3f} | "
            f"{r['completeness_score']:.3f} | {_fmt_pct(r['duplicate_rate'])} | "
            f"{_fmt_pct(r['unit_issue_rate'])} |")
    lines += [
        "",
        "## Temuan Anomali Distribusi",
        f"- **{f['n_anom_spbu']} SPBU terindikasi penyimpangan** (≥2 dari 4 aturan: utilitas kuota "
        f"rendah, pola penjualan flat, klaim stok habis, melebihi kuota).",
        f"- Wilayah dengan temuan terbanyak: "
        + ", ".join(f"{idx} ({val})" for idx, val in f["by_region"].head(3).items()) + ".",
        f"- Kinerja deteksi terhadap ground truth simulasi — rule-based: presisi {_fmt_pct(rb['precision'])}, "
        f"recall {_fmt_pct(rb['recall'])}; Isolation Forest: presisi {_fmt_pct(ifo['precision'])}, "
        f"recall {_fmt_pct(ifo['recall'])}.",
        "",
        "### SPBU prioritas inspeksi ulang (utilitas kuota terendah)",
        "",
        "| SPBU | Wilayah | Produk | Utilitas kuota | CV penjualan | Klaim stok habis |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in f["top_anom"].iterrows():
        lines.append(
            f"| {r['spbu_id']} | {r['region']} | {r['product']} | "
            f"{_fmt_pct(r['mean_utilization'])} | {_fmt_pct(r['sales_cv'])} | "
            f"{_fmt_pct(r['stock_out_rate'])} |")
    lines += ["", "## Rekomendasi Tindak Lanjut"]
    lines += [f"{i}. {rec}" for i, rec in enumerate(_recommendations(f), 1)]
    lines += [
        "",
        "---",
        "*Catatan metodologi: seluruh data adalah simulasi dengan ground truth yang ditanamkan "
        "(parameter di `src/config.py`); business logic mengacu pada pemberitaan publik BPH Migas/"
        "Pertamina. Angka pada laporan ini bukan data resmi.*",
    ]
    md = "\n".join(lines)
    out = config.REPORTS / "laporan_eksekutif.md"
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    return md


def write_pdf(f: dict) -> None:
    v = f["validasi"]
    rb, ifo = f["rb"], f["ifo"]
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1x", parent=styles["Heading1"], fontSize=15, spaceAfter=2,
                        textColor=colors.HexColor("#1a3a5c"))
    h2 = ParagraphStyle("H2x", parent=styles["Heading2"], fontSize=11.5, spaceBefore=8,
                        spaceAfter=3, textColor=colors.HexColor("#1a3a5c"))
    body = ParagraphStyle("Bodyx", parent=styles["BodyText"], fontSize=8.6, leading=11.5)
    small = ParagraphStyle("Smallx", parent=body, fontSize=7.4, leading=9.5,
                           textColor=colors.HexColor("#555555"))

    doc = SimpleDocTemplate(
        str(config.REPORTS / "laporan_eksekutif.pdf"), pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=12 * mm,
        title="Laporan Eksekutif - Simulasi Pengawasan Distribusi BBM Bersubsidi")

    story = [
        Paragraph("Laporan Eksekutif — Simulasi Pengawasan Distribusi BBM Bersubsidi", h1),
        Paragraph(f"Periode {f['clean']['date'].min().date()} s.d. {f['clean']['date'].max().date()} · "
                  f"disusun otomatis {datetime.now().strftime('%d/%m/%Y')}", small),
        Spacer(1, 4),

        Paragraph("Ringkasan Eksekutif", h2),
        Paragraph(
            f"Dari <b>{f['n_spbu']} SPBU</b> yang diawasi <b>{v['n_verificators']} verifikator</b> selama 90 hari, "
            f"<b>{f['n_anom_spbu']} SPBU ({_fmt_pct(f['anom_share'])}) terindikasi penyimpangan</b>, terkonsentrasi "
            f"di <b>{f['worst_region']}</b>. Potensi volume bersubsidi tidak tercatat diperkirakan "
            f"<b>{_fmt_num(f['loss_est_liters'])} liter (≈ Rp {_fmt_num(f['loss_value_rp'])})</b>. "
            f"Kualitas pelaporan baik: {_fmt_pct(v['late_rate'])} laporan "
            f"terlambat, skor reliabilitas verifikator rata-rata {v['mean_reliability']:.3f}.", body),

        Paragraph("SPBU Prioritas Inspeksi Ulang", h2),
        Table(
            [[c for c in ("SPBU", "Wilayah", "Produk", "Util. kuota", "CV penjualan", "Stok habis")]] +
            [[r["spbu_id"], r["region"], r["product"], _fmt_pct(r["mean_utilization"]),
              _fmt_pct(r["sales_cv"]), _fmt_pct(r["stock_out_rate"])]
             for _, r in f["top_anom"].head(6).iterrows()],
            colWidths=[24 * mm, 32 * mm, 20 * mm, 26 * mm, 30 * mm, 24 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7.6),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#eef3f8")]),
                ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ])),
        Spacer(1, 5),

        Paragraph("Kualitas Pelaporan & Kinerja Deteksi", h2),
        Paragraph(
            f"Data mentah {v['n_raw']:,} baris → bersih {v['n_clean']:,} baris: {v['n_duplicates_removed']:,} duplikat "
            f"dihapus, {v['n_unit_corrected']:,} salah satuan dikoreksi. Terhadap ground truth simulasi, deteksi "
            f"rule-based mencapai presisi {_fmt_pct(rb['precision'])} / recall {_fmt_pct(rb['recall'])}; Isolation Forest "
            f"presisi {_fmt_pct(ifo['precision'])} / recall {_fmt_pct(ifo['recall'])}.", body),

        Paragraph("Rekomendasi Tindak Lanjut", h2),
    ]
    for i, rec in enumerate(_recommendations(f), 1):
        story.append(Paragraph(f"{i}. {rec}", body))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Catatan metodologi: seluruh data adalah simulasi dengan ground truth yang ditanamkan "
        "(parameter di src/config.py); business logic mengacu pada pemberitaan publik BPH Migas/Pertamina. "
        "Angka pada laporan ini bukan data resmi.", small))

    doc.build(story)


def main() -> None:
    f = build_findings()
    write_markdown(f)
    write_pdf(f)
    print(f"Laporan -> {(config.REPORTS / 'laporan_eksekutif.md').relative_to(config.PROJECT_ROOT)}")
    print(f"Laporan -> {(config.REPORTS / 'laporan_eksekutif.pdf').relative_to(config.PROJECT_ROOT)}")
    print(f"Intisari: {f['n_anom_spbu']}/{f['n_spbu']} SPBU terindikasi anomali "
          f"({_fmt_pct(f['anom_share'])}), terkonsentrasi di {f['worst_region']}")


if __name__ == "__main__":
    main()
