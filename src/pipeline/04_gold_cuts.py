"""
Gold: match-rate and bias tables.

The question this pipeline exists to answer is whether the sales the UPRN
look-up cannot match are randomly distributed, and if not, in which direction
and by how much. HMLR publishes no official match rate, so every figure here
is computed from the raw files by this repo.

Method notes that matter for reading the output:

* Denominator excludes record status D. All 1,514 deletions are unmatched by
  construction — the look-up covers live records only — so including them
  measures the pipeline's own bookkeeping rather than HMLR's matching.

* Rates carry Wilson score 95% intervals. With ~100k rows the intervals are
  narrow, but the small cells (new-build "Other", n=153) are exactly where a
  bare percentage would mislead.

* Risk ratios compare each group against its complement, with log-method
  intervals.

* The new-build effect is reported crude AND stratified by property type,
  using a Mantel-Haenszel adjusted risk ratio with Greenland-Robins variance.
  The crude and adjusted figures disagree, and that disagreement is the
  finding — see docs/findings.md.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from scipy.stats import chi2, chi2_contingency

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_SLUG = "release_2026-08-28"
SILVER_DIR = REPO_ROOT / "data" / "silver" / RELEASE_SLUG
GOLD_DIR = REPO_ROOT / "data" / "gold" / RELEASE_SLUG

Z = 1.959963984540054  # 95%

PROPERTY_TYPE_LABELS = {
    "D": "Detached", "S": "Semi-detached", "T": "Terraced",
    "F": "Flat / maisonette", "O": "Other — land / garages / non-residential",
}
OLD_NEW_LABELS = {"Y": "New build", "N": "Established"}
PPD_CATEGORY_LABELS = {"A": "A — standard price paid", "B": "B — additional price paid"}


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + Z * Z / n
    centre = p + Z * Z / (2 * n)
    spread = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n))
    return ((centre - spread) / denom, (centre + spread) / denom)


def risk_ratio(a: int, n1: int, b: int, n0: int) -> tuple[float, float, float]:
    """Unmatched risk in the group vs its complement, with a log-method CI."""
    if not (n1 and n0 and a and b):
        return (float("nan"),) * 3
    rr = (a / n1) / (b / n0)
    se = math.sqrt(1 / a - 1 / n1 + 1 / b - 1 / n0)
    return (rr, rr * math.exp(-Z * se), rr * math.exp(Z * se))


def breakdown(df: pd.DataFrame, column: str, labels: dict | None = None) -> pd.DataFrame:
    """Unmatched share by group, with intervals and risk vs the complement."""
    total_n, total_unmatched = len(df), int((~df["is_matched"]).sum())
    rows = []
    for value, group in df.groupby(column, dropna=False):
        n = len(group)
        unmatched = int((~group["is_matched"]).sum())
        lo, hi = wilson(unmatched, n)
        rr, rr_lo, rr_hi = risk_ratio(
            unmatched, n, total_unmatched - unmatched, total_n - n
        )
        rows.append({
            column: value,
            "label": (labels or {}).get(value, value),
            "transactions": n,
            "share_of_all_transactions_pct": round(100 * n / total_n, 2),
            "matched": n - unmatched,
            "unmatched": unmatched,
            "unmatched_pct": round(100 * unmatched / n, 2),
            "unmatched_ci_low_pct": round(100 * lo, 2),
            "unmatched_ci_high_pct": round(100 * hi, 2),
            "risk_ratio_vs_rest": round(rr, 2),
            "risk_ratio_ci_low": round(rr_lo, 2),
            "risk_ratio_ci_high": round(rr_hi, 2),
        })
    return pd.DataFrame(rows).sort_values("unmatched_pct", ascending=False)


def mantel_haenszel(df: pd.DataFrame, exposure: str, positive: str, stratify_by: str) -> dict:
    """
    Adjusted risk ratio for `exposure == positive` on being unmatched,
    pooled across strata. Greenland-Robins variance.
    """
    numer = denom = var_num = 0.0
    strata = []
    for level, stratum in df.groupby(stratify_by):
        exposed = stratum[stratum[exposure] == positive]
        unexposed = stratum[stratum[exposure] != positive]
        n1, n0 = len(exposed), len(unexposed)
        n = n1 + n0
        if not (n1 and n0):
            continue
        a = int((~exposed["is_matched"]).sum())
        b = int((~unexposed["is_matched"]).sum())
        numer += a * n0 / n
        denom += b * n1 / n
        var_num += (n1 * n0 * (a + b) - a * b * n) / (n * n)
        strata.append({
            "stratum": level,
            "exposed_n": n1, "exposed_unmatched_pct": round(100 * a / n1, 2),
            "unexposed_n": n0, "unexposed_unmatched_pct": round(100 * b / n0, 2),
            "stratum_risk_ratio": round((a / n1) / (b / n0), 2) if b else None,
            "_var": (1 / a - 1 / n1 + 1 / b - 1 / n0) if (a and b) else None,
        })
        if strata[-1]["_var"] is not None:
            srr = (a / n1) / (b / n0)
            sse = math.sqrt(strata[-1]["_var"])
            strata[-1]["stratum_rr_ci_low"] = round(srr * math.exp(-Z * sse), 2)
            strata[-1]["stratum_rr_ci_high"] = round(srr * math.exp(Z * sse), 2)

    rr = numer / denom
    se = math.sqrt(var_num / (numer * denom))

    # Cochran's Q on the log risk ratios. A pooled estimate is only meaningful
    # if the strata are estimating the same effect; if Q rejects, the pooled
    # figure is an average of things that genuinely differ and the
    # stratum-specific table is the honest presentation.
    logs = [(math.log(s["stratum_risk_ratio"]), s["_var"])
            for s in strata if s["stratum_risk_ratio"]]
    weights = [1 / v for _, v in logs]
    pooled_iv = sum(w * l for (l, _), w in zip(logs, weights)) / sum(weights)
    q = sum(w * (l - pooled_iv) ** 2 for (l, _), w in zip(logs, weights))
    dof = len(logs) - 1
    q_p = float(chi2.sf(q, dof)) if dof else float("nan")
    for s in strata:
        s.pop("_var", None)

    ratios = [s["stratum_risk_ratio"] for s in strata if s["stratum_risk_ratio"]]
    return {
        "exposure": f"{exposure} == {positive}",
        "stratified_by": stratify_by,
        "adjusted_risk_ratio": round(rr, 3),
        "ci_low": round(rr * math.exp(-Z * se), 3),
        "ci_high": round(rr * math.exp(Z * se), 3),
        "heterogeneity": {
            "cochran_q": round(q, 1),
            "dof": dof,
            "p_value": q_p,
            "stratum_risk_ratio_min": min(ratios),
            "stratum_risk_ratio_max": max(ratios),
            "pooling_appropriate": bool(q_p > 0.05),
            "note": (
                "Stratum effects differ, so the pooled adjusted risk ratio is a "
                "weighted average of genuinely different effects and should not "
                "be quoted as 'the' new-build effect. Report the strata."
            ) if q_p <= 0.05 else "Strata consistent; pooled estimate is interpretable.",
        },
        "strata": strata,
    }


def crude_rr(df: pd.DataFrame, column: str, positive: str) -> dict:
    exposed = df[df[column] == positive]
    unexposed = df[df[column] != positive]
    a, n1 = int((~exposed["is_matched"]).sum()), len(exposed)
    b, n0 = int((~unexposed["is_matched"]).sum()), len(unexposed)
    rr, lo, hi = risk_ratio(a, n1, b, n0)
    return {
        "exposure": f"{column} == {positive}",
        "exposed_unmatched_pct": round(100 * a / n1, 2),
        "unexposed_unmatched_pct": round(100 * b / n0, 2),
        "crude_risk_ratio": round(rr, 3),
        "ci_low": round(lo, 3), "ci_high": round(hi, 3),
    }


def independence_test(df: pd.DataFrame, column: str) -> dict:
    table = pd.crosstab(df[column], df["is_matched"])
    chi2, p, dof, _ = chi2_contingency(table)
    n = int(table.values.sum())
    return {
        "variable": column,
        "chi2": round(float(chi2), 1),
        "dof": int(dof),
        "p_value": float(p),
        "cramers_v": round(math.sqrt(chi2 / (n * min(table.shape[0] - 1, table.shape[1] - 1))), 3),
        "note": "with n≈100k, significance is assured; the effect sizes carry the argument",
    }


def write(df: pd.DataFrame, name: str) -> None:
    df.to_csv(GOLD_DIR / f"{name}.csv", index=False)
    print(f"[gold]  {name}.csv ({len(df)} rows)")


def main() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    fct = pd.read_parquet(SILVER_DIR / "fct_transaction.parquet")
    silver = json.loads((SILVER_DIR / "validation.json").read_text())
    if not silver["validation_gate"]["passed"]:
        raise RuntimeError("Silver validation gate did not pass; refusing to build Gold")

    analysis = fct[fct["is_analysis_row"]].copy()
    print(f"[scope] {len(analysis):,} analysis rows of {len(fct):,} "
          f"({len(fct) - len(analysis):,} deletions excluded)")

    # 1. Headline, and what the deletion decision is worth ------------------
    headline = pd.DataFrame([
        {"scope": "All rows in the monthly release", "transactions": len(fct),
         "matched": int(fct["is_matched"].sum()),
         "unmatched": int((~fct["is_matched"]).sum()),
         "unmatched_pct": round(100 * (~fct["is_matched"]).mean(), 2)},
        {"scope": "Analysis scope (deletions excluded)", "transactions": len(analysis),
         "matched": int(analysis["is_matched"].sum()),
         "unmatched": int((~analysis["is_matched"]).sum()),
         "unmatched_pct": round(100 * (~analysis["is_matched"]).mean(), 2)},
    ])
    write(headline, "01_match_rate_headline")

    # 2. The cardinality table ---------------------------------------------
    cardinality = pd.DataFrame([
        {"cardinality": "0 UPRNs", "meaning":
            "Unmatched — no PAF entry / land only / garage / incomplete address",
         "transactions": int((analysis["uprn_count"] == 0).sum()),
         "effect_on_fact_table": "Dropped silently by an inner join"},
        {"cardinality": "1 UPRN", "meaning": "Clean one-to-one match",
         "transactions": int((analysis["uprn_count"] == 1).sum()),
         "effect_on_fact_table": "Grain preserved"},
        {"cardinality": ">1 UPRN", "meaning":
            "One transaction covering several addressable locations",
         "transactions": int((analysis["uprn_count"] > 1).sum()),
         "effect_on_fact_table":
            "Would inflate row count on a left join — does not occur in this release"},
    ])
    write(cardinality, "02_cardinality")

    # 3-6. Bias breakdowns --------------------------------------------------
    write(breakdown(analysis, "property_type", PROPERTY_TYPE_LABELS),
          "03_unmatched_by_property_type")
    write(breakdown(analysis, "old_new", OLD_NEW_LABELS),
          "04_unmatched_by_new_build")
    write(breakdown(analysis, "ppd_category_type", PPD_CATEGORY_LABELS),
          "05_unmatched_by_ppd_category")

    stratified = breakdown(
        analysis.assign(
            property_type_x_new_build=analysis["property_type"].map(PROPERTY_TYPE_LABELS)
            + " · " + analysis["old_new"].map(OLD_NEW_LABELS)
        ),
        "property_type_x_new_build",
    )
    write(stratified, "06_unmatched_by_property_type_and_new_build")

    postcode = breakdown(
        analysis.assign(postcode_present=analysis["has_postcode"].map(
            {True: "Postcode present", False: "Postcode absent"})),
        "postcode_present",
    )
    write(postcode, "07_unmatched_by_postcode_presence")

    # 7. Effect sizes -------------------------------------------------------
    summary = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "release_slug": RELEASE_SLUG,
        "analysis_rows": len(analysis),
        "deletions_excluded": len(fct) - len(analysis),
        "unmatched_pct": round(100 * (~analysis["is_matched"]).mean(), 2),
        "cardinality": {
            "zero_uprns": int((analysis["uprn_count"] == 0).sum()),
            "one_uprn": int((analysis["uprn_count"] == 1).sum()),
            "many_uprns": int((analysis["uprn_count"] > 1).sum()),
        },
        "independence": [independence_test(analysis, c)
                         for c in ("property_type", "old_new", "ppd_category_type")],
        "new_build_effect": {
            "crude": crude_rr(analysis, "old_new", "Y"),
            "adjusted_for_property_type": mantel_haenszel(
                analysis, "old_new", "Y", "property_type"),
        },
    }
    (GOLD_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print("[gold]  summary.json")

    nb = summary["new_build_effect"]
    print(f"\n[effect] new build, crude RR      {nb['crude']['crude_risk_ratio']} "
          f"({nb['crude']['ci_low']}–{nb['crude']['ci_high']})")
    adj = nb["adjusted_for_property_type"]
    print(f"[effect] new build, adjusted RR   {adj['adjusted_risk_ratio']} "
          f"({adj['ci_low']}–{adj['ci_high']}) stratified by property type")
    het = adj["heterogeneity"]
    print(f"[effect] heterogeneity Q={het['cochran_q']} df={het['dof']} "
          f"p={het['p_value']:.3g} | stratum RRs "
          f"{het['stratum_risk_ratio_min']}–{het['stratum_risk_ratio_max']} | "
          f"pooling appropriate: {het['pooling_appropriate']}")


if __name__ == "__main__":
    main()
