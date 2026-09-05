# HM Land Registry Price Paid Data — UPRN look-up match-rate analysis

On 28 August 2026 HM Land Registry published, for the first time, a stable
property identifier for Price Paid Data: a monthly CSV pairing the
38-character transaction unique identifier with a UPRN, under the Open
Government Licence v3.0.

HMLR's specification states which sales will not match — land without postal
addresses, garages sold separately, new builds not yet in the Royal Mail PAF,
incomplete title addresses, partial transactions. This pipeline tests whether
those gaps are randomly distributed, and if not, measures the direction and
size of the bias.

No official match rate has been published. Every figure here is reproduced
from the raw files by the code in this repo.

## Status

Bronze and Silver complete; the validation gate passes. Gold in progress.

## Layout

```
data/bronze/release_2026-08-28/   raw CSVs as served, plus provenance
data/silver/release_2026-08-28/   fact, bridge, and validation.json
data/gold/                        match-rate and bias tables
src/pipeline/                     numbered, runnable in order
docs/sources.md                   sources, field specs, licensing, scope
docs/data_dictionary.md           Silver tables, grain, assertions
```

Medallion pattern, pandas and Parquet, matching the other pipelines in this
portfolio.

## Running it

```
pip install -r requirements.txt
python3 src/pipeline/01_bronze_ppd_ingest.py
python3 src/pipeline/02_bronze_reconciliation_reference.py
python3 src/pipeline/03_silver_join.py
```

Bronze downloads ~23MB and is excluded from git. Pass `--force` to re-ingest.

**These files cannot be re-downloaded later.** HMLR keeps only the latest
month at a stable URL, overwritten in place on the 20th working day of each
month. Running Bronze after the next release captures a different month, not
this one.

## Validation gate

HMLR serves the same Price Paid Data through a second channel, a SPARQL
triplestore at `landregistry.data.gov.uk`. The gate reproduces HMLR's own
transaction count from this extraction and confirms it matches.

The monthly file is a delta, so only the newest transfer month is wholly
contained in a single release and can be tested for equality. Earlier months
are queried too, so the audit trail shows the expected divergence rather than
asserting a single lucky number.

**It passes.** Transfers dated July 2026: 22,835 from this extraction, 22,835
from HMLR's triplestore. The three control months diverge by exactly the
volume published in earlier releases. Silver writes no Parquet if the gate
fails.

## Grain

The fact table is one row per transaction and carries no `uprn` column; the
UPRNs live in a bridge at (transaction, UPRN) grain. HMLR's spec allows one
sale to map to several UPRNs, which would change the fact table's row count on
a left join. In this release it does not occur — 94,112 transactions match
exactly one UPRN, none match more. The multiplicity that *does* exist runs the
other way: 1,055 UPRNs carry between 2 and 7 transactions each.

See [docs/data_dictionary.md](docs/data_dictionary.md).

## Licence and attribution

Source data © Crown copyright, Open Government Licence v3.0. Required
attribution statements and the Royal Mail PAF conditions on the address fields
are set out in [docs/sources.md](docs/sources.md).

No personal data is used or published. Price Paid Data is property-related
information, not personal information.
