from fire_dna import build_fire_dna_profile


def rows(years=5, zero=False):
    return [
        {"year": year, "month": month, "days_in_record": 28, "harmonized_activity": 0 if zero else month * (1 + 0.1 * (year - 2020))}
        for year in range(2020, 2020 + years)
        for month in range(1, 13)
    ]


def profile(data):
    return build_fire_dna_profile(data, {}, {"start": "2020-01-01", "end": "2024-12-31"}, {"mean_sufficiency_score": 82, "pct_days_unobservable": 8, "method": "test"})


def test_monthly_median_and_peak_month():
    result = profile(rows())
    assert result["monthly_reference"][0]["median_activity"] == 1.2
    assert result["peak_month"] == "Dec"


def test_annual_aggregation_requires_all_months():
    data = rows()
    data = [row for row in data if not (row["year"] == 2022 and row["month"] == 4)]
    result = profile(data)
    assert result["annual"][2]["comparable"] is False
    assert result["annual"][2]["months"] == 11


def test_theil_sen_detects_consistent_increase():
    result = profile(rows())
    assert result["trend"]["direction"] == "Increasing"
    assert result["trend"]["slope_per_year"] > 0


def test_zero_activity_is_not_missing_and_is_stable():
    result = profile(rows(zero=True))
    assert result["typical_annual_activity"] == 0
    assert result["trend"]["direction"] == "Stable"
    assert result["peak_month"] == "Jan"


def test_insufficient_years_do_not_claim_trend():
    result = profile(rows(years=3))
    assert result["trend"]["direction"] == "Insufficient data"


def test_partial_month_excluded_from_reference():
    data = rows()
    data[0]["days_in_record"] = 5
    result = profile(data)
    assert result["monthly_reference"][0]["years"] == 4


def test_summary_is_deterministic_and_mentions_period():
    result = profile(rows())
    assert "Between 2020 and 2024" in result["summary"]
    assert "increasing" in result["summary"]
