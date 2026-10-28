"""Konfigurasi terpusat untuk proyek Dashboard Simulasi Pengawasan Distribusi BBM Bersubsidi.

Semua asumsi bisnis dikumpulkan di sini agar mudah diaudit dan diubah:
proyek ini meniru pekerjaan Analis Pengawal Energi (BPH Migas) dengan data
sintetis, sehingga setiap parameter simulasi harus eksplisit dan terdokumentasi.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
REPORTS = PROJECT_ROOT / "reports"
ASSETS = PROJECT_ROOT / "assets"

# ---------------------------------------------------------------------------
# Simulasi lapangan
# ---------------------------------------------------------------------------
SEED = 2026
N_VERIFICATORS = 100          # verifikator lapangan (meniru skema pengawasan BPH Migas)
N_SPBU = 400                  # SPBU yang diawasi
N_DAYS = 90                   # periode pelaporan (hari kalender)
START_DATE = "2026-07-01"     # awal periode simulasi
REGIONS = {
    "Jawa Tengah": 0.35,
    "Jawa Timur": 0.30,
    "DI Yogyakarta": 0.15,
    "Jawa Barat": 0.20,
}

# Produk BBM bersubsidi yang diawasi (sesuai kelompok BBM bersubsidi BPH Migas)
PRODUCTS = {
    "Premium": {"daily_quota_liters": 900, "price_per_liter": 10_000},
    "Solar": {"daily_quota_liters": 1500, "price_per_liter": 6_800},
}

# ---------------------------------------------------------------------------
# Jenis "noise" yang ditanamkan untuk meniru kondisi data lapangan nyata
# ---------------------------------------------------------------------------
NOISE = {
    "duplicate_rate": 0.03,        # laporan ganda (double submit)
    "missing_field_rate": 0.05,    # kolom penting kosong
    "late_report_rate": 0.08,      # laporan terlambat dari jadwal harian
    "unit_inconsistency": 0.02,    # satuan tidak konsisten (hektoliter vs liter)
}

# ---------------------------------------------------------------------------
# Pola penyimpangan yang disimulasikan (ground truth untuk evaluasi deteksi)
# ---------------------------------------------------------------------------
ANOMALY = {
    "spbu_share": 0.08,            # porsi SPBU yang "diarahkan" berperilaku menyimpang
    "underreporting_factor": 0.35, # penjualan dilaporkan jauh di bawah kuota
    "flat_pattern": True,          # penjualan flat tidak wajar (variasi ~0)
    "stock_claim_out": True,       # klaim stok habis padahal penjualan rendah
}

# ---------------------------------------------------------------------------
# Ambang batas analisis (rule-based, mudah diaudit)
# ---------------------------------------------------------------------------
THRESHOLDS = {
    "quota_util_min": 0.60,        # utilitas kuota < 60% -> terindikasi underreporting
    "quota_util_max": 1.10,        # utilitas kuota > 110% -> melebihi kuota (pelanggaran)
    "flat_cv": 0.05,               # coefficient of variation penjualan < 5% -> pola flat
    "completeness_score_min": 0.80,  # skor kelengkapan laporan minimum
    "verificator_reliability_min": 0.70,  # skor reliabilitas verifikator minimum
}
