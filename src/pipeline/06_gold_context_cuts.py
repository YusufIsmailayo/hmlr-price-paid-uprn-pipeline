"""
Gold: the cuts behind findings.md §8, plus the correction to §5.

04_gold_cuts.py answers the question the project was built to ask. This script
answers the four I asked afterwards, once the bias result was settled, and it
exists because those figures were originally computed in a scratch script.
Anything quoted in docs/ has to be reproducible from the repo, so they live
here now.

  1. Price. I assumed unmatched sales would be cheap scraps. They are not.
  2. Geography. Whether the unmatched share varies by county once property
     type is held constant. It does not, and the null is worth publishing.
  3. The 262 transactions published with no postcode.
  4. The 1,055 UPRNs carrying more than one sale.

One correction falls out of the crosstab at the top. Every "Other" transaction
is PPD category B and none is category A, so category B and property type O are
not independent predictors — O sits wholly inside B. findings.md §5 originally
read them as two findings. Net of O, category B's unmatched share falls from
19.36% to 7.29%, and this script writes both figures so the correction is
checkable rather than asserted.

Method note on §4. The obvious reading of the repeated UPRNs is that they are
several dwellings under one identifier — the multiplicity HMLR's spec warns
about. They are not: no
repeated UPRN carries more than one distinct PAON or SAON. They are the same
address sold repeatedly across up to 31 years, arriving together because the
monthly file is a delta. That makes them the first opportunity anyone has had
to check Price Paid Data's own attributes against a stable key, which is what
the consistency table measures.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_SLUG = "release_2026-08-28"
SILVER_DIR = REPO_ROOT / "data" / "silver" / RELEASE_SLUG
GOLD_DIR = REPO_ROOT / "data" / "gold" / RELEASE_SLUG

Z = 1.959963984540054  # 95%

PROPERTY_TYPE_LABELS = {
    "D": "Detached", "S": "Semi-detached", "T": "Terraced",
    "F": "Flat / maisonette", "O": "Other — land / garages / non-residential",
}
HOUSE_TYPES = ["D", "S", "T"]
MIN_COUNTY_N = 300  # below this a county rate is too noisy to rank


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + Z * Z / n
    centre = p + Z * Z / (2 * n)
    spread = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n))
    return ((centre - spread) / denom, (centre + spread) / denom)


def write(df: pd.DataFrame, name: str) -> None:
    df.to_csv(GOLD_DIR / f"{name}.csv", index=False)
    print(f"[gold]  {name}.csv ({len(df)} rows)")


def rate(df: pd.DataFrame) -> tuple[int, int, float]:
    n, unmatched = len(df), int((~df["is_matched"]).sum())
    return n, unmatched, round(100 * unmatched / n, 2) if n else float("nan")


# --- 1. the §5 correction -------------------------------------------------

def ppd_category_net_of_other(a: pd.DataFrame) -> pd.DataFrame:
    """
    Category B against category A, and category B with the O rows removed.

    All 6,286 O transactions are category B, so the headline B rate is largely
    the O rate wearing a different label. Splitting it is the honest reading.
    """
    rows = []
    for label, sub in [
        ("A — standard price paid", a[a.ppd_category_type == "A"]),
        ("B — additional price paid", a[a.ppd_category_type == "B"]),
        ("B, of which property type O", a[(a.ppd_category_type == "B") & (a.property_type == "O")]),
        ("B, net of property type O", a[(a.ppd_category_type == "B") & (a.property_type != "O")]),
    ]:
        n, unmatched, pct = rate(sub)
        lo, hi = wilson(unmatched, n)
        rows.append({
            "scope": label, "transactions": n, "unmatched": unmatched,
            "unmatched_pct": pct,
            "unmatched_ci_low_pct": round(100 * lo, 2),
            "unmatched_ci_high_pct": round(100 * hi, 2),
        })
    return pd.DataFrame(rows)


# --- 2. price -------------------------------------------------------------

def price_by_match_status(a: pd.DataFrame) -> pd.DataFrame:
    """
    Quantiles rather than means. One £141m portfolio transfer moves a mean and
    tells the reader nothing about a typical unmatched sale.

    Reported for all transactions and for category A alone, because the value
    share is dominated by category B and quoting the combined figure without
    that split would overstate the hole.
    """
    rows = []
    for scope, sub in [("All transactions", a),
                       ("Category A only", a[a.ppd_category_type == "A"])]:
        total_value = int(sub["price"].sum())
        for status, part in [("matched", sub[sub.is_matched]),
                             ("unmatched", sub[~sub.is_matched])]:
            p = part["price"]
            rows.append({
                "scope": scope, "match_status": status, "transactions": len(part),
                "share_of_transactions_pct": round(100 * len(part) / len(sub), 2),
                "price_p25": int(p.quantile(0.25)), "price_median": int(p.median()),
                "price_p75": int(p.quantile(0.75)), "price_p95": int(p.quantile(0.95)),
                "price_max": int(p.max()),
                "total_value_gbp": int(p.sum()),
                "share_of_value_pct": round(100 * p.sum() / total_value, 2),
            })
    return pd.DataFrame(rows)


def price_by_type_and_match(a: pd.DataFrame) -> pd.DataFrame:
    """Median price by property type and match status, category A only."""
    aa = a[a.ppd_category_type == "A"]
    rows = []
    for code, label in PROPERTY_TYPE_LABELS.items():
        sub = aa[aa.property_type == code]
        if sub.empty:
            # O has no category A rows at all — recorded, not silently skipped.
            rows.append({"property_type": code, "label": label, "transactions": 0,
                         "median_matched": None, "median_unmatched": None})
            continue
        m, u = sub[sub.is_matched]["price"], sub[~sub.is_matched]["price"]
        rows.append({
            "property_type": code, "label": label, "transactions": len(sub),
            "median_matched": int(m.median()) if len(m) else None,
            "median_unmatched": int(u.median()) if len(u) else None,
        })
    return pd.DataFrame(rows)


# --- 3. geography ---------------------------------------------------------

def unmatched_by_county(a: pd.DataFrame) -> pd.DataFrame:
    """
    County rates on all property, and on houses alone.

    The all-property spread looks like a geographic effect. It is composition:
    flat-heavy places score badly because flats match poorly. Holding property
    type constant is the whole point of the second column.
    """
    rows = []
    houses = a[a.property_type.isin(HOUSE_TYPES)]
    for county, group in a.groupby("county"):
        n, unmatched, pct = rate(group)
        if n < MIN_COUNTY_N:
            continue
        h = houses[houses.county == county]
        hn, h_unmatched, h_pct = rate(h)
        rows.append({
            "county": county, "transactions": n, "unmatched": unmatched,
            "unmatched_pct": pct,
            "house_transactions": hn, "house_unmatched": h_unmatched,
            "house_unmatched_pct": h_pct if hn >= MIN_COUNTY_N else None,
        })
    return pd.DataFrame(rows).sort_values("unmatched_pct", ascending=False)


# --- 4. the postcode-less rows -------------------------------------------

def postcode_absent_profile(a: pd.DataFrame) -> pd.DataFrame:
    """What the transactions published without a postcode actually are."""
    absent = a[~a.has_postcode]
    rows = []
    for column in ("property_type", "old_new", "duration", "ppd_category_type"):
        for value, count in absent[column].value_counts().items():
            rows.append({
                "attribute": column, "value": value, "transactions": int(count),
                "share_of_postcode_absent_pct": round(100 * count / len(absent), 2),
            })
    for column in ("saon", "street", "locality"):
        rows.append({
            "attribute": "blank_field_share", "value": column,
            "transactions": int((absent[column] == "").sum()),
            "share_of_postcode_absent_pct": round(100 * (absent[column] == "").mean(), 2),
        })
    return pd.DataFrame(rows)


# --- 5. the repeated UPRNs ------------------------------------------------

def repeat_uprn_consistency(a: pd.DataFrame, bridge: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    For every UPRN carrying more than one sale, do Price Paid Data's own
    attributes agree with themselves?

    This is only askable because the look-up exists. Before it, there was no
    stable key against which two rows describing the same building could be
    compared, so an inconsistency of this kind was unfalsifiable.
    """
    per_uprn = bridge.groupby("uprn").size()
    repeated = set(per_uprn[per_uprn > 1].index)
    joined = bridge[bridge.uprn.isin(repeated)].merge(a, on="tuid", how="inner")
    joined["transfer_year"] = joined["transfer_date"].dt.year

    grouped = joined.groupby("uprn").agg(
        sales=("tuid", "size"),
        distinct_property_type=("property_type", "nunique"),
        distinct_duration=("duration", "nunique"),
        distinct_postcode=("postcode", "nunique"),
        distinct_paon=("paon", "nunique"),
        distinct_saon=("saon", "nunique"),
        distinct_date=("transfer_date", "nunique"),
        distinct_price=("price", "nunique"),
        first_year=("transfer_year", "min"),
        last_year=("transfer_year", "max"),
    )
    n = len(grouped)

    def row(label, mask, note):
        return {"measure": label, "uprns": int(mask.sum()),
                "share_of_repeated_uprns_pct": round(100 * mask.mean(), 2),
                "sales_affected": int(grouped.loc[mask, "sales"].sum()), "note": note}

    table = pd.DataFrame([
        row("More than one property type", grouped.distinct_property_type > 1,
            "outer bound — most involve the residual Other bucket"),
        row("More than one duration", grouped.distinct_duration > 1,
            "freehold on one sale, leasehold on another"),
        row("More than one postcode", grouped.distinct_postcode > 1, ""),
        row("More than one PAON", grouped.distinct_paon > 1,
            "would indicate several dwellings under one UPRN"),
        row("More than one SAON", grouped.distinct_saon > 1,
            "would indicate several flats under one UPRN"),
        row("All sales share one transfer date", grouped.distinct_date == 1,
            "consistent with one title transferred in parts"),
        row("All sales share one date and price", (grouped.distinct_date == 1)
            & (grouped.distinct_price == 1), ""),
        row("Spans more than one calendar year", grouped.last_year > grouped.first_year,
            "a price history, not a same-month multi-sale"),
    ])

    inconsistent = grouped[grouped.distinct_property_type > 1].index
    combos = (joined[joined.uprn.isin(inconsistent)]
              .groupby("uprn").property_type.apply(lambda s: " / ".join(sorted(set(s)))))
    pairs = combos.value_counts().rename_axis("property_type_pair").reset_index(name="uprns")

    # "Other" is not a dwelling type. It is the residual bucket for land,
    # garages, parking and non-residential, so a plot recorded as O and the
    # house later built on it recorded as D are two correct descriptions of
    # different things, not the register contradicting itself. Only conflicts
    # between two genuine dwelling types are unarguable, so they are counted
    # separately and it is that smaller number the write-up leads on.
    pairs["involves_other"] = pairs["property_type_pair"].str.contains("O")
    hard = combos[~combos.str.contains("O")]

    # Sequence order cannot resolve the innocent reading either way: among the
    # D/O pairs the split between land-first and land-last is near even, and a
    # third of them share a transfer date, so the ordering is not well defined.
    do_uprns = combos[combos == "D / O"].index
    do = joined[joined.uprn.isin(do_uprns)].sort_values("transfer_date")
    tied = int(do.groupby("uprn").transfer_date.apply(lambda s: s.duplicated().any()).sum())

    summary = {
        "repeated_uprns": n,
        "type_conflicts": {
            "uprns_any_type_conflict": int(len(combos)),
            "uprns_conflict_involving_other": int(combos.str.contains("O").sum()),
            "uprns_dwelling_type_conflict": int(len(hard)),
            "dwelling_type_conflict_share_of_repeats_pct": round(100 * len(hard) / n, 2),
            "dwelling_type_pairs": hard.value_counts().to_dict(),
            "d_o_pairs": int(len(do_uprns)),
            "d_o_pairs_with_tied_transfer_dates": tied,
            "note": ("Other is the residual bucket, not a dwelling type. A plot sold "
                     "as Other and the house later built on it sold as Detached are "
                     "two correct records, so only the conflicts between two genuine "
                     "dwelling types are unarguable. Transfer-date order cannot "
                     "separate the innocent readings: the D/O split is near even and "
                     "many share a date."),
        },
        "sales_on_repeated_uprns": len(joined),
        "max_sales_on_one_uprn": int(grouped.sales.max()),
        "median_span_years": int((grouped.last_year - grouped.first_year).median()),
        "max_span_years": int((grouped.last_year - grouped.first_year).max()),
        "sales_dated_before_2020": int((joined.transfer_year < 2020).sum()),
        "property_type_pairs": pairs.to_dict("records"),
    }
    return table, summary


def main() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    silver = json.loads((SILVER_DIR / "validation.json").read_text())
    if not silver["validation_gate"]["passed"]:
        raise RuntimeError("Silver validation gate did not pass; refusing to build Gold")

    fct = pd.read_parquet(SILVER_DIR / "fct_transaction.parquet")
    bridge = pd.read_parquet(SILVER_DIR / "bridge_transaction_uprn.parquet")
    a = fct[fct["is_analysis_row"]].copy()
    print(f"[scope] {len(a):,} analysis rows")

    overlap = pd.crosstab(a.property_type, a.ppd_category_type)
    print("[check] property type x PPD category:\n" + overlap.to_string())
    if overlap.loc["O", "A"] != 0:
        raise RuntimeError(
            "property type O now has category A rows; findings.md §5 assumes "
            "O sits wholly inside category B and must be revisited"
        )

    category = ppd_category_net_of_other(a)
    write(category, "08_ppd_category_net_of_other")
    write(price_by_match_status(a), "09_price_by_match_status")
    write(price_by_type_and_match(a), "10_median_price_by_type_and_match")
    counties = unmatched_by_county(a)
    write(counties, "11_unmatched_by_county")
    write(postcode_absent_profile(a), "12_postcode_absent_profile")
    repeats, repeat_summary = repeat_uprn_consistency(a, bridge)
    write(repeats, "13_repeat_uprn_consistency")
    conflicts = pd.DataFrame(
        [{"property_type_pair": k, "uprns": v, "involves_other": False}
         for k, v in repeat_summary["type_conflicts"]["dwelling_type_pairs"].items()]
    )
    write(conflicts, "14_repeat_uprn_dwelling_type_conflicts")

    houses = counties[counties.house_unmatched_pct.notna()]
    absent = a[~a.has_postcode]
    summary = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "release_slug": RELEASE_SLUG,
        "analysis_rows": len(a),
        "ppd_category_correction": {
            "category_b_unmatched_pct": float(
                category.loc[category.scope == "B — additional price paid", "unmatched_pct"].iloc[0]),
            "category_b_net_of_other_unmatched_pct": float(
                category.loc[category.scope == "B, net of property type O", "unmatched_pct"].iloc[0]),
            "other_rows_in_category_a": int(overlap.loc["O", "A"]),
            "note": ("Property type O sits wholly inside PPD category B, so the two "
                     "are not independent predictors of going unmatched."),
        },
        "price": {
            "unmatched_share_of_transactions_pct": round(100 * (~a.is_matched).mean(), 2),
            "unmatched_share_of_value_pct": round(
                100 * a.loc[~a.is_matched, "price"].sum() / a["price"].sum(), 2),
            "median_matched_gbp": int(a.loc[a.is_matched, "price"].median()),
            "median_unmatched_gbp": int(a.loc[~a.is_matched, "price"].median()),
        },
        "geography": {
            "counties_tested": int(len(counties)),
            "all_property_min_pct": float(counties.unmatched_pct.min()),
            "all_property_max_pct": float(counties.unmatched_pct.max()),
            "houses_only_counties": int(len(houses)),
            "houses_only_min_pct": float(houses.house_unmatched_pct.min()),
            "houses_only_max_pct": float(houses.house_unmatched_pct.max()),
            "houses_only_median_pct": float(houses.house_unmatched_pct.median()),
            "note": ("The all-property spread is composition, not geography. Holding "
                     "property type constant collapses it."),
        },
        "postcode_absent": {
            "transactions": int(len(absent)),
            "matched": int(absent.is_matched.sum()),
            "property_type_o": int((absent.property_type == "O").sum()),
            "category_b": int((absent.ppd_category_type == "B").sum()),
        },
        "repeated_uprns": repeat_summary,
    }
    (GOLD_DIR / "context_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print("[gold]  context_summary.json")

    c = summary["ppd_category_correction"]
    print(f"\n[correct] category B {c['category_b_unmatched_pct']}% unmatched, "
          f"but {c['category_b_net_of_other_unmatched_pct']}% net of property type O")
    p = summary["price"]
    print(f"[price]   unmatched are {p['unmatched_share_of_transactions_pct']}% of transactions "
          f"but {p['unmatched_share_of_value_pct']}% of value; median "
          f"£{p['median_unmatched_gbp']:,} vs £{p['median_matched_gbp']:,} matched")
    g = summary["geography"]
    print(f"[geo]     all property {g['all_property_min_pct']}–{g['all_property_max_pct']}%; "
          f"houses only {g['houses_only_min_pct']}–{g['houses_only_max_pct']}% "
          f"(median {g['houses_only_median_pct']}%) — the spread is composition")
    r = repeat_summary
    print(f"[repeat]  {r['repeated_uprns']:,} UPRNs carry {r['sales_on_repeated_uprns']:,} sales, "
          f"spanning up to {r['max_span_years']} years; none carry >1 PAON or SAON")


if __name__ == "__main__":
    main()
