"""Uji integrasi pipeline: generate -> validate -> analyze -> report pada skala kecil.

Pipeline dijalankan penuh di tmp_path (data kecil) untuk memverifikasi kontrak
antar-modul dan artefak output, tanpa mengganggu data/ di repo.
"""

import json

import pandas as pd

from src import config


def _run_pipeline_small(tmp_path, monkeypatch):
    """Jalankan 4 modul pipeline dengan dataset kecil & path terisolasi."""
    import numpy as np
    import src.generate_data as gen
    import src.validate_data as val
    import src.analyze as ana
    import src.report as rep

    # path terisolasi — semua modul membaca config.DATA_*/PROJECT_ROOT saat runtime,
    # jadi patch hanya pada objek config.
    monkeypatch.setattr(config, "DATA_RAW", tmp_path / "raw")
    monkeypatch.setattr(config, "DATA_PROCESSED", tmp_path / "processed")
    monkeypatch.setattr(config, "REPORTS", tmp_path / "reports")
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)

    original = (config.N_SPBU, config.N_DAYS, config.N_VERIFICATORS)
    config.N_SPBU, config.N_DAYS, config.N_VERIFICATORS = 30, 20, 10
    try:
        df = gen.generate_raw_reports(np.random.default_rng(config.SEED))
        config.DATA_RAW.mkdir(parents=True, exist_ok=True)
        df.to_csv(config.DATA_RAW / "inspeksi_raw.csv", index=False)

        val.main()
        ana.main()
        rep.main()
    finally:
        config.N_SPBU, config.N_DAYS, config.N_VERIFICATORS = original


def test_pipeline_produces_all_artifacts(tmp_path, monkeypatch):
    _run_pipeline_small(tmp_path, monkeypatch)
    for rel in ("processed/inspeksi_clean.csv", "processed/kualitas_pelaporan.csv",
                "processed/validasi_ringkasan.json", "processed/anomali_spbu.csv",
                "processed/distribusi_wilayah.csv", "processed/tren_harian.csv",
                "processed/evaluasi_deteksi.json"):
        assert (tmp_path / rel).exists(), f"artefak hilang: {rel}"
    assert (tmp_path / "reports/laporan_eksekutif.md").exists()
    assert (tmp_path / "reports/laporan_eksekutif.pdf").exists()


def test_pipeline_clean_smaller_than_raw(tmp_path, monkeypatch):
    _run_pipeline_small(tmp_path, monkeypatch)
    summary = json.loads((tmp_path / "processed/validasi_ringkasan.json").read_text(encoding="utf-8"))
    assert summary["n_clean"] < summary["n_raw"]
    assert summary["n_duplicates_removed"] > 0


def test_pipeline_report_contains_key_numbers(tmp_path, monkeypatch):
    _run_pipeline_small(tmp_path, monkeypatch)
    md = (tmp_path / "reports/laporan_eksekutif.md").read_text(encoding="utf-8")
    assert "Ringkasan Eksekutif" in md
    assert "SPBU" in md and "rekomendasi" in md.lower()
    # intisari anomali tercantum dan konsisten dengan evaluasi
    evaluasi = json.loads((tmp_path / "processed/evaluasi_deteksi.json").read_text(encoding="utf-8"))
    assert "rule_based" in evaluasi and "isolation_forest" in evaluasi


def test_pipeline_anomaly_features_contract(tmp_path, monkeypatch):
    _run_pipeline_small(tmp_path, monkeypatch)
    feat = pd.read_csv(tmp_path / "processed/anomali_spbu.csv")
    required = {"spbu_id", "region", "product", "mean_utilization", "sales_cv",
                "stock_out_rate", "indicated_anomaly", "is_anomalous_truth"}
    assert required.issubset(feat.columns)
    # konsistensi label: kolom truth boolean, indikasi >= 2 aturan
    assert feat["is_anomalous_truth"].isin([True, False]).all()
    assert (feat.loc[feat["indicated_anomaly"], "anomaly_score"] >= 2).all()
