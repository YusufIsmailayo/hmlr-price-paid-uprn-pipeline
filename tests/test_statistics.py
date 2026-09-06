"""
Unit tests for the two statistical helpers.

Everything downstream is a percentage with an interval attached, so if these
are wrong the tables are wrong in a way no consistency check would catch.
Values are checked against hand-worked cases rather than against the code's
own output.
"""

from __future__ import annotations

import math

import pytest

from conftest import load_pipeline_module

gold_cuts = load_pipeline_module("04_gold_cuts.py")


def test_wilson_is_symmetric_about_a_half():
    lo, hi = gold_cuts.wilson(50, 100)
    assert lo == pytest.approx(1 - hi, abs=1e-12)
    assert lo == pytest.approx(0.4038, abs=1e-4)


def test_wilson_stays_inside_the_unit_interval_at_zero():
    """
    The reason I use Wilson rather than Wald. At k=0 a Wald interval is
    [0, 0]; Wilson still reports the uncertainty, and never goes negative.
    """
    lo, hi = gold_cuts.wilson(0, 30)
    assert lo == 0.0
    assert 0 < hi < 1


def test_wilson_narrows_as_the_sample_grows():
    small = gold_cuts.wilson(15, 30)
    large = gold_cuts.wilson(1500, 3000)
    assert (large[1] - large[0]) < (small[1] - small[0])


def test_wilson_on_an_empty_group_is_not_a_number():
    lo, hi = gold_cuts.wilson(0, 0)
    assert math.isnan(lo) and math.isnan(hi)


def test_risk_ratio_of_identical_risks_is_one():
    rr, lo, hi = gold_cuts.risk_ratio(10, 100, 20, 200)
    assert rr == pytest.approx(1.0)
    assert lo < 1 < hi


def test_risk_ratio_matches_a_hand_worked_case():
    # 20% against 5% is fourfold.
    rr, lo, hi = gold_cuts.risk_ratio(20, 100, 5, 100)
    assert rr == pytest.approx(4.0)
    assert lo < rr < hi


def test_risk_ratio_interval_is_symmetric_on_the_log_scale():
    rr, lo, hi = gold_cuts.risk_ratio(40, 200, 10, 200)
    assert math.log(rr) - math.log(lo) == pytest.approx(math.log(hi) - math.log(rr))


def test_risk_ratio_refuses_a_zero_cell():
    """No unmatched rows in a group means no log, and no interval."""
    assert all(math.isnan(v) for v in gold_cuts.risk_ratio(0, 100, 5, 100))


def test_published_property_type_risk_ratios_recompute_from_the_counts(gold):
    """
    The bridge between the unit tests and the tables: recompute each published
    risk ratio from the raw counts in the same CSV and check it agrees.
    """
    df = gold["03_unmatched_by_property_type"]
    total_n = int(df["transactions"].sum())
    total_unmatched = int(df["unmatched"].sum())
    for _, row in df.iterrows():
        rr, _, _ = gold_cuts.risk_ratio(
            int(row["unmatched"]), int(row["transactions"]),
            total_unmatched - int(row["unmatched"]), total_n - int(row["transactions"]),
        )
        assert round(rr, 2) == pytest.approx(row["risk_ratio_vs_rest"], abs=0.01)
