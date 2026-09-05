# Data dictionary — Silver

Written by `src/pipeline/03_silver_join.py` to
`data/silver/release_2026-08-28/`. Source field definitions are in
[sources.md](sources.md); this covers the modelled tables.

## Why two tables

HMLR's specification allows one sale to link to several UPRNs, because a sale
can cover more than one addressable location. A `uprn` column on the fact
table would therefore change its row count the first month that happens —
silently, on a left join, with no error.

So the fact table stays at transaction grain permanently and carries only
`uprn_count` / `is_matched`. The UPRNs themselves live in a bridge table at
(transaction, UPRN) grain. This is grain-safe whatever a later month contains.

In the 28 August 2026 release the bridge happens to be one-to-one, so the
distinction costs nothing today. That is the point of building it now.

## `fct_transaction.parquet` — 101,600 rows

Grain: one row per transaction unique identifier. Asserted unique.

| Column | Type | Notes |
|---|---|---|
| `tuid` | string | Primary key. 38 characters **including braces**, as published. Strip braces only when crossing to HMLR's triplestore, which also requires the `ppi:TransactionIdDatatype` typed literal. |
| `price` | int64 | |
| `postcode` | string | Empty string where absent — not null, not imputed. Missing address detail is a documented non-match reason, so absence is signal. |
| `property_type` | string | D detached, S semi-detached, T terraced, F flat/maisonette, O other. Domain enforced. |
| `old_new` | string | Y newly built, N established. Domain enforced. |
| `duration` | string | F freehold, L leasehold. Observed, not enforced. |
| `paon`, `saon`, `street`, `locality`, `town_city`, `district`, `county` | string | Address fields. Royal Mail PAF conditions apply — see sources.md. |
| `ppd_category_type` | string | A standard, B additional. Domain enforced. |
| `record_status` | string | A add, C change, D delete. Domain enforced. |
| `transfer_date` | datetime64[ns] | Parsed from the source's `YYYY-MM-DD 00:00`. |
| `transfer_month` | string | `YYYY-MM`. Used by the validation gate. |
| `has_postcode` | bool | |
| `is_analysis_row` | bool | `record_status != 'D'`. See below. |
| `uprn_count` | int64 | 0, 1, or more. Never null. |
| `is_matched` | bool | `uprn_count > 0`. |

## `bridge_transaction_uprn.parquet` — 94,112 rows

Grain: one row per (transaction, UPRN) pair.

| Column | Type | Notes |
|---|---|---|
| `tuid` | string | Foreign key to `fct_transaction`. Referential integrity asserted: zero orphans. |
| `uprn` | string | Held as string, not integer, so the identifier is never arithmetic and never coerced through a float. |

## Deletions

`is_analysis_row` is `False` for the 1,514 record-status-D rows. They are kept
in Silver rather than dropped, so the decision is visible and reversible, and
excluded in Gold.

They are unmatched by construction — the look-up covers live records only, and
all 1,514 have zero UPRNs. Leaving them in an analysis denominator moves the
unmatched share from 5.97% to 7.37%, a 1.4-point artefact of not reading the
Record Status column.

## Assertions

All in `validation.json` alongside the tables. Any failure raises and no
Parquet is written.

| Assertion | Result |
|---|---|
| Bronze SHA-256 matches the ingest manifest | pass |
| `tuid` unique in the fact table | pass, 101,600 |
| Zero orphan look-up rows | pass |
| Enforced domains contain no unexpected values | pass |
| Left join does not change fact table row count | pass, 101,600 → 101,600 |
| Validation gate: transfers dated 2026-07 reproduce HMLR's own count | pass, 22,835 = 22,835 |

## Cardinality as measured

| Direction | Finding |
|---|---|
| Transaction → UPRN | 0 UPRNs: 7,488. 1 UPRN: 94,112. **More than 1: zero.** Max 1. |
| UPRN → transaction | 1,055 UPRNs carry 2–7 transactions each. Aggregating by property double-counts sales. |

The multiplicity the specification warns about does not occur in this release.
The multiplicity that does occur runs the other way, and is the one that will
bite an analysis grouped by property rather than by sale.
