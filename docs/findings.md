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
Cochran's Q = 331.4 on 4 df, p ≈ 1.8×10⁻⁷⁰. Stratum risk ratios run from 0.78
to 6.54 — the effect is not merely confounded, it is *modified* by property
type, reversing direction between houses and land.

The Mantel-Haenszel adjusted risk ratio is 1.452 (1.336–1.579). It is computed
and stored in `summary.json`, and it should **not** be quoted as "the"
new-build effect. It is a weighted average of a sixfold effect in houses, no
effect in flats, and a slight protective effect in land. Reporting it alone
would be a cleaner-looking number that says less than the table above.

## 5. Two stronger predictors than new-build status

| Cut | Unmatched | Risk ratio |
|---|---|---|
| PPD category B (repossessions, buy-to-let, non-private purchasers, "Other" types) | 19.36% | 6.79 (6.46–7.14) |
| PPD category A (standard) | 2.85% | 0.15 |
| Postcode absent (n=262) | **99.62%** | 17.41 |
| Postcode present | 5.72% | 0.06 |

Cramér's V for PPD category is 0.273. The postcode result is effectively
deterministic and confirms the spec's "incomplete address detail" exclusion:
of 262 transactions with no postcode, exactly one matched.

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

## 7. What this data cannot support

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
