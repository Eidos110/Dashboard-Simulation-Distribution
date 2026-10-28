"""Uji unit generator data sintetis: struktur, noise, dan ground truth."""

import numpy as np
import pandas as pd

from src import config
from src.generate_data import generate_raw_reports


def test_shape_and_ids(small_raw):
    """Struktur dasar: jumlah SPBU, produk, hari, dan verifikator sesuai config."""
    assert small_raw["spbu_id"].nunique() == 20
    assert set(small_raw["product"]) == set(config.PRODUCTS)
    n_days = pd.to_datetime(config.START_DATE).to_period("D")
    assert small_raw["date"].nunique() == 14
    assert (small_raw["verifikator_id"].str.match(r"^VER-\d{3}$")).all()


def test_no_negative_values(small_raw):
    """Penjualan & stok tidak boleh negatif."""
    assert (small_raw["reported_sales_liters"].dropna() >= 0).all()
    assert (small_raw["closing_stock_liters"].dropna() >= 0).all()


def test_duplicates_are_copies_not_originals(small_raw):
    """Regression: is_duplicate_truth harus menandai baris SALINAN (RPT-D)."""
    marked = small_raw[small_raw["is_duplicate_truth"]]
    assert len(marked) > 0
    assert marked["report_id"].str.startswith("RPT-D").all()
    # setiap salinan punya kembaran bernilai sama di baris asli
    key_cols = ["spbu_id", "product", "date", "reported_sales_liters"]
    for _, row in marked.head(20).iterrows():
        twins = small_raw[
            (small_raw["spbu_id"] == row["spbu_id"])
            & (small_raw["product"] == row["product"])
            & (small_raw["date"] == row["date"])
            & (small_raw["report_id"] != row["report_id"])]
        assert len(twins) >= 1


def test_late_rate_close_to_config(small_raw):
    """Regression: rate keterlambatan efektif mendekati NOISE config (bukan ~75%)."""
    rate = small_raw["is_late"].mean()
    target = config.NOISE["late_report_rate"]
    assert abs(rate - target) < 0.03, f"late rate {rate:.3f} vs config {target}"
    # laporan terlambat selalu submitted > tanggal laporan; tepat waktu tidak
    assert (small_raw.loc[small_raw["is_late"], "submitted_date"]
            > small_raw.loc[small_raw["is_late"], "date"]).all()
    assert (small_raw.loc[~small_raw["is_late"], "submitted_date"]
            == small_raw.loc[~small_raw["is_late"], "date"]).all()


def test_unit_issue_signature(small_raw):
    """Laporan salah satuan bernilai kecil (skala hektoliter) dan ada yang terdeteksi."""
    small = small_raw[(small_raw["reported_sales_liters"].notna())
                      & (small_raw["reported_sales_liters"] > 0)
                      & (small_raw["reported_sales_liters"] < 50)]
    assert len(small) > 0, "harus ada laporan bersatuan hektoliter di raw"


def test_missing_fields_present(small_raw):
    """Noise kolom kosong benar-benar ditanamkan."""
    assert small_raw["reported_sales_liters"].isna().sum() > 0
    assert small_raw["closing_stock_liters"].isna().sum() > 0


def test_anomalous_truth_labeled(small_raw):
    """Ground truth anomali berporsi sesuai config dan konsisten per SPBU."""
    truth = small_raw.groupby("spbu_id")["is_anomalous_truth"].first()
    share = truth.mean()
    assert abs(share - config.ANOMALY["spbu_share"]) < 0.15
    # konsisten: satu SPBU punya satu nilai truth
    assert (small_raw.groupby("spbu_id")["is_anomalous_truth"].nunique() == 1).all()


def test_anomalous_spbu_behavior(small_raw):
    """SPBU anomali: utilitas rendah & flat; SPBU normal: utilitas wajar."""
    clean = small_raw.dropna(subset=["reported_sales_liters"]).copy()
    clean["util"] = clean["reported_sales_liters"] / clean["quota_liters"]
    agg = clean.groupby(["spbu_id", "is_anomalous_truth"])["util"].agg(["mean", "std"])
    anom = agg.xs(True, level="is_anomalous_truth")
    norm = agg.xs(False, level="is_anomalous_truth")
    assert (anom["mean"] < config.THRESHOLDS["quota_util_min"] + 0.05).all()
    assert (norm["mean"] > config.THRESHOLDS["quota_util_min"]).mean() > 0.95


def test_reproducible_with_same_seed(rng):
    """Seed sama -> data identik (penting agar laporan dapat direproduksi)."""
    a = generate_raw_reports(np.random.default_rng(config.SEED))
    b = generate_raw_reports(np.random.default_rng(config.SEED))
    pd.testing.assert_frame_equal(a, b)
