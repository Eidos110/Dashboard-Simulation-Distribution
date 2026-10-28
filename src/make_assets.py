"""Buat gambar statis untuk README: tren harian, skor verifikator, dan anomali.

Output: assets/readme_trend.png, assets/readme_reliability.png, assets/readme_anomali.png
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import config

plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})


def main() -> None:
    clean = pd.read_csv(config.DATA_PROCESSED / "inspeksi_clean.csv", parse_dates=["date"])
    feat = pd.read_csv(config.DATA_PROCESSED / "anomali_spbu.csv")
    rel = pd.read_csv(config.DATA_PROCESSED / "kualitas_pelaporan.csv")

    config.ASSETS.mkdir(parents=True, exist_ok=True)

    # --- 1) Tren penjualan harian per produk dengan sorotan periode anomali ---
    trend = (clean.dropna(subset=["reported_sales_liters"])
             .groupby(["date", "product"], as_index=False)
             .agg(total_sales_liters=("reported_sales_liters", "sum")))
    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=150)
    for product, color in (("Premium", "#e05c3a"), ("Solar", "#2a6f97")):
        sub = trend[trend["product"] == product]
        ax.plot(sub["date"], sub["total_sales_liters"], label=product, color=color, lw=1.4)
    ax.set_title("Tren penjualan harian BBM bersubsidi (simulasi, liter/hari)")
    ax.set_ylabel("Liter/hari")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(config.ASSETS / "readme_trend.png")
    plt.close(fig)

    # --- 2) Distribusi skor reliabilitas verifikator ---
    fig, ax = plt.subplots(figsize=(8, 3.0), dpi=150)
    colors = np.where(rel["reliability_score"] < config.THRESHOLDS["verificator_reliability_min"],
                      "#e05c3a", "#2a6f97")
    ax.bar(rel["verifikator_id"], rel["reliability_score"], color=colors, width=0.8)
    ax.axhline(config.THRESHOLDS["verificator_reliability_min"], color="#e05c3a",
               ls="--", lw=1, label="ambang reliabilitas")
    ax.set_title("Skor reliabilitas 98 verifikator (kelengkapan + konsistensi + kewajaran)")
    ax.set_ylabel("Skor (0–1)")
    ax.set_ylim(0, 1.05)
    ax.set_xticks([])
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(config.ASSETS / "readme_reliability.png")
    plt.close(fig)

    # --- 3) Utilitas kuota vs volatilitas dengan sorot anomali ---
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=150)
    normal = feat[~feat["indicated_anomaly"]]
    anom = feat[feat["indicated_anomaly"]]
    ax.scatter(normal["mean_utilization"], normal["sales_cv"], s=8, alpha=0.45,
               color="#8fa8bf", label="normal")
    ax.scatter(anom["mean_utilization"], anom["sales_cv"], s=14, alpha=0.85,
               color="#e05c3a", label="terindikasi anomali")
    ax.axvline(config.THRESHOLDS["quota_util_min"], color="#e05c3a", ls="--", lw=1)
    ax.axhline(config.THRESHOLDS["flat_cv"], color="#e0a13a", ls="--", lw=1)
    ax.set_title(f"Deteksi anomali: {int(anom['spbu_id'].nunique())} SPBU terindikasi "
                 "penyimpangan (simulasi)")
    ax.set_xlabel("Rata-rata utilitas kuota")
    ax.set_ylabel("Volatilitas penjualan (CV)")
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:.0%}")
    ax.yaxis.set_major_formatter(lambda y, _: f"{y:.0%}")
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(config.ASSETS / "readme_anomali.png")
    plt.close(fig)

    for name in ("readme_trend.png", "readme_reliability.png", "readme_anomali.png"):
        print("OK ->", (config.ASSETS / name).relative_to(config.PROJECT_ROOT))


if __name__ == "__main__":
    main()
