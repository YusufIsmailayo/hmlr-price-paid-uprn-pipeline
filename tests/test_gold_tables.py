"""
Internal consistency of the Gold tables, and the specific findings docs/ quotes.

The invariant tests sweep every breakdown table, so a new cut added later is
covered without anyone remembering to write a test for it.
"""

from __future__ import annotations

import pytest

from conftest import BREAKDOWN_TABLES


@pytest.mark.parametrize("table", BREAKDOWN_TABLES)
def test_matched_and_unmatched_sum_to_the_denominator(gold, table):
    df = gold[table]
    assert (df["matched"] + df["unmatched"] == df["transactions"]).all()


@pytest.mark.parametrize("table", BREAKDOWN_TABLES)
def test_percentages_agree_with_the_counts(gold, table):
    df = gold[table]
    recomputed = (100 * df["unmatched"] / df["transactions"]).round(2)
    assert (recomputed - df["unmatched_pct"]).abs().max() < 0.01


@pytest.mark.parametrize("table", BREAKDOWN_TABLES)
def test_wilson_intervals_bracket_their_point_estimate(gold, table):
    df = gold[table]
    assert (df["unmatched_ci_low_pct"] <= df["unmatched_pct"]).all()
    assert (df["unmatched_pct"] <= df["unmatched_ci_high_pct"]).all()
    assert (df["unmatched_ci_low_pct"] >= 0).all()
    assert (df["unmatched_ci_high_pct"] <= 100).all()


def test_headline_scopes_differ_only_by_the_deletions(gold):
    headline = gold["01_match_rate_headline"].set_index("scope")
    everything = headline.loc["All rows in the monthly release"]
    analysis = headline.loc["Analysis scope (deletions excluded)"]
    assert everything["transactions"] - analysis["transactions"] == 1_514
    # Deletions are unmatched by construction, so matched is untouched.
    assert everything["matched"] == analysis["matched"] == 94_112
    assert analysis["unmatched_pct"] < everything["unmatched_pct"]


def test_property_type_is_the_dominant_axis(gold, gold_summary):
    df = gold["03_unmatched_by_property_type"].set_index("property_type")
    assert df.loc["O", "unmatched_pct"] > 40
    assert df.loc["S", "unmatched_pct"] < 2
    assert df.loc["O", "unmatched_pct"] > 10 * df.loc["S", "unmatched_pct"]
    cramers = {t["variable"]: t["cramers_v"] for t in gold_summary["independence"]}
    assert cramers["property_type"] > cramers["ppd_category_type"] > cramers["old_new"]


def test_the_new_build_flag_is_negligible_on_its_own(gold_summary):
    """§3 of the findings. If this ever stops being true the article is wrong."""
    cramers = {t["variable"]: t["cramers_v"] for t in gold_summary["independence"]}
    assert cramers["old_new"] < 0.05
    crude = gold_summary["new_build_effect"]["crude"]
    assert 1.0 < crude["crude_risk_ratio"] < 1.3


def test_the_strata_may_not_be_pooled(gold_summary):
    """
    §4. The Mantel-Haenszel figure is computed and stored, but Cochran's Q
    rejects homogeneity, so nothing may quote it as 'the' new-build effect.
    """
    adjusted = gold_summary["new_build_effect"]["adjusted_for_property_type"]
    het = adjusted["heterogeneity"]
    assert het["pooling_appropriate"] is False
    assert het["p_value"] < 0.001
    assert het["stratum_risk_ratio_min"] < 1 < het["stratum_risk_ratio_max"], (
        "the effect reverses direction between strata; that reversal is the finding"
    )


def test_property_type_o_sits_wholly_inside_ppd_category_b(context_summary):
    """
    §5's correction. O and category B are not independent predictors. If a
    category A 'Other' row ever appears, the correction has to be revisited.
    """
    correction = context_summary["ppd_category_correction"]
    assert correction["other_rows_in_category_a"] == 0
    assert (correction["category_b_net_of_other_unmatched_pct"]
            < correction["category_b_unmatched_pct"] / 2)


def test_unmatched_sales_skew_expensive(context_summary):
    """§7. The counter-intuitive result, guarded."""
    price = context_summary["price"]
    assert price["median_unmatched_gbp"] > price["median_matched_gbp"]
    assert price["unmatched_share_of_value_pct"] > price["unmatched_share_of_transactions_pct"]


def test_geography_collapses_once_property_type_is_held_constant(context_summary):
    """§7. The null result — the county spread is composition, not geography."""
    geo = context_summary["geography"]
    all_spread = geo["all_property_max_pct"] - geo["all_property_min_pct"]
    house_spread = geo["houses_only_max_pct"] - geo["houses_only_min_pct"]
    assert house_spread < all_spread / 4


def test_repeated_uprns_are_one_address_not_several(context_summary, gold):
    """
    §7. If a repeated UPRN ever carries more than one PAON or SAON, it really
    is several dwellings and the section needs rewriting.
    """
    df = gold["13_repeat_uprn_consistency"].set_index("measure")
    assert df.loc["More than one PAON", "uprns"] == 0
    assert df.loc["More than one SAON", "uprns"] == 0
    assert df.loc["More than one property type", "uprns"] > 0
    assert context_summary["repeated_uprns"]["max_span_years"] > 20


def test_type_conflicts_are_split_from_the_other_bucket(context_summary, gold):
    """
    §7's headline. "Other" is the residual bucket, not a dwelling type, so a
    plot recorded as O and the house later built on it recorded as D are two
    correct records. Only conflicts between two genuine dwelling types are
    unarguable, and the write-up must lead on that smaller number.
    """
    conflicts = context_summary["repeated_uprns"]["type_conflicts"]
    assert conflicts["uprns_dwelling_type_conflict"] < conflicts["uprns_any_type_conflict"]
    assert (conflicts["uprns_conflict_involving_other"]
            + conflicts["uprns_dwelling_type_conflict"]
            == conflicts["uprns_any_type_conflict"])
    pairs = gold["14_repeat_uprn_dwelling_type_conflicts"]
    assert not pairs["involves_other"].any()
    assert pairs["uprns"].sum() == conflicts["uprns_dwelling_type_conflict"]
    assert not pairs["property_type_pair"].str.contains("O").any()


def test_the_detached_land_ordering_cannot_be_resolved(context_summary):
    """
    A tempting reading is that the D/O pairs are land sold first, then the house
    built on it. Transfer-date order does not support that claim: many of those
    UPRNs share a date, so the sequence is not well defined and the article must
    not assert a direction.
    """
    conflicts = context_summary["repeated_uprns"]["type_conflicts"]
    assert conflicts["d_o_pairs_with_tied_transfer_dates"] > 0
