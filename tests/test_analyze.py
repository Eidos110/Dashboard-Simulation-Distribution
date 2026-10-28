"""Uji unit lapisan analisis: fitur, aturan anomali, Isolation Forest, evaluasi."""

import numpy as np
import pandas as pd
import pytest

from src import config
from src.analyze import (daily_spbu_table, evaluate_detection,
                         isolation_forest_flags, regional_summary,
                         rule_based_flags, spbu_features)


def _make_feat(rows):
    return pd.DataFrame(rows)


def _base_feat(n_normal=50, n_anom=5, seed=1):
    """Fitur sintetis: normal utilitas ~0.85/CV ~0.12; anomali ~0.35/CV ~0.02."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_normal):
        rows.append({"spbu_id": f"S{i:03d}", "region": "Jawa Tengah", "product": "Premium",
                     "n_days": 90, "quota_liters": 900,
                     "mean_sales_liters": 765.0, "mean_utilization": rng.uniform(0.72, 1.0),
                     "sales_cv": rng.uniform(0.08, 0.18), "stock_out_rate": rng.uniform(0, 0.1),
                     "is_anomalous_truth": False})
    for i in range(n_anom):
        rows.append({"spbu_id": f"A{i:03d}", "region": "Jawa Timur", "product": "Premium",
                     "n_days": 90, "quota_liters": 900,
                     "mean_sales_liters": 315.0, "mean_utilization": rng.uniform(0.33, 0.38),
                     "sales_cv": rng.uniform(0.01, 0.04), "stock_out_rate": rng.uniform(0.9, 1.0),
                     "is_anomalous_truth": True})
    return pd.DataFrame(rows)


def test_rule_based_flags_catch_anomalies():
    feat = rule_based_flags(_base_feat())
    assert feat["indicated_anomaly"].sum() >= 5  # semua anomali sintetis tertangkap
    # skor anomali = jumlah flag yang aktif
    flags = feat[["flag_underreporting", "flag_over_quota", "flag_flat_pattern",
                  "flag_stock_out"]].sum(axis=1)
    assert (feat["anomaly_score"] == flags).all()
    # indikasi anomali butuh >= 2 aturan
    assert (feat.loc[feat["indicated_anomaly"], "anomaly_score"] >= 2).all()


def test_rule_based_no_false_positive_on_clean_data():
    """SPBU dengan utilitas wajar & CV sehat tidak boleh terindikasi."""
    feat = _make_feat([{"spbu_id": "OK1", "region": "R", "product": "Premium",
                        "n_days": 90, "quota_liters": 900, "mean_sales_liters": 800.0,
                        "mean_utilization": 0.89, "sales_cv": 0.12,
                        "stock_out_rate": 0.05, "is_anomalous_truth": False}])
    feat = rule_based_flags(feat)
    assert not feat.loc[0, "indicated_anomaly"]


def test_isolation_forest_flags_shape_and_separation():
    feat = _base_feat()
    out = isolation_forest_flags(feat)
    assert "iforest_anomaly" in out and "iforest_score" in out
    assert out["iforest_anomaly"].sum() > 0
    # skor anomali cluster harus lebih tinggi dari mayoritas normal
    assert out.loc[out["iforest_anomaly"], "iforest_score"].mean() > \
        out.loc[~out["iforest_anomaly"], "iforest_score"].mean()


def test_evaluate_detection_perfect_on_separable():
    feat = rule_based_flags(_base_feat())
    feat = isolation_forest_flags(feat)
    res = evaluate_detection(feat)
    rb = res["rule_based"]
    assert rb["false_negative"] == 0
    assert rb["false_positive"] == 0
    assert rb["precision"] == 1.0 and rb["recall"] == 1.0


def test_evaluate_detection_counts_valid_ranges():
    feat = rule_based_flags(_base_feat())
    feat = isolation_forest_flags(feat)
    res = evaluate_detection(feat)
    for method in ("rule_based", "isolation_forest"):
        m = res[method]
        assert 0 <= m["precision"] <= 1 and 0 <= m["recall"] <= 1
        assert m["f1"] <= 1.0


def test_daily_spbu_table_utilization():
    clean = pd.DataFrame([
        {"spbu_id": "S1", "region": "R", "verifikator_id": "V1", "product": "Premium",
         "date": "2026-01-01", "reported_sales_liters": 700.0,
         "closing_stock_liters": 100.0, "quota_liters": 900},
        {"spbu_id": "S1", "region": "R", "verifikator_id": "V1", "product": "Premium",
         "date": "2026-01-02", "reported_sales_liters": np.nan,
         "closing_stock_liters": 100.0, "quota_liters": 900},
    ])
    daily = daily_spbu_table(clean)
    assert len(daily) == 1  # baris NaN penjualan dibuang
    assert daily.loc[0, "quota_utilization"] == pytest.approx(700 / 900)


def test_regional_summary_math():
    clean = pd.DataFrame([
        {"region": "R1", "product": "Premium", "spbu_id": "S1",
         "reported_sales_liters": 700.0, "quota_liters": 900},
        {"region": "R1", "product": "Premium", "spbu_id": "S2",
         "reported_sales_liters": 800.0, "quota_liters": 900},
    ])
    region = regional_summary(clean)
    assert len(region) == 1
    assert region.loc[0, "total_sales_liters"] == 1500.0
    assert region.loc[0, "utilization"] == pytest.approx(1500 / 1800, abs=0.01)  # dibulatkan 2 desimal di modul
    assert region.loc[0, "n_spbu"] == 2


def test_spbu_features_groups_by_spbu_product(small_clean):
    daily = daily_spbu_table(small_clean)
    feat = spbu_features(daily)
    assert len(feat) == small_clean.groupby(["spbu_id", "product"]).ngroups
    assert feat["n_days"].gt(0).all()
    assert feat["mean_utilization"].notna().all()
