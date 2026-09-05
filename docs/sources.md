# Sources and field specifications

All sources are HM Land Registry, published under the Open Government Licence
v3.0. UPRNs additionally carry Ordnance Survey Crown copyright and database
rights. Verified live on 5 September 2026.

## Attribution required on any published output

> Contains HM Land Registry data © Crown copyright and database right 2026.
> This data is licensed under the Open Government Licence v3.0.

> UPRNs contain OS data © Crown copyright and database rights 2026.
> This data is licensed under the Open Government Licence v3.0.

Address data in Price Paid Data is processed against Ordnance Survey's
AddressBase Premium, which incorporates Royal Mail's PAF database. Royal Mail
and OS permit its use for personal/non-commercial purposes and for displaying
residential property price information. Any other use of the address fields
requires Royal Mail's permission.

## Files ingested

| File | URL | Bytes | Lines |
|---|---|---|---|
| `pp-monthly-update-new-version.csv` | `https://price-paid-data.publicdata.landregistry.gov.uk/pp-monthly-update-new-version.csv` | 17,735,671 | 101,600 |
| `pp-uprn-lookup-jul-2026.csv` | `https://price-paid-data.publicdata.landregistry.gov.uk/pp-uprn-lookup-jul-2026.csv` | 5,169,801 | 94,112 |

Both carry `Last-Modified: Fri, 28 Aug 2026 05:12 GMT` — the release moment.
Neither has a header row.

The complete file (`pp-complete.csv`, 5,510,772,256 bytes, all transactions
from 1 January 1995) is **not** ingested. See "Scope" below.

### Naming

The published filename is `pp-uprn-lookup-jul-2026.csv` — hyphenated, and the
month is the **data** month, not the publication month. The file published on
28 August 2026 is named `jul-2026`. `pp-uprn-lookup-aug-2026.csv` returns HTTP
403; it does not exist yet.

### Retention

HMLR keeps only the latest version of each file, at a stable URL, overwritten
in place on the 20th working day of each month. The Bronze copy is the only
archive. Nothing in this repo is reproducible from source after the next
release.

## Field specifications

### Price Paid Data, "new version" monthly format (16 fields)

| # | Field | Notes |
|---|---|---|
| 1 | Transaction unique identifier | 38 characters, **including braces**: `{GUID}` |
| 2 | Price | |
| 3 | Date of Transfer | |
| 4 | Postcode | may be empty |
| 5 | Property Type | D detached, S semi-detached, T terraced, F flat/maisonette, O other |
| 6 | Old/New | Y newly built, N established |
| 7 | Duration | F freehold, L leasehold |
| 8 | PAON | primary addressable object name |
| 9 | SAON | secondary addressable object name |
| 10 | Street | |
| 11 | Locality | |
| 12 | Town/City | |
| 13 | District | |
| 14 | County | |
| 15 | PPD Category Type | A standard price paid, B additional price paid |
| 16 | Record Status | A add, C change, D delete — **monthly file only** |

The complete file omits field 16. PPD Category B covers repossessions and
power-of-sale transfers, buy-to-lets, transfers to non-private individuals,
and "Other" property types.

### UPRN Look Up Table (2 fields)

| # | Field | Type |
|---|---|---|
| 1 | Transaction unique identifier | 38-character identifier, braced |
| 2 | UPRN | 12-digit maximum identifier |

Both mandatory. Spec: <https://www.gov.uk/government/statistical-data-sets/technical-specification-transaction-unique-identifier-and-uprn-look-up-table-dataset>

### Why a transaction will not match a UPRN

The specification lists five exclusion categories:

1. Plots of land, fields, garden land, development land or amenity land
   without postal addresses
2. Garages, parking spaces or storage units sold separately without
   independent addressable locations
3. Newly built properties or converted units not yet in the latest PAF data
4. Properties with incomplete, non-standard or mismatched registered title
   addresses
5. Partial transactions of larger titles with no identifiable separate
   addressable location

The spec also states that one sale may link to more than one UPRN, "because a
sale can cover more than one addressable location, such as several flats,
separate dwellings, or different parts of a property."

## Scope

The look-up table is forward-only: it applies to monthly Price Paid Data
published from 28 August 2026 onwards and is not available for previously
published datasets.

Verified empirically: all 94,112 look-up identifiers appear in
`pp-monthly-update-new-version.csv`, and none fall outside it. **The
denominator for any match-rate figure is therefore the 101,600-row monthly
file, not the 30-year complete file.** Joining the look-up to `pp-complete.csv`
yields a match rate near zero that measures the forward-only policy and
nothing else.

## Reconciliation source

HMLR publishes the same Price Paid Data through a SPARQL triplestore at
<https://landregistry.data.gov.uk/landregistry/query>, licensed OGL v3.0. Used
as the validation gate: see `src/pipeline/02_bronze_reconciliation_reference.py`.

Crossing between the two channels on transaction id requires care. The CSVs
carry the braced 38-character form; the triplestore carries a bare 36-character
GUID typed as `ppi:TransactionIdDatatype`. A plain string literal matches
nothing:

```sparql
PREFIX ppi: <http://landregistry.data.gov.uk/def/ppi/>
SELECT ?date ?price WHERE {
  ?rec ppi:transactionId "8D2A39EB-879B-491E-91F9-2AB12DDF769C"^^ppi:TransactionIdDatatype ;
       ppi:transactionDate ?date ; ppi:pricePaid ?price }
```

The resource URI `http://landregistry.data.gov.uk/data/ppi/transaction/<guid>`
also dereferences directly.

`ppi:recordStatus` in the triplestore is **not** the CSV's Record Status. The
triplestore holds current state; the CSV holds the operation applied in this
cycle. A 1995 record marked `C` in the CSV reads `ppi:add` in the triplestore.

## Secondary reference, not a gate

HMLR's Transaction Data release of 21 August 2026 reports 103,398
"transactions for value" for July 2026, out of 2,134,898 applications
completed. Counted by application *completion* date, England and Wales.

This is a different universe from the Price Paid monthly file, which is a
delta of adds, changes and deletions spanning transfer dates back to 1995.
Recorded for context; not reconciled against.

<https://www.gov.uk/guidance/hm-land-registry-transaction-data>
