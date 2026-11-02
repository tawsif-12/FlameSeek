"""Multi-year components on simulated data with known truth (Part 3)."""
import numpy as np
import pytest

from generate import circ_dist, simulate
from pipeline import anomalies, calendar
from forecast import climatology, evaluate, xgb


@pytest.fixture(scope="module")
def sim():
    return simulate()


def test_calendar_recovers_peak_week(cfg, sim):
    df, truth = sim
    cal = calendar.build_calendar(df, cfg)
    assert cal["status"] == "ok"
    found = cal["peak"].set_index("cell_id")["peak_week"]
    err = np.array([circ_dist(found[c], truth["peak_week"][c]) for c in found.index])
    assert (err <= 1).mean() >= 0.9, f"peak week errors: {sorted(err)}"
    assert np.median(err) <= 1
    # Onset (20% of the year's total) comes before the peak in most cell-years.
    on = cal["onset"].merge(cal["peak"], on="cell_id")
    before = circ_dist(on["onset_week"], on["peak_week"]) <= 10
    assert before.mean() > 0.9


def test_anomalies_found_with_few_false_alarms(cfg, sim):
    df, truth = sim
    res = anomalies.detect(df, cfg)
    assert res["status"] == "ok"
    t = res["table"].set_index(["cell_id", "year", "week"])
    for key in truth["anomalies"]:
        assert bool(t.loc[key, "anomaly_flag"]), f"planted anomaly {key} missed (z={t.loc[key, 'z_equiv']:.2f})"
    planted = set(truth["anomalies"])
    flags = t[t["anomaly_flag"]].index
    false = [k for k in flags if k not in planted]
    rate = len(false) / len(t)
    assert rate <= 0.02, f"false alarm rate {rate:.3%} ({len(false)} of {len(t)})"


def test_pettitt_detects_step_change(cfg, sim):
    df, truth = sim
    annual = df.groupby("year")["value"].sum()
    r = anomalies.pettitt(annual.to_numpy(), annual.index, cfg)
    assert r["status"] == "ok"
    assert abs(r["first_after_change"] - truth["step_year"]) <= 1
    # With n = 15 and the change after year 8, even a perfect split gives K = 8*7 = 56 and
    # p ≈ 2·exp(-6·56² / (15³ + 15²)) = 0.0107, so p < 0.01 is unreachable; 0.05 is the test level.
    assert r["p_value"] < 0.05
    ctrl, _ = simulate(step_factor=1.0, seed=11)
    a2 = ctrl.groupby("year")["value"].sum()
    assert anomalies.pettitt(a2.to_numpy(), a2.index, cfg)["p_value"] > 0.05


def test_climatology_forecast_has_skill(cfg, sim, tmp_path):
    df, _ = sim
    years = sorted(df["year"].unique())
    train, test = df[df["year"] <= years[-4]], df[df["year"] > years[-4]]
    model = climatology.fit(train, cfg)
    assert model["status"] == "ok"
    pred = climatology.predict(model, test)
    base_rate = (train["value"] > 0).mean()
    bss = evaluate.brier_skill(pred["p"], pred["y"], base_rate)
    assert 0 <= evaluate.brier(pred["p"], pred["y"]) <= 1
    assert bss > 0.1, f"BSS {bss:.3f}"
    rel = evaluate.reliability(pred["p"], pred["y"])
    assert rel["n"].sum() == len(pred)
    # Calibrated: in well-populated bins, observed frequency is close to the forecast.
    big = rel[rel["n"] >= 200]
    assert (np.abs(big["obs_freq"] - big["mean_p"]) < 0.15).all()
    evaluate.plot_reliability(rel, tmp_path / "rel.png")
    assert (tmp_path / "rel.png").exists()


def test_short_records_return_insufficient_history(cfg, sim):
    df, _ = sim
    one = df[df["year"] == df["year"].max()]
    assert calendar.build_calendar(one, cfg)["status"] == "insufficient_history"
    assert anomalies.detect(one, cfg)["status"] == "insufficient_history"
    assert climatology.fit(one, cfg)["status"] == "insufficient_history"
    assert anomalies.pettitt([1.0, 2.0, 3.0], [2024, 2025, 2026], cfg)["status"] == "insufficient_history"
    assert xgb.train(one, cfg, [2025])["status"] == "requires_multi_year_data"
