"""
Bronze ingest for HM Land Registry Price Paid Data and the Transaction unique
identifier / UPRN Look Up Table.

Downloads the two CSVs published together on 28 August 2026 and stamps each
with a SHA-256, the server's Last-Modified header and byte/line counts, into
one directory per monthly release.

Bronze is the only archive of these files that will ever exist. HMLR keeps
only the latest month of the UPRN look-up table, and
pp-monthly-update-new-version.csv is overwritten in place on the 20th working
day of each month. A month not captured here cannot be recovered later.

Files are written byte-for-byte as served: no header row is added, no parsing,
no type coercion. Both files ship without a header row — the field order is
recorded in docs/sources.md and applied in Silver, not here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
BRONZE_DIR = REPO_ROOT / "data" / "bronze"

BASE_URL = "https://price-paid-data.publicdata.landregistry.gov.uk"

# The look-up table is forward-only: it applies to monthly Price Paid Data
# published from 28 August 2026 onwards and is not available for previously
# published datasets. This is the first such release in existence.
RELEASE_SLUG = "release_2026-08-28"
PUBLICATION_DATE = "2026-08-28"
DATA_MONTH = "2026-07"

PPD_ATTRIBUTION = (
    "Contains HM Land Registry data © Crown copyright and database right 2026. "
    "This data is licensed under the Open Government Licence v3.0."
)
UPRN_ATTRIBUTION = (
    "UPRNs contain OS data © Crown copyright and database rights 2026. "
    "This data is licensed under the Open Government Licence v3.0."
)


@dataclass(frozen=True)
class Source:
    filename: str
    description: str
    attribution: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.filename}"


SOURCES = [
    Source(
        filename="pp-monthly-update-new-version.csv",
        description=(
            "Price Paid Data monthly update, 'new version' format (16 fields, "
            "including the Record Status column absent from the complete file). "
            "A delta, not a snapshot: additions, changes and deletions applied "
            "in this publication cycle, with transfer dates running back to 1995."
        ),
        attribution=[PPD_ATTRIBUTION],
    ),
    Source(
        filename="pp-uprn-lookup-jul-2026.csv",
        description=(
            "Transaction unique identifier and UPRN Look Up Table. Two fields, "
            "no header: 38-character braced transaction unique identifier, and "
            "UPRN (12 digits max). Covers the transactions in the monthly update "
            "published on the same date. The month in the filename is the data "
            "month, not the publication month."
        ),
        attribution=[PPD_ATTRIBUTION, UPRN_ATTRIBUTION],
    ),
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _line_count(path: Path) -> int:
    """Count records without parsing. Handles a missing trailing newline."""
    count = 0
    last = b""
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            count += chunk.count(b"\n")
            last = chunk[-1:] or last
    if last and last != b"\n":
        count += 1  # final record not newline-terminated
    return count


def fetch(source: Source, out_dir: Path) -> dict:
    dest = out_dir / source.filename
    print(f"[download] {source.filename} <- {source.url}")

    with requests.get(source.url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        headers = resp.headers
        with dest.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)

    size = dest.stat().st_size
    declared = headers.get("Content-Length")
    if declared is not None and int(declared) != size:
        raise IOError(
            f"{source.filename}: truncated download — "
            f"Content-Length {declared} but wrote {size} bytes"
        )

    record = {
        "filename": source.filename,
        "source_url": source.url,
        "description": source.description,
        "attribution": source.attribution,
        # Last-Modified is the release timestamp and the only version marker
        # these files carry — the URLs are stable and the contents are replaced.
        "http_last_modified": headers.get("Last-Modified"),
        "http_etag": headers.get("ETag"),
        "content_type": headers.get("Content-Type"),
        "size_bytes": size,
        "line_count": _line_count(dest),
        "sha256": _sha256(dest),
    }
    print(
        f"[stamped]  {size:,} bytes | {record['line_count']:,} lines | "
        f"sha256={record['sha256'][:16]}… | last-modified={record['http_last_modified']}"
    )
    return record


def main(force: bool = False) -> Path:
    out_dir = BRONZE_DIR / RELEASE_SLUG
    metadata_path = out_dir / "metadata.json"
    if metadata_path.exists() and not force:
        print(f"[skip] {RELEASE_SLUG}: already ingested at {out_dir}")
        return out_dir

    out_dir.mkdir(parents=True, exist_ok=True)
    files = [fetch(source, out_dir) for source in SOURCES]

    metadata = {
        "publisher": "HM Land Registry",
        "release_slug": RELEASE_SLUG,
        "publication_date": PUBLICATION_DATE,
        "data_month": DATA_MONTH,
        "publication_schedule": "20th working day of each month",
        "licence": "Open Government Licence v3.0",
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "retention_note": (
            "HMLR retains only the latest version of each of these files. Both "
            "URLs are stable and overwritten in place, so this Bronze copy is "
            "not reproducible from the source after the next release."
        ),
        "files": files,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2))
    print(f"[metadata] {metadata_path.relative_to(REPO_ROOT)}")
    return out_dir


if __name__ == "__main__":
    import sys

    main(force="--force" in sys.argv)
