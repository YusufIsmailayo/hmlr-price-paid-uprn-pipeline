"""
Bronze capture of the publisher's own figures, for the validation gate.

Scripted equivalent of notebooks/01_bronze.ipynb.

The gate is: rebuild HM Land Registry's own transaction count from our
extraction and confirm it matches. That requires an independently published
figure to match *against*, captured at ingest time with its provenance.

HMLR serves the same Price Paid Data through a second channel — a SPARQL
triplestore at landregistry.data.gov.uk. Same publisher, same records,
entirely separate delivery pipeline, so agreement between it and our CSV
extraction is real evidence and not a tautology.

Why only the newest transfer month is a clean test
--------------------------------------------------
pp-monthly-update-new-version.csv is a delta. For any transfer month except
the newest, the triplestore holds this release's rows *plus* rows for the
same month published in earlier releases, so the counts must diverge. Only
the newest transfer month is wholly contained in a single release. The
adjacent months are queried here as well, precisely so the audit trail shows
the divergence and demonstrates that the match on the newest month is
mechanism rather than coincidence.

Joining on transaction id across the two channels (not needed for this gate,
but noted so it is not rediscovered the hard way): the CSVs carry the
38-character *braced* identifier, the triplestore a bare 36-character GUID
typed as ppi:TransactionIdDatatype — a plain xsd:string literal matches
nothing. Either use "<guid>"^^ppi:TransactionIdDatatype or dereference
http://landregistry.data.gov.uk/data/ppi/transaction/<guid> directly.
"""

from __future__ import annotations

import calendar
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
BRONZE_DIR = REPO_ROOT / "data" / "bronze"
RELEASE_SLUG = "release_2026-08-28"

SPARQL_ENDPOINT = "https://landregistry.data.gov.uk/landregistry/query"

# Newest transfer month in the 28 Aug 2026 release — the reconciliation month.
TARGET_MONTH = "2026-07"
# Earlier months, expected to diverge. Evidence, not a test.
CONTROL_MONTHS = ["2026-06", "2026-05", "2025-09"]

QUERY_TEMPLATE = """PREFIX ppi: <http://landregistry.data.gov.uk/def/ppi/>
SELECT (COUNT(*) AS ?n) WHERE {{
  ?t ppi:transactionDate ?d .
  FILTER(?d >= "{first}"^^<http://www.w3.org/2001/XMLSchema#date>
      && ?d <= "{last}"^^<http://www.w3.org/2001/XMLSchema#date>)
}}"""

# Secondary figure. Recorded for context, deliberately NOT used as the gate:
# Transaction Data counts applications *completed* in the month, whereas the
# Price Paid monthly file is a delta of adds/changes/deletions spanning three
# decades of transfer dates. Different universes; forcing them to agree would
# be manufacturing a match.
TRANSACTION_DATA_REFERENCE = {
    "source_url": "https://www.gov.uk/government/news/july-2026-transaction-data",
    "guidance_url": "https://www.gov.uk/guidance/hm-land-registry-transaction-data",
    "published_date": "2026-08-21",
    "period": "July 2026",
    "coverage": "England and Wales",
    "basis": "customer applications completed in the month, by completion date",
    "transactions_for_value": 103398,
    "total_applications_completed": 2134898,
    "use": "context only — not a reconciliation target, see module docstring",
}


def month_bounds(ym: str) -> tuple[str, str]:
    year, month = (int(p) for p in ym.split("-"))
    return f"{ym}-01", f"{ym}-{calendar.monthrange(year, month)[1]:02d}"


def count_transactions(ym: str) -> dict:
    first, last = month_bounds(ym)
    query = QUERY_TEMPLATE.format(first=first, last=last)
    print(f"[sparql] counting transfers dated {first}..{last}")
    resp = requests.get(
        SPARQL_ENDPOINT,
        params={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=300,
    )
    resp.raise_for_status()
    count = int(resp.json()["results"]["bindings"][0]["n"]["value"])
    print(f"[sparql] {ym} -> {count:,}")
    return {"transfer_month": ym, "count": count, "query": query}


def main(force: bool = False) -> Path:
    out_dir = BRONZE_DIR / RELEASE_SLUG
    out_path = out_dir / "reconciliation_reference.json"
    if out_path.exists() and not force:
        print(f"[skip] reconciliation reference already captured at {out_path}")
        return out_path

    out_dir.mkdir(parents=True, exist_ok=True)
    reference = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "linked_data": {
            "endpoint": SPARQL_ENDPOINT,
            "publisher": "HM Land Registry",
            "licence": "Open Government Licence v3.0",
            "reconciliation_month": TARGET_MONTH,
            "target": count_transactions(TARGET_MONTH),
            "controls": [count_transactions(ym) for ym in CONTROL_MONTHS],
        },
        "transaction_data_reference": TRANSACTION_DATA_REFERENCE,
    }
    out_path.write_text(json.dumps(reference, indent=2))
    print(f"[metadata] {out_path.relative_to(REPO_ROOT)}")
    return out_path


if __name__ == "__main__":
    import sys

    main(force="--force" in sys.argv)
