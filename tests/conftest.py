"""Fixture bersama: dataset kecil untuk uji unit tanpa menjalankan pipeline penuh."""

import numpy as np
import pandas as pd
import pytest

from src import config


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(config.SEED)


@pytest.fixture
def small_raw(rng) -> pd.DataFrame:
    """Raw reports skala kecil (20 SPBU x 2 produk x 14 hari) untuk uji modul."""
    import src.generate_data as gen

    original = (config.N_SPBU, config.N_DAYS)
    config.N_SPBU, config.N_DAYS = 20, 14
    try:
        df = gen.generate_raw_reports(rng)
    finally:
        config.N_SPBU, config.N_DAYS = original
    return df


@pytest.fixture
def small_clean(small_raw) -> pd.DataFrame:
    """Hasil validasi dari raw kecil (tanpa menyentuh disk)."""
    import src.validate_data as val

    dup_mask = small_raw.duplicated(subset=val.KEY_COLS, keep="first")
    clean = small_raw.loc[~dup_mask].copy()
    clean["had_unit_issue"] = val.detect_unit_issue(clean)
    unit = clean["had_unit_issue"]
    clean.loc[unit, "reported_sales_liters"] = clean.loc[unit, "reported_sales_liters"] * 100
    stock_unit = unit & clean["closing_stock_liters"].notna()
    clean.loc[stock_unit, "closing_stock_liters"] = (
        clean.loc[stock_unit, "closing_stock_liters"] * 100)
    clean["quota_utilization"] = clean["reported_sales_liters"] / clean["quota_liters"]
    return clean
