"""
The gate is the claim the whole repository rests on: that my extraction
reproduces a transaction count HM Land Registry publish through a separate
channel. These tests fail if that stops being true, or if the evidence for it
is quietly weakened.
"""

from __future__ import annotations


def test_gate_passed(silver_report):
    assert silver_report["validation_gate"]["passed"] is True


def test_gate_reproduces_hmlr_count_exactly(silver_report):
    gate = silver_report["validation_gate"]
    assert gate["actual"] == gate["expected"] == 22_835
    assert gate["reconciliation_month"] == "2026-07"


def test_gate_reconciles_against_a_second_channel(silver_report):
    """A gate that reconciles against my own files would be a tautology."""
    assert "landregistry.data.gov.uk" in silver_report["validation_gate"]["endpoint"]


def test_control_months_diverge_as_a_delta_file_must(silver_report):
    """
    If every month matched, the July match would be measuring something other
    than what I claim. The controls have to disagree, and by a positive volume.
    """
    controls = silver_report["validation_gate"]["controls"]
    assert len(controls) >= 3
    for control in controls:
        assert control["published_in_earlier_releases"] > 0, control["transfer_month"]
        assert control["in_this_release"] < control["hmlr_linked_data_total"]


def test_bronze_manifest_records_provenance(bronze_manifest):
    """The payloads cannot be re-downloaded; the manifest is the only record."""
    assert bronze_manifest["licence"] == "Open Government Licence v3.0"
    assert len(bronze_manifest["files"]) == 2
    for entry in bronze_manifest["files"]:
        assert len(entry["sha256"]) == 64
        assert entry["http_last_modified"]
        assert entry["size_bytes"] > 0
