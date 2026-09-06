"""
Grain assertions. The fact table carries no uprn column precisely so that a
left join cannot change its row count; these tests hold that design in place.
"""

from __future__ import annotations


def test_join_preserves_fact_table_row_count(silver_report):
    join = silver_report["grain_and_cardinality"]["join_preserves_fct_row_count"]
    assert join["before"] == join["after"] == 101_600
    assert join["passed"] is True


def test_transaction_id_is_unique(silver_report):
    grain = silver_report["grain_and_cardinality"]["fct_grain_unique_tuid"]
    assert grain["passed"] is True
    assert grain["rows"] == 101_600


def test_bridge_has_no_orphans(silver_report):
    """The look-up's universe is assumed to be this release."""
    integrity = silver_report["grain_and_cardinality"]["bridge_referential_integrity"]
    assert integrity["orphan_lookup_rows"] == 0


def test_cardinality_adds_up(silver_report):
    card = silver_report["grain_and_cardinality"]["cardinality_transaction_to_uprn"]
    assert card["zero_uprns"] + card["one_uprn"] + card["many_uprns"] == 101_600
    assert card["one_uprn"] == 94_112


def test_no_transaction_maps_to_several_uprns_in_this_release(silver_report):
    """
    The specification allows it and a later month may contain it. If that
    happens this test fails, which is the point: the bridge absorbs it, but
    every figure quoted in docs/ assumes it did not occur here.
    """
    card = silver_report["grain_and_cardinality"]["cardinality_transaction_to_uprn"]
    assert card["many_uprns"] == 0
    assert card["max_uprns_per_transaction"] == 1


def test_multiplicity_runs_the_other_way(silver_report):
    """1,055 UPRNs carry more than one sale — the real double-count hazard."""
    reverse = silver_report["grain_and_cardinality"]["cardinality_uprn_to_transaction"]
    assert reverse["uprns_with_multiple_transactions"] == 1_055
    assert reverse["max_transactions_per_uprn"] == 7
    assert reverse["distinct_uprns"] < reverse["distinct_uprns"] + reverse["uprns_with_multiple_transactions"]
