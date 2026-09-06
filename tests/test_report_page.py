"""
The figures page is generated from the Gold tables and never hand-edited. These
tests guard that contract from the output side.
"""

from __future__ import annotations

import json
import re

import pytest

from conftest import GOLD_DIR


def test_no_unsubstituted_template_tokens(figures_html):
    """A leftover {{TOKEN}} in published prose is the failure this prevents."""
    assert not re.findall(r"\{\{[A-Z_]+\}\}", figures_html)


def test_page_quotes_the_headline_figures(figures_html, gold_summary):
    assert f"{gold_summary['unmatched_pct']:.2f}%" in figures_html
    assert f"{gold_summary['analysis_rows']:,}" in figures_html


def test_page_states_the_gate_result(figures_html, silver_report):
    assert f"{silver_report['validation_gate']['actual']:,}" in figures_html


def test_every_cited_gold_table_exists(figures_html):
    """The page footnotes each figure with its source file; they must be real."""
    cited = set(re.findall(r"gold/(\d\d_[a-z_]+)\.csv", figures_html))
    assert cited, "no gold tables cited on the page"
    for name in cited:
        assert (GOLD_DIR / f"{name}.csv").exists(), name


def test_embedded_chart_data_matches_the_gold_table(figures_html, gold):
    """
    The charts are drawn from JSON embedded at build time. If that JSON ever
    drifts from data/gold, the page is lying and the tables are not.
    """
    match = re.search(r"var DATA = (\{.*?\});", figures_html, re.S)
    assert match, "could not find the embedded chart data"
    data = json.loads(match.group(1))
    published = {row["label"]: row["pct"] for row in data["fig1"]}
    for _, row in gold["03_unmatched_by_property_type"].iterrows():
        label = row["label"].replace(" / non-residential", "")
        assert published[label] == pytest.approx(row["unmatched_pct"], abs=0.01)
