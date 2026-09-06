# Findings

Release of 28 August 2026, data month July 2026. All figures reproduced from
the raw files by `src/pipeline/`; tables in `data/gold/release_2026-08-28/`.

Analysis scope is 100,086 transactions — the monthly release of 101,600 less
1,514 deletions, which are unmatched by construction.

**Headline: 5.97% of transactions have no UPRN. The gaps are emphatically not
random, but the axis of the bias is property type, not the new-build flag.**

## 1. Cardinality

| Cardinality | Transactions | Effect on the fact table |
|---|---|---|
| 0 UPRNs | 5,974 | dropped silently by an inner join |
| 1 UPRN | 94,112 | grain preserved |
| >1 UPRN | **0** | none — does not occur in this release |

HMLR's specification allows one sale to link to several UPRNs. In the first
published month it never happens. A left join leaves the fact table at exactly
101,600 rows.

The multiplicity that does exist runs the other way: **1,055 UPRNs carry
between 2 and 7 transactions each**, 2,417 transactions in total. That is
harmless at transaction grain and double-counts the moment anything is
aggregated by property.

## 2. Property type — the bias is large

| Type | n | Unmatched | 95% CI | Risk ratio vs rest |
|---|---|---|---|---|
| Other — land / garages / non-residential | 6,286 | **43.59%** | 42.37–44.82 | **12.64** (12.10–13.21) |
| Flat / maisonette | 16,861 | 12.69% | 12.20–13.20 | 2.76 (2.62–2.90) |
| Detached | 23,135 | 1.93% | 1.76–2.11 | 0.27 |
| Terraced | 26,383 | 1.38% | 1.25–1.53 | 0.18 |
| Semi-detached | 27,421 | 1.03% | 0.92–1.16 | 0.13 |

Cramér's V = 0.448. A "land or garage" sale is **42 times** more likely to be
unmatched than a semi-detached house. This is the finding, and it is exactly
what the specification's exclusion list predicts.

## 3. New build — the premise does not survive as stated

| Flag | n | Unmatched | 95% CI |
|---|---|---|---|
| New build | 7,960 | 6.70% | 6.17–7.27 |
| Established | 92,126 | 5.91% | 5.76–6.06 |

Crude risk ratio **1.13** (1.04–1.236). Cramér's V = **0.009**.

The intervals separate, so with 100,086 rows the effect is detectable. It is
also nearly nothing. A bar chart of unmatched share by new-build flag shows
two bars of almost equal height, and any piece resting on that chart is
resting on a 0.8 percentage-point gap.

## 4. Why the new-build effect is hidden, and what it really is

Stratifying by property type reverses the impression:

| Property type | New build | Established | Stratum RR |
|---|---|---|---|
| Semi-detached | 4.75% (n=2,083) | 0.73% (n=25,338) | **6.54** |
| Terraced | 7.50% (n=867) | 1.18% (n=25,516) | **6.38** |
| Detached | 3.08% (n=3,113) | 1.75% (n=20,022) | 1.76 |
| Flat / maisonette | 12.67% (n=1,744) | 12.69% (n=15,117) | 1.00 |
| Other | 33.99% (n=153) | 43.83% (n=6,133) | 0.78 |

Among houses, a new build is six times more likely to be unmatched — precisely
the PAF-lag mechanism the specification describes. The crude figure hides it
because the two groups have different compositions: "Other" is 6.7% of
established sales but only 1.9% of new builds, and it drags the established
rate up; flats are over-represented among new builds and are equally unmatched
either way.

**But the strata do not agree, and that rules out a single adjusted number.**
Cochran's Q = 332.6 on 4 df, p ≈ 1.0×10⁻⁷⁰. Stratum risk ratios run from 0.78
to 6.54 — the effect is not merely confounded, it is *modified* by property
type, reversing direction between houses and land.

The Mantel-Haenszel adjusted risk ratio is 1.452 (1.336–1.579). It is computed
and stored in `summary.json`, and it should **not** be quoted as "the"
new-build effect. It is a weighted average of a sixfold effect in houses, no
effect in flats, and a slight protective effect in land. Reporting it alone
would be a cleaner-looking number that says less than the table above.

## 5. Two stronger predictors than new-build status — with one correction

| Cut | Unmatched | Risk ratio |
|---|---|---|
| PPD category B (repossessions, buy-to-let, non-private purchasers, "Other" types) | 19.36% | 6.79 (6.46–7.14) |
| PPD category A (standard) | 2.85% | 0.15 |
| Postcode absent (n=262) | **99.62%** | 17.41 |
| Postcode present | 5.72% | 0.06 |

Cramér's V for PPD category is 0.273. The postcode result is effectively
deterministic and confirms the spec's "incomplete address detail" exclusion:
of 262 transactions with no postcode, exactly one matched.

**Correction — PPD category and property type are not independent.** I first
read the category B result as a finding standing alongside property type. It
is not. Every one of the 6,286 "Other" transactions is category B and **none
is category A**, so O sits wholly inside B, and the category B rate is largely
the O rate under a different label.

| Scope | n | Unmatched |
|---|---|---|
| A — standard price paid | 81,190 | 2.85% |
| B — additional price paid | 18,896 | 19.36% |
| B, of which property type O | 6,286 | 43.59% |
| **B, net of property type O** | 12,610 | **7.29%** |

Three quarters of category B's unmatched rows are the O rows. Net of them the
category still matters — 7.29% against 2.85% — but it is a secondary effect,
not a second finding. `06_gold_context_cuts.py` asserts the overlap on every
run and stops the build if a category A "Other" row ever appears.

## 6. Honest verdict on the premise

The article's premise was that unmatched sales are disproportionately
new-builds and land-only sales, and that a new-build bar materially taller
than an established one would carry the piece.

- **Land and non-addressable property: confirmed, overwhelmingly.** 43.59%
  unmatched, 12.6× the rest. This is the finding.
- **New builds: not confirmed as stated.** 6.70% vs 5.91% crude. The chart the
  outline expects to carry the piece does not carry it.
- **New builds, conditioned on property type: confirmed for houses**, at a
  sixfold relative risk — but with such strong effect modification that it
  cannot be stated as one number.

The bias is real, it is large, and it is knowable in direction. It is simply
not located where the outline placed it. The compositional effect — that the
naive chart hides a real sixfold signal behind a flat one — is a more
interesting result than the one originally sought, and it is fully reproducible
from this repo.

## 7. Four further cuts, once the bias question was settled

From `06_gold_context_cuts.py`; tables `08`–`13` and `context_summary.json`.

### Unmatched sales are not cheap scraps — they skew expensive

| Scope | Median matched | Median unmatched | Unmatched share of transactions | of value |
|---|---|---|---|---|
| All transactions | £284,000 | £320,000 | 5.97% | **12.69%** |
| Category A only | £295,000 | £375,000 | 2.85% | 3.73% |

I expected unmatched sales to be low-value fragments. They are the opposite. The
12.69% value share is the striking figure, but most of it is category B carrying
portfolio transfers up to £141m, so the combined number overstates the hole and
should not be quoted alone. The category A row is the defensible one, and it
still points the same way.

The skew is concentrated in flats: within category A a matched flat has a median
price of £225,000 and an unmatched one £399,500. Houses barely move — detached
£415,000 matched against £392,500 unmatched.

### Geography is a null result

| Cut | Counties (n ≥ 300) | Range | Median |
|---|---|---|---|
| All property | 77 | 2.34% – 22.61% | 4.70% |
| Houses only | 65 | 0.25% – 3.56% | 1.32% |

On all property the spread looks like a real geographic effect — Brighton and
Hove worst at 22.61%, Greater London second at 14.71%. It is composition: those
are flat-heavy places, and flats match poorly everywhere. Hold property type
constant and the spread collapses, with London at 1.49% against 1.42% for the
rest of England and Wales.

That is the same trap as §3, in a second variable. Twice in one dataset, a
plausible driver turns out to be property type wearing a disguise.

### The 262 postcode-less transactions are institutional property

231 of 262 are property type O and 237 are category B. `paon` is populated on
every one, but `street` is blank on 17.6% against 1.8% across all transactions.
These are named places rather than addresses — Staffordshire Police
Headquarters at £10.3m, Summerhill Farm at £16.1m, "Plot 20", "Staddlestones".
Exclusion 4 in the specification, exactly as written.

### The repeated UPRNs are not what I documented them to be

I recorded the 1,055 repeated UPRNs only as a double-count hazard and never
asked what they were. The obvious reading — several dwellings under one
identifier, the multiplicity the specification warns about — is wrong.
**No repeated UPRN carries more than one distinct PAON or SAON.**
They are the same address sold repeatedly — 621 of them span more than one
calendar year, up to 31 years, and 991 of the 2,417 sales are dated before 2020.
They arrive together because the monthly file is a delta, not because a sale
covered several properties.

The remaining third (348 UPRNs, 266 of them at an identical price as well as an
identical date) do look like one title transferred in parts.

That reframing makes a harder finding available:

| Measure | UPRNs | Share | Sales affected |
|---|---|---|---|
| More than one property type | **208** | 19.7% | 502 |
| More than one duration (freehold vs leasehold) | **150** | 14.2% | 325 |
| More than one postcode | 0 | 0.0% | 0 |

Nearly a fifth of repeated UPRNs have Price Paid Data filing the same physical
property under different property types. The commonest disagreements involve
"Other": D/O on 78 UPRNs, O/T on 36, O/S on 35. One address — 4 The Cross,
Halifax — is recorded Detached, Detached, Terraced, Detached, Terraced,
Detached, Terraced across seven sales from 1996 to 2010.

This is only askable because the look-up exists. Without a stable key there was
no way to line up two rows describing the same building, so an inconsistency of
this kind was not merely unmeasured but unfalsifiable. The look-up's first
effect is not that it cleans Price Paid Data — it is that it makes Price Paid
Data checkable against itself.

## 8. What this data cannot support

- **One month only.** The look-up is forward-only and this is the first
  release in existence. Nothing here establishes a trend, and July is a single
  month of registrations, not of sales.
- **The 30-year back-catalogue is untouched.** These rates describe newly
  published records, not the complete file.
- **No official match rate exists** to check these figures against. The
  validation gate reconciles the transaction *count* against HMLR's own
  triplestore (22,835 = 22,835); the match rates themselves are unaudited
  because HMLR has published nothing to audit them with.
- **`is_matched` is not `is_matchable`.** A missing UPRN means HMLR's process
  produced no link, which is not the same as the property having no UPRN.
- **The repeat-sale consistency result covers repeats only.** 1,055 UPRNs is
  1.1% of the 92,750 distinct UPRNs in this release. It says nothing about the
  attribute quality of the other 98.9%, which have one sale each and therefore
  nothing to disagree with.
- **County rates are one month of registrations.** Ranking counties on a single
  delta file measures which places happened to register in July as much as
  anything structural.
