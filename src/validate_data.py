"""Lapisan validasi & konsolidasi data inspeksi lapangan.

Meniru tugas Analis Pengawal Energi: "memvalidasi dan mengkonsolidasikan data
lapangan" serta "memantau kualitas pelaporan verifikator". Output:
  1. data/processed/inspeksi_clean.csv  - data bersih siap analisis
  2. data/processed/kualitas_pelaporan.csv - skor per verifikator
  3. data/processed/validasi_ringkasan.json - metrik kualitas agregat
"""

import json

import numpy as np
import pandas as pd

from src import config

KEY_COLS = ["spbu_id", "product", "date", "verifikator_id",
            "reported_sales_liters", "closing_stock_liters"]


def detect_unit_issue(df: pd.DataFrame) -> pd.Series:
    """Deteksi laporan yang ditulis dalam hektoliter alih-alih liter.

    Signature: nilai jauh di bawah kuota (<= 1,5% kuota, yaitu rentang hektoliter)
    dan merupakan kelipatan 0,1 yang bulat — konvensi simulasi ini; pada data
    nyata butuh konfirmasi verifikator.
    """
    mask = df["reported_sales_liters"].notna() & (df["reported_sales_liters"] > 0)
    hl_range = df["reported_sales_liters"] <= df["quota_liters"] * 0.015
    return mask & hl_range


def completeness_score(sub: pd.DataFrame) -> float:
    """Skor kelengkapan laporan satu verifikator (0-1): form terisi penuh & tepat waktu."""
    required = ["reported_sales_liters", "closing_stock_liters"]
    filled = sub[required].notna().all(axis=1).mean()
    ontime = (~sub["is_late"]).mean()
    return round(0.6 * filled + 0.4 * ontime, 4)


def remove_duplicates(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, int]:
    """Hapus laporan ganda (baris identik pada kunci logis, simpan yang pertama).

    Mengembalikan (data bersih, jumlah kiriman ganda per verifikator, total dihapus).
    Kiriman ganda dihitung SEBELUM barisnya dihapus karena perilaku verifikator.
    """
    dup_mask = raw.duplicated(subset=KEY_COLS, keep="first")
    dup_by_ver = raw.loc[dup_mask].groupby("verifikator_id").size()
    clean = raw.loc[~dup_mask].copy()
    return clean, dup_by_ver, int(dup_mask.sum())


def standardize_units(clean: pd.DataFrame) -> pd.DataFrame:
    """Deteksi laporan bersatuan hektoliter, tandai, lalu koreksi x100 ke liter."""
    clean = clean.copy()
    clean["had_unit_issue"] = detect_unit_issue(clean)
    unit_mask = clean["had_unit_issue"]
    clean.loc[unit_mask, "reported_sales_liters"] = (
        clean.loc[unit_mask, "reported_sales_liters"] * 100)
    stock_unit = unit_mask & clean["closing_stock_liters"].notna()
    clean.loc[stock_unit, "closing_stock_liters"] = (
        clean.loc[stock_unit, "closing_stock_liters"] * 100)
    return clean


def verificator_reliability(clean: pd.DataFrame, dup_by_ver: pd.Series,
                            raw_counts: pd.Series) -> pd.DataFrame:
    """Skor reliabilitas tiap verifikator dari kualitas & perilaku laporannya.

    Komponen:
      - kelengkapan (60%): form terisi penuh & tepat waktu
      - konsistensi (25%): 1 - rasio kiriman ganda & laporan satuan campur
      - kewajaran (15%): rasio laporan dengan utilitas kuota dalam batas wajar
    """
    unit_by_ver = clean.groupby("verifikator_id")["had_unit_issue"].mean()
    within = clean["quota_utilization"].between(
        config.THRESHOLDS["quota_util_min"], config.THRESHOLDS["quota_util_max"])
    plaus_by_ver = within.groupby(clean["verifikator_id"]).mean()

    rows = []
    for vid, sub in clean.groupby("verifikator_id"):
        completeness = completeness_score(sub)
        dup_ratio = float(dup_by_ver.get(vid, 0.0)) / float(raw_counts.get(vid, 1))
        unit_ratio = float(unit_by_ver.get(vid, 0.0))
        consistency = max(1.0 - (dup_ratio + unit_ratio), 0.0)
        plausibility = float(plaus_by_ver.get(vid, 0.0))

        reliability = round(0.60 * completeness + 0.25 * consistency
                            + 0.15 * plausibility, 4)
        rows.append({
            "verifikator_id": vid,
            "n_reports_raw": int(raw_counts.get(vid, 0)),
            "n_reports_clean": len(sub),
            "n_spbu": sub["spbu_id"].nunique(),
            "duplicate_rate": round(dup_ratio, 4),
            "unit_issue_rate": round(unit_ratio, 4),
            "completeness_score": completeness,
            "consistency_score": round(consistency, 4),
            "plausibility_score": round(plausibility, 4),
            "reliability_score": reliability,
            "reliable": reliability >= config.THRESHOLDS["verificator_reliability_min"],
        })
    return pd.DataFrame(rows).sort_values("reliability_score")


def main() -> None:
    raw_path = config.DATA_RAW / "inspeksi_raw.csv"
    raw = pd.read_csv(raw_path, parse_dates=["date", "submitted_date"])
    raw_counts = raw.groupby("verifikator_id").size()

    # 1) Duplikasi: hitung dulu kiriman ganda per verifikator (dari baris yang akan dihapus)
    clean, dup_by_ver, n_dups = remove_duplicates(raw)

    # 2) Satuan: deteksi sebelum koreksi
    clean = standardize_units(clean)
    n_units = int(clean["had_unit_issue"].sum())

    # 3) Utilitas kuota
    clean["quota_utilization"] = clean["reported_sales_liters"] / clean["quota_liters"]

    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    clean_path = config.DATA_PROCESSED / "inspeksi_clean.csv"
    clean.to_csv(clean_path, index=False)

    # 4) Skor verifikator
    rel = verificator_reliability(clean, dup_by_ver, raw_counts)
    rel_path = config.DATA_PROCESSED / "kualitas_pelaporan.csv"
    rel.to_csv(rel_path, index=False)

    summary = {
        "n_raw": int(len(raw)),
        "n_clean": int(len(clean)),
        "n_duplicates_removed": int(n_dups),
        "n_unit_corrected": n_units,
        "n_missing_sales": int(clean["reported_sales_liters"].isna().sum()),
        "n_late_reports": int(clean["is_late"].sum()),
        "late_rate": round(float(clean["is_late"].mean()), 4),
        "n_verificators": int(rel.shape[0]),
        "n_reliable_verificators": int(rel["reliable"].sum()),
        "mean_reliability": round(float(rel["reliability_score"].mean()), 4),
        "min_reliability": round(float(rel["reliability_score"].min()), 4),
    }
    summary_path = config.DATA_PROCESSED / "validasi_ringkasan.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Clean data  : {summary['n_clean']:,} baris -> {clean_path.relative_to(config.PROJECT_ROOT)}")
    print(f"Duplikat    : {summary['n_duplicates_removed']:,} dihapus | satuan dikoreksi: {summary['n_unit_corrected']:,}")
    print(f"Terlambat   : {summary['n_late_reports']:,} ({summary['late_rate']:.1%})")
    print(f"Verifikator : {summary['n_verificators']} | reliabel: {summary['n_reliable_verificators']} "
          f"| skor rata-rata {summary['mean_reliability']:.3f} | terendah {summary['min_reliability']:.3f}")
    print(f"Skor        -> {rel_path.relative_to(config.PROJECT_ROOT)} | ringkasan -> {summary_path.relative_to(config.PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
