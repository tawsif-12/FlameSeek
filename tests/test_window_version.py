"""Each processing window reports its own data version."""
from pipeline.config import load_settings


def test_window_data_version_overrides_global_label():
    assert load_settings(window="sync_2016")["data_version"] == "firms_country_sp_2016_India_Bangladesh_v1"


def test_window_without_own_label_keeps_global_label():
    default = load_settings()
    assert load_settings(window="igp_2026")["data_version"] == default["data_version"]
    assert "2016" not in default["data_version"]
