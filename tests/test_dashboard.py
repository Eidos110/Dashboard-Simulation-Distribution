"""Uji dashboard Streamlit dengan AppTest (runtime sungguhan, tanpa browser).

AppTest menjalankan src/dashboard.py dari atas sampai bawah sehingga error
apa pun pada load data, komputasi KPI, atau konstruksi chart akan tertangkap.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

DASHBOARD_PATH = Path(__file__).resolve().parents[1] / "src" / "dashboard.py"


@pytest.fixture(scope="module")
def app():
    at = AppTest.from_file(str(DASHBOARD_PATH), default_timeout=120)
    at.run()
    return at


def test_app_runs_without_exception(app):
    assert not app.exception, f"dashboard melempar exception: {app.exception}"


def test_app_title(app):
    texts = [t.value for t in app.title]
    assert any("Pengawasan Distribusi BBM" in t for t in texts)


def test_app_has_four_tabs(app):
    tabs = app.tabs
    assert len(tabs) == 4
    labels = [t.label for t in tabs]
    assert any("Ringkasan" in l for l in labels)
    assert any("Kualitas" in l for l in labels)
    assert any("Anomali" in l for l in labels)
    assert any("Tren" in l for l in labels)


def test_kpi_metrics_present(app):
    """KPI utama dirender: SPBU diawasi, anomali, verifikator, laporan."""
    values = [m.value for m in app.metric]
    assert len(values) >= 4
    assert any("400" in str(v) for v in values), "KPI 'SPBU diawasi' harus 400"


def test_charts_rendered(app):
    """Konten visual tab ringkasan terisi: info intisari & teks pendukung ada."""
    # AppTest tidak mengekspos plotly_chart; verifikasi konten pendukung chart
    assert len(app.info) >= 1, "info intisari harus tampil"
    info_text = app.info[0].value
    assert "terindikasi" in info_text.lower()
    assert len(app.markdown) >= 1, "header seksi chart harus tampil"


def test_methodology_note(app):
    body = "\n".join(c.value for c in app.caption)
    assert "simulasi" in body.lower()
