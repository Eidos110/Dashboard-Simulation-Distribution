"""Lapisan analisis: capaian distribusi, deteksi anomali, dan evaluasi deteksi.

Aturan deteksi (rule-based, audit-friendly):
  A. Utilitas kuota < ambang bawah  -> terindikasi underreporting
  B. Utilitas kuota > ambang atas   -> penjualan melebihi kuota (pelanggaran)
  C. Pola penjualan flat (CV < ambang) -> tidak wajar secara statistik
  D. Isolation Forest (scikit-learn) sebagai pembanding multivariat

Output:
  1. data/processed/anomali_spbu.csv        - skor & label per SPBU
  2. data/processed/distribusi_wilayah.csv  - capaian per wilayah x produk
  3. data/processed/tren_harian.csv         - tren penjualan harian per produk
  4. data/processed/evaluasi_deteksi.json   - presisi/recall vs ground truth
"""

import json

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from src import config


def daily_spbu_table(clean: pd.DataFrame) -> pd.DataFrame:
    """Agregasi harian per SPBU x produk dengan fitur untuk deteksi anomali."""
    g = (clean.dropna(subset=["reported_sales_liters"])
         .groupby(["spbu_id", "region", "verifikator_id", "product", "date"],
                  as_index=False)
         .agg(reported_sales_liters=("reported_sales_liters", "sum"),
              closing_stock_liters=("closing_stock_liters", "mean"),
              quota_liters=("quota_liters", "first")))
    g["quota_utilization"] = g["reported_sales_liters"] / g["quota_liters"]
    return g


def spbu_features(daily: pd.DataFrame) -> pd.DataFrame:
    """Fitur tingkat SPBU: rata-rata utilitas, volatilitas, konsistensi stok."""
    def _agg(sub: pd.DataFrame) -> pd.Series:
        cv = (sub["reported_sales_liters"].std() / sub["reported_sales_liters"].mean()
              if sub["reported_sales_liters"].mean() else np.nan)
        return pd.Series({
            "region": sub["region"].iloc[0],
            "n_days": len(sub),
            "mean_sales_liters": sub["reported_sales_liters"].mean(),
            "quota_liters": sub["quota_liters"].iloc[0],
            "mean_utilization": sub["quota_utilization"].mean(),
            "sales_cv": cv,
            "stock_out_rate": (sub["closing_stock_liters"]
                               < sub["quota_liters"] * 0.05).mean(),
        })

    feats = (daily.groupby(["spbu_id", "product"])
             .apply(_agg, include_groups=False)
             .reset_index())
    return feats


def rule_based_flags(feat: pd.DataFrame) -> pd.DataFrame:
    """Terapkan aturan ambang batas dari config ke fitur SPBU."""
    t = config.THRESHOLDS
    out = feat.copy()
    out["flag_underreporting"] = out["mean_utilization"] < t["quota_util_min"]
    out["flag_over_quota"] = out["mean_utilization"] > t["quota_util_max"]
    out["flag_flat_pattern"] = out["sales_cv"].fillna(1.0) < t["flat_cv"]
    out["flag_stock_out"] = out["stock_out_rate"] > 0.5

    out["anomaly_score"] = (out[["flag_underreporting", "flag_over_quota",
                                 "flag_flat_pattern", "flag_stock_out"]]
                            .sum(axis=1))
    out["indicated_anomaly"] = out["anomaly_score"] >= 2
    return out


def isolation_forest_flags(feat: pd.DataFrame) -> pd.DataFrame:
    """Pembanding multivariat: Isolation Forest pada fitur perilaku SPBU."""
    cols = ["mean_utilization", "sales_cv", "stock_out_rate"]
    x = feat[cols].fillna(feat[cols].median()).to_numpy()
    model = IsolationForest(n_estimators=200, contamination=config.ANOMALY["spbu_share"],
                            random_state=config.SEED)
    labels = model.fit_predict(x)  # -1 = anomali
    scores = -model.score_samples(x)  # makin besar makin anomali
    out = feat.copy()
    out["iforest_anomaly"] = labels == -1
    out["iforest_score"] = np.round(scores, 4)
    return out


def evaluate_detection(feat: pd.DataFrame) -> dict:
    """Presisi & recall deteksi vs ground truth simulasi.

    Ground truth didefinisikan pada tingkat SPBU; evaluasi diambil per pasangan
    SPBU x produk karena aturan bekerja per produk.
    """
    truth_by_spbu = (feat.groupby("spbu_id")["is_anomalous_truth"].first())
    results = {}
    for method, col in (("rule_based", "indicated_anomaly"),
                        ("isolation_forest", "iforest_anomaly")):
        pred_by_spbu = feat.groupby("spbu_id")[col].mean() >= 0.5
        joined = pd.DataFrame({"truth": truth_by_spbu, "pred": pred_by_spbu}).dropna()
        tp = int(((joined["truth"]) & (joined["pred"])).sum())
        fp = int((~joined["truth"] & joined["pred"]).sum())
        fn = int((joined["truth"] & ~joined["pred"]).sum())
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        results[method] = {"true_positive": tp, "false_positive": fp,
                           "false_negative": fn, "precision": round(precision, 4),
                           "recall": round(recall, 4), "f1": round(f1, 4)}
    return results


def regional_summary(clean: pd.DataFrame) -> pd.DataFrame:
    """Capaian distribusi per wilayah x produk: volume, utilitas, SPBU terindikasi."""
    g = (clean.dropna(subset=["reported_sales_liters"])
         .groupby(["region", "product"], as_index=False)
         .agg(total_sales_liters=("reported_sales_liters", "sum"),
              total_quota_liters=("quota_liters", "sum"),
              n_spbu=("spbu_id", "nunique")))
    g["utilization"] = g["total_sales_liters"] / g["total_quota_liters"]
    return g.round(2)


def daily_trend(clean: pd.DataFrame) -> pd.DataFrame:
    """Tren penjualan harian nasional per produk."""
    g = (clean.dropna(subset=["reported_sales_liters"])
         .groupby(["date", "product"], as_index=False)
         .agg(total_sales_liters=("reported_sales_liters", "sum")))
    return g


def main() -> None:
    clean = pd.read_csv(config.DATA_PROCESSED / "inspeksi_clean.csv",
                        parse_dates=["date", "submitted_date"])

    daily = daily_spbu_table(clean)
    feat = spbu_features(daily)

    # ground truth tingkat SPBU diproyeksikan ke pasangan SPBU x produk
    truth = clean.groupby("spbu_id")["is_anomalous_truth"].first()
    feat["is_anomalous_truth"] = feat["spbu_id"].map(truth).astype(bool)

    feat = rule_based_flags(feat)
    feat = isolation_forest_flags(feat)

    feat_path = config.DATA_PROCESSED / "anomali_spbu.csv"
    feat.to_csv(feat_path, index=False)

    region = regional_summary(clean)
    region_path = config.DATA_PROCESSED / "distribusi_wilayah.csv"
    region.to_csv(region_path, index=False)

    trend = daily_trend(clean)
    trend_path = config.DATA_PROCESSED / "tren_harian.csv"
    trend.to_csv(trend_path, index=False)

    evaluation = evaluate_detection(feat)
    evaluation["n_spbu_truth_anomalous"] = int(truth.sum())
    eval_path = config.DATA_PROCESSED / "evaluasi_deteksi.json"
    eval_path.write_text(json.dumps(evaluation, indent=2), encoding="utf-8")

    t = config.THRESHOLDS
    print(f"SPBU x produk : {len(feat)} baris fitur")
    print(f"Rule-based    : {int(feat['indicated_anomaly'].sum())} terindikasi anomali "
          f"(underreporting {int(feat['flag_underreporting'].sum())}, "
          f"flat {int(feat['flag_flat_pattern'].sum())}, "
          f"over-quota {int(feat['flag_over_quota'].sum())})")
    print(f"IsolationForest: {int(feat['iforest_anomaly'].sum())} anomali")
    for method, m in evaluation.items():
        if isinstance(m, dict):
            print(f"  {method:17s}: presisi {m['precision']:.2f} | recall {m['recall']:.2f} | F1 {m['f1']:.2f}")
    print(f"Output        -> {feat_path.relative_to(config.PROJECT_ROOT)}, "
          f"{region_path.relative_to(config.PROJECT_ROOT)}, "
          f"{trend_path.relative_to(config.PROJECT_ROOT)}, {eval_path.relative_to(config.PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
