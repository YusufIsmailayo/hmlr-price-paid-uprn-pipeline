"""
Silver: type the Bronze CSVs, join the UPRN look-up, assert the grain, and
run the validation gate.

Two tables come out, and the split is the whole point:

  fct_transaction        one row per transaction unique identifier. Carries
                         uprn_count and is_matched, but NOT a uprn column.
  bridge_transaction_uprn  one row per (transaction, UPRN) pair.

HMLR's specification allows one sale to link to several UPRNs, "because a sale
can cover more than one addressable location". Putting a uprn column on the
fact table would therefore silently change its row count the first month that
happens. Multiplicity lives in the bridge; the fact table stays at transaction
grain permanently. The assertions below check both directions so the test
still fires in a later month even though this one contains no such case.

Deletions (record status D) are kept, not dropped. They are flagged with
is_analysis_row = False so the choice is explicit and auditable in one place.
They are unmatched by construction — the look-up covers live records only — so
leaving them in an analysis denominator overstates the unmatched rate.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_SLUG = "release_2026-08-28"
BRONZE_DIR = REPO_ROOT / "data" / "bronze" / RELEASE_SLUG
SILVER_DIR = REPO_ROOT / "data" / "silver" / RELEASE_SLUG

PPD_FILE = "pp-monthly-update-new-version.csv"
LOOKUP_FILE = "pp-uprn-lookup-jul-2026.csv"

# Field order from the HMLR specification; neither file ships a header row.
PPD_COLUMNS = [
    "tuid", "price", "date_of_transfer", "postcode", "property_type",
    "old_new", "duration", "paon", "saon", "street", "locality",
    "town_city", "district", "county", "ppd_category_type", "record_status",
]
LOOKUP_COLUMNS = ["tuid", "uprn"]

# Domains that the analysis depends on. An unexpected value here would change
# what the Gold breakdowns mean, so it stops the pipeline rather than being
# quietly carried through.
ENFORCED_DOMAINS = {
    "property_type": {"D", "S", "T", "F", "O"},
    "old_new": {"Y", "N"},
    "ppd_category_type": {"A", "B"},
    "record_status": {"A", "C", "D"},
}
# Recorded but not enforced — not used in any breakdown.
OBSERVED_DOMAINS = ["duration"]


class ValidationError(AssertionError):
    """A gate failed. Silver does not produce output when this is raised."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_bronze() -> dict:
    """Refuse to build Silver on a Bronze that has drifted from its manifest."""
    metadata = json.loads((BRONZE_DIR / "metadata.json").read_text())
    checked = []
    for entry in metadata["files"]:
        path = BRONZE_DIR / entry["filename"]
        actual = _sha256(path)
        if actual != entry["sha256"]:
            raise ValidationError(
                f"{entry['filename']}: sha256 {actual} does not match the "
                f"Bronze manifest ({entry['sha256']}). Bronze has been "
                f"modified since ingest; re-run 01 with --force."
            )
        checked.append({"filename": entry["filename"], "sha256": actual})
        print(f"[bronze]   {entry['filename']} checksum ok")
    return {"release_slug": RELEASE_SLUG, "files": checked}


def load_ppd() -> pd.DataFrame:
    df = pd.read_csv(
        BRONZE_DIR / PPD_FILE, header=None, names=PPD_COLUMNS,
        dtype=str, keep_default_na=False,
    )
    df["price"] = df["price"].astype("int64")
    df["transfer_date"] = pd.to_datetime(df["date_of_transfer"], format="%Y-%m-%d %H:%M")
    df["transfer_month"] = df["transfer_date"].dt.strftime("%Y-%m")
    df = df.drop(columns=["date_of_transfer"])

    # Blank postcode is a real, meaningful value here (the spec names missing
    # address detail as a non-match reason), so it is flagged, not imputed.
    df["has_postcode"] = df["postcode"].str.len() > 0
    df["is_analysis_row"] = df["record_status"] != "D"

    for column, expected in ENFORCED_DOMAINS.items():
        unexpected = set(df[column].unique()) - expected
        if unexpected:
            raise ValidationError(
                f"{column}: unexpected value(s) {sorted(unexpected)} not in "
                f"{sorted(expected)}. The Gold breakdowns assume this domain."
            )
    print(f"[load]     {PPD_FILE}: {len(df):,} rows, domains ok")
    return df


def load_lookup() -> pd.DataFrame:
    df = pd.read_csv(
        BRONZE_DIR / LOOKUP_FILE, header=None, names=LOOKUP_COLUMNS,
        dtype=str, keep_default_na=False,
    )
    print(f"[load]     {LOOKUP_FILE}: {len(df):,} rows")
    return df


def build(ppd: pd.DataFrame, lookup: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    checks: dict = {}

    # --- fact table grain -------------------------------------------------
    if ppd["tuid"].duplicated().any():
        raise ValidationError(
            "transaction unique identifier is not unique in the monthly file; "
            "it is the declared primary key of the fact table"
        )
    checks["fct_grain_unique_tuid"] = {"rows": len(ppd), "passed": True}
    print(f"[grain]    fct_transaction: {len(ppd):,} rows, tuid unique")

    # --- referential integrity of the bridge ------------------------------
    orphans = int((~lookup["tuid"].isin(set(ppd["tuid"]))).sum())
    if orphans:
        raise ValidationError(
            f"{orphans:,} look-up rows reference a transaction absent from the "
            f"monthly file. The look-up's universe is assumed to be this "
            f"release; that assumption no longer holds."
        )
    checks["bridge_referential_integrity"] = {"orphan_lookup_rows": 0, "passed": True}
    print("[grain]    bridge: 0 orphan look-up rows")

    bridge = lookup.rename(columns={"tuid": "tuid", "uprn": "uprn"}).copy()

    # --- cardinality, transaction -> UPRN ---------------------------------
    uprn_count = bridge.groupby("tuid").size().rename("uprn_count")
    fct = ppd.merge(uprn_count, left_on="tuid", right_index=True, how="left")
    fct["uprn_count"] = fct["uprn_count"].fillna(0).astype("int64")
    fct["is_matched"] = fct["uprn_count"] > 0

    forward = fct["uprn_count"].value_counts().sort_index()
    checks["cardinality_transaction_to_uprn"] = {
        "zero_uprns": int((fct["uprn_count"] == 0).sum()),
        "one_uprn": int((fct["uprn_count"] == 1).sum()),
        "many_uprns": int((fct["uprn_count"] > 1).sum()),
        "max_uprns_per_transaction": int(fct["uprn_count"].max()),
    }
    print("[card]     UPRNs per transaction: " + ", ".join(
        f"{n}->{c:,}" for n, c in forward.items()))

    # The assertion the article is about: a left join must not change the row
    # count of the fact table. It holds here because uprn lives in the bridge.
    if len(fct) != len(ppd):
        raise ValidationError(
            f"fact table row count changed on join: {len(ppd):,} -> {len(fct):,}"
        )
    checks["join_preserves_fct_row_count"] = {
        "before": len(ppd), "after": len(fct), "passed": True,
    }
    print(f"[card]     join preserved fct row count: {len(ppd):,} -> {len(fct):,}")

    # --- cardinality, UPRN -> transaction (the multiplicity that DOES exist)
    per_uprn = bridge.groupby("uprn").size()
    checks["cardinality_uprn_to_transaction"] = {
        "distinct_uprns": int(per_uprn.size),
        "uprns_with_multiple_transactions": int((per_uprn > 1).sum()),
        "transactions_on_repeat_uprns": int(per_uprn[per_uprn > 1].sum()),
        "max_transactions_per_uprn": int(per_uprn.max()),
    }
    print(
        f"[card]     {int((per_uprn > 1).sum()):,} UPRNs carry >1 transaction "
        f"(max {int(per_uprn.max())}) — aggregating by property double-counts"
    )

    checks["observed_domains"] = {
        c: sorted(ppd[c].unique()) for c in OBSERVED_DOMAINS
    }
    return fct, bridge, checks


def validation_gate(fct: pd.DataFrame) -> dict:
    """Reproduce HMLR's own transaction count from this extraction."""
    reference = json.loads((BRONZE_DIR / "reconciliation_reference.json").read_text())
    target = reference["linked_data"]["target"]
    month, expected = target["transfer_month"], target["count"]

    actual = int((fct["transfer_month"] == month).sum())
    passed = actual == expected
    print(
        f"[gate]     transfers dated {month}: extraction {actual:,} vs "
        f"HMLR linked data {expected:,} -> {'MATCH' if passed else 'MISMATCH'}"
    )
    if not passed:
        raise ValidationError(
            f"validation gate failed for {month}: extracted {actual:,}, HMLR "
            f"linked data reports {expected:,} (difference {actual - expected:+,}). "
            f"Nothing downstream may be published until this is explained."
        )

    controls = []
    for control in reference["linked_data"]["controls"]:
        ym = control["transfer_month"]
        in_release = int((fct["transfer_month"] == ym).sum())
        controls.append({
            "transfer_month": ym,
            "in_this_release": in_release,
            "hmlr_linked_data_total": control["count"],
            "published_in_earlier_releases": control["count"] - in_release,
        })
        print(
            f"[gate]     control {ym}: {in_release:,} in this release of "
            f"{control['count']:,} total — {control['count'] - in_release:,} "
            f"published earlier, as expected for a delta file"
        )

    return {
        "endpoint": reference["linked_data"]["endpoint"],
        "reconciliation_month": month,
        "expected": expected,
        "actual": actual,
        "passed": passed,
        "controls": controls,
    }


def main() -> None:
    SILVER_DIR.mkdir(parents=True, exist_ok=True)

    bronze = verify_bronze()
    ppd, lookup = load_ppd(), load_lookup()
    fct, bridge, checks = build(ppd, lookup)
    gate = validation_gate(fct)

    fct.to_parquet(SILVER_DIR / "fct_transaction.parquet", index=False)
    bridge.to_parquet(SILVER_DIR / "bridge_transaction_uprn.parquet", index=False)
    print(f"[write]    fct_transaction.parquet    {len(fct):,} rows")
    print(f"[write]    bridge_transaction_uprn.parquet {len(bridge):,} rows")

    report = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bronze": bronze,
        "grain_and_cardinality": checks,
        "validation_gate": gate,
        "analysis_scope_note": (
            "is_analysis_row excludes record status D (deletions). They are "
            "unmatched by construction — the look-up covers live records only "
            "— so including them overstates the unmatched share."
        ),
    }
    (SILVER_DIR / "validation.json").write_text(json.dumps(report, indent=2))
    print(f"[write]    validation.json")


if __name__ == "__main__":
    main()
