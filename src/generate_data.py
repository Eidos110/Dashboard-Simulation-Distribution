"""Generator data sintetis laporan inspeksi SPBU.

Meniru aliran kerja pengawasan distribusi BBM bersubsidi: verifikator lapangan
melaporkan penjualan harian per SPBU, lalu laporan dikumpulkan. Data yang
dihasilkan sengaja "kotor" (duplikat, kolom kosong, satuan campur, laporan
terlambat) dan ditanamkan pola penyimpangan berlabel sehingga lapisan validasi
dan analisis bisa dievaluasi terhadap ground truth.

Business logic digali dari pemberitaan publik BPH Migas/Pertamina (kuota
harian SPBU, kelompok Premium & Solar bersubsidi); angka adalah asumsi.
"""

import numpy as np
import pandas as pd

from src import config


def _build_spbu_master(rng: np.random.Generator) -> pd.DataFrame:
    """Master data SPBU: lokasi, kuota harian, verifikator pendamping."""
    region_names = list(config.REGIONS.keys())
    region_probs = list(config.REGIONS.values())

    spbu_ids = [f"SPBU-{i:04d}" for i in range(1, config.N_SPBU + 1)]
    regions = rng.choice(region_names, size=config.N_SPBU, p=region_probs)

    # Verifikator dibagi merata tapi tidak rapi: beberapa menangani lebih banyak SPBU
    verifikator_ids = rng.integers(1, config.N_VERIFICATORS + 1, size=config.N_SPBU)

    rows = []
    for sid, region, vid in zip(spbu_ids, regions, verifikator_ids):
        rows.append({
            "spbu_id": sid,
            "region": region,
            "verifikator_id": f"VER-{vid:03d}",
        })
    return pd.DataFrame(rows)


def _assign_anomalous_spbu(master: pd.DataFrame, rng: np.random.Generator) -> set:
    """Pilih SPBU yang akan disimulasikan berperilaku menyimpang (ground truth)."""
    n_anom = int(config.N_SPBU * config.ANOMALY["spbu_share"])
    idx = rng.choice(config.N_SPBU, size=n_anom, replace=False)
    return set(master.iloc[idx]["spbu_id"])


def _daily_sales(base_quota: float, is_anomalous: bool, rng: np.random.Generator) -> float:
    """Penjualan harian satu SPBU satu produk.

    Normal: sekitar 70-100% kuota dengan variasi mingguan.
    Anomali (underreporting): dilaporkan jauh di bawah kuota dan polanya flat.
    """
    if is_anomalous:
        factor = config.ANOMALY["underreporting_factor"]
        noise = rng.normal(0, 0.02)
        return max(0.0, base_quota * factor * (1 + noise))
    seasonal = 1 + 0.10 * np.sin(2 * np.pi * rng.integers(0, 7) / 7)
    factor = rng.uniform(0.70, 1.00) * seasonal
    noise = rng.normal(0, 0.05)
    return max(0.0, base_quota * factor * (1 + noise))


def generate_raw_reports(rng: np.random.Generator) -> pd.DataFrame:
    """Buat laporan harian per SPBU x produk x hari, lalu tanamkan noise."""
    dates = pd.date_range(config.START_DATE, periods=config.N_DAYS, freq="D")
    master = _build_spbu_master(rng)
    anomalous_ids = _assign_anomalous_spbu(master, rng)

    records = []
    for _, spbu in master.iterrows():
        is_anom = spbu["spbu_id"] in anomalous_ids
        for product, spec in config.PRODUCTS.items():
            quota = spec["daily_quota_liters"]
            for day in dates:
                sales = _daily_sales(quota, is_anom, rng)
                stock = rng.uniform(0.20, 1.00) * quota * 2
                if is_anom and config.ANOMALY["stock_claim_out"]:
                    # klaim stok habis meski penjualan rendah -> inkonsistensi
                    stock = rng.uniform(0.0, 0.05) * quota
                records.append({
                    "report_id": f"RPT-{len(records) + 1:07d}",
                    "spbu_id": spbu["spbu_id"],
                    "region": spbu["region"],
                    "verifikator_id": spbu["verifikator_id"],
                    "product": product,
                    "date": day,
                    "quota_liters": quota,
                    "reported_sales_liters": round(sales, 1),
                    "closing_stock_liters": round(stock, 1),
                    "is_anomalous_truth": is_anom,
                })

    df = pd.DataFrame(records)
    df = _inject_noise(df, rng)
    return df


def _inject_noise(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Tanamkan noise realistis tanpa merusak kolom identitas."""
    n = len(df)

    # 1) Kolom penting kosong (closing stock atau penjualan hilang)
    miss_mask = rng.random(n) < config.NOISE["missing_field_rate"]
    miss_col = rng.choice(["reported_sales_liters", "closing_stock_liters"], size=n)
    for col in ("reported_sales_liters", "closing_stock_liters"):
        df.loc[miss_mask & (miss_col == col), col] = np.nan

    # 2) Satuan tidak konsisten: sebagian laporan menulis nilai dalam hektoliter
    #    (mis. 800 liter tercatat "8.0") — inilah kesalahan yang harus dideteksi
    unit_mask = rng.random(n) < config.NOISE["unit_inconsistency"]
    for col in ("reported_sales_liters", "closing_stock_liters"):
        df.loc[unit_mask, col] = (df.loc[unit_mask, col] / 100.0).round(1)

    # 3) Laporan terlambat: timestamp pengiriman > tanggal laporan
    #    Keterlambatan 1-3 hari dengan distribusi seragam; ekspektasi rate = NOISE config.
    late_mask = rng.random(n) < config.NOISE["late_report_rate"]
    submit_offset = np.where(late_mask, rng.integers(1, 4, size=n), 0)
    df["submitted_date"] = df["date"] + pd.to_timedelta(submit_offset, unit="D")
    df["is_late"] = submit_offset > 0

    # 4) Laporan ganda: salin subset baris dengan report_id baru
    n_dup = int(n * config.NOISE["duplicate_rate"])
    dup_idx = rng.choice(n, size=n_dup, replace=False)
    dups = df.iloc[dup_idx].copy()
    dups["report_id"] = [f"RPT-D{i:07d}" for i in range(len(dups))]
    dups["is_duplicate_truth"] = True
    df["is_duplicate_truth"] = False
    df = pd.concat([df, dups], ignore_index=True)
    return df.sample(frac=1.0, random_state=42).reset_index(drop=True)


def main() -> None:
    rng = np.random.default_rng(config.SEED)
    df = generate_raw_reports(rng)

    config.DATA_RAW.mkdir(parents=True, exist_ok=True)
    out = config.DATA_RAW / "inspeksi_raw.csv"
    df.to_csv(out, index=False)

    print(f"Raw reports : {len(df):,} baris -> {out.relative_to(config.PROJECT_ROOT)}")
    print(f"SPBU        : {df['spbu_id'].nunique()} | verifikator: {df['verifikator_id'].nunique()}")
    print(f"Periode     : {df['date'].min().date()} s.d. {df['date'].max().date()}")
    print(f"Ground truth: {df.loc[df['is_anomalous_truth'], 'spbu_id'].nunique()} SPBU anomali, "
          f"{int(df['is_duplicate_truth'].sum()):,} baris duplikat")


if __name__ == "__main__":
    main()
