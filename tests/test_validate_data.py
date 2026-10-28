"""Uji unit lapisan validasi: dedup, koreksi satuan, skor verifikator."""

import numpy as np
import pandas as pd
import pytest

from src import config
from src.validate_data import (completeness_score, detect_unit_issue,
                               remove_duplicates, standardize_units,
                               verificator_reliability)


def _make_df(rows):
    df = pd.DataFrame(rows)
    df["is_late"] = df.get("is_late", pd.Series(False, index=df.index))
    return df


def test_remove_duplicates_keeps_first():
    df = _make_df([
        {"report_id": "A", "spbu_id": "S1", "product": "Premium", "date": "2026-01-01",
         "verifikator_id": "V1", "reported_sales_liters": 100.0, "closing_stock_liters": 50.0},
        {"report_id": "B", "spbu_id": "S1", "product": "Premium", "date": "2026-01-01",
         "verifikator_id": "V1", "reported_sales_liters": 100.0, "closing_stock_liters": 50.0},
        {"report_id": "C", "spbu_id": "S1", "product": "Premium", "date": "2026-01-02",
         "verifikator_id": "V1", "reported_sales_liters": 120.0, "closing_stock_liters": 40.0},
    ])
    clean, dup_by_ver, n_removed = remove_duplicates(df)
    assert n_removed == 1
    assert len(clean) == 2
    assert set(clean["report_id"]) == {"A", "C"}  # first kept
    assert dup_by_ver["V1"] == 1


def test_detect_unit_issue_flags_hectoliter_values():
    df = _make_df([
        # 8.0 liter padahal kuota 900 -> jelas salah satuan (harusnya 800 L)
        {"report_id": "A", "spbu_id": "S1", "product": "Premium", "quota_liters": 900,
         "reported_sales_liters": 8.0, "closing_stock_liters": 2.0},
        # 720 liter dari kuota 900 -> normal, bukan salah satuan
        {"report_id": "B", "spbu_id": "S1", "product": "Premium", "quota_liters": 900,
         "reported_sales_liters": 720.0, "closing_stock_liters": 100.0},
        # NaN tidak boleh terdeteksi
        {"report_id": "C", "spbu_id": "S1", "product": "Premium", "quota_liters": 900,
         "reported_sales_liters": np.nan, "closing_stock_liters": 100.0},
        # 13.5 dari kuota 900 = tepat 1.5% (batas) -> terdeteksi
        {"report_id": "D", "spbu_id": "S1", "product": "Premium", "quota_liters": 900,
         "reported_sales_liters": 13.5, "closing_stock_liters": 2.0},
    ])
    flags = detect_unit_issue(df)
    assert list(flags) == [True, False, False, True]


def test_standardize_units_multiplies_by_100():
    df = _make_df([
        {"report_id": "A", "spbu_id": "S1", "product": "Premium", "quota_liters": 900,
         "reported_sales_liters": 8.0, "closing_stock_liters": 2.0},
        {"report_id": "B", "spbu_id": "S1", "product": "Premium", "quota_liters": 900,
         "reported_sales_liters": 720.0, "closing_stock_liters": 100.0},
    ])
    fixed = standardize_units(df)
    assert fixed["had_unit_issue"].sum() == 1
    assert fixed.loc[0, "reported_sales_liters"] == 800.0
    assert fixed.loc[0, "closing_stock_liters"] == 200.0
    assert fixed.loc[1, "reported_sales_liters"] == 720.0  # baris normal tak tersentuh


def test_completeness_score_components():
    # semua terisi & tepat waktu -> 1.0
    full = _make_df([
        {"reported_sales_liters": 100.0, "closing_stock_liters": 50.0, "is_late": False},
        {"reported_sales_liters": 90.0, "closing_stock_liters": 40.0, "is_late": False},
    ])
    assert completeness_score(full) == 1.0
    # semua kosong & terlambat -> 0.0
    empty = _make_df([
        {"reported_sales_liters": np.nan, "closing_stock_liters": np.nan, "is_late": True},
    ])
    assert completeness_score(empty) == 0.0
    # bobot: 60% kelengkapan + 40% ketepatan waktu
    half = _make_df([
        {"reported_sales_liters": 100.0, "closing_stock_liters": 50.0, "is_late": True},
        {"reported_sales_liters": np.nan, "closing_stock_liters": np.nan, "is_late": False},
    ])
    assert completeness_score(half) == pytest.approx(0.5)


def test_verificator_reliability_orders_penalized_first(small_clean):
    rel = verificator_reliability(
        small_clean,
        dup_by_ver=pd.Series(dtype=int),
        raw_counts=small_clean.groupby("verifikator_id").size())
    # skor dalam [0,1], reliabel sesuai ambang
    assert rel["reliability_score"].between(0, 1).all()
    expected = rel["reliability_score"] >= config.THRESHOLDS["verificator_reliability_min"]
    assert (rel["reliable"] == expected).all()
    # verifikator dengan laporan kosong banyak harus lebih rendah dari yang rapi
    assert rel["reliability_score"].max() >= rel["reliability_score"].min()


def test_verificator_reliability_duplicate_penalty():
    """Regression: kiriman ganda per verifikator ikut menurunkan konsistensi."""
    base = {"product": "Premium", "date": "2026-01-01", "quota_liters": 900,
            "reported_sales_liters": 700.0, "closing_stock_liters": 100.0,
            "is_late": False}
    rows = []
    for i in range(10):
        rows.append({"report_id": f"R{i}", "spbu_id": "S1", "verifikator_id": "V1", **base})
    clean = _make_df(rows)
    clean["had_unit_issue"] = False
    clean["quota_utilization"] = clean["reported_sales_liters"] / clean["quota_liters"]

    raw_counts = pd.Series({"V1": 12})          # 10 bersih + 2 duplikat
    dup_by_ver = pd.Series({"V1": 2})
    rel = verificator_reliability(clean, dup_by_ver, raw_counts)
    # duplikat rate 2/12 menurunkan konsistensi, tapi tidak sampai nol
    assert rel.loc[0, "duplicate_rate"] == pytest.approx(2 / 12, abs=1e-3)
    assert rel.loc[0, "reliability_score"] < 0.60 * 1.0 + 0.25 * 1.0 + 0.15 * 1.0
    assert rel.loc[0, "reliability_score"] > 0.6  # tidak dihukum sampai hancur
