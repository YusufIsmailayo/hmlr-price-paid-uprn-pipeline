"""
Render the figures page from the Gold tables.

Every number on the published page — the chart data, the stat tiles, and the
figures quoted in the prose — is read from data/gold and data/silver here and
substituted into templates/figures.html.template. Nothing is typed by hand, so
the page cannot drift from the pipeline: re-run Gold, re-run this, and the
prose moves with the tables.

The template is plain HTML with {{TOKEN}} placeholders. A leftover token in the
output raises rather than shipping a page with "{{CRUDE_RR}}" in the middle of
a sentence.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_SLUG = "release_2026-08-28"
GOLD_DIR = REPO_ROOT / "data" / "gold" / RELEASE_SLUG
SILVER_DIR = REPO_ROOT / "data" / "silver" / RELEASE_SLUG
TEMPLATE = Path(__file__).resolve().parent / "templates" / "figures.html.template"
OUT_PATH = REPO_ROOT / "docs" / "figures.html"

# Row order on the charts: the argument reads houses first, because that is
# where the new-build effect lives, then flats, then the outlier.
STRATUM_ORDER = ["S", "T", "D", "F", "O"]
STRATUM_LABELS = {
    "S": "Semi-detached", "T": "Terraced", "D": "Detached",
    "F": "Flat / maisonette", "O": "Other — land / garages",
}
SUPERSCRIPT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def pct(v: float) -> str:
    return f"{v:.2f}%"


def sci(p: float) -> str:
    """1.83e-70 -> '1.8 × 10⁻⁷⁰'."""
    mantissa, exponent = f"{p:.1e}".split("e")
    return f"{mantissa} × 10{str(int(exponent)).translate(SUPERSCRIPT)}"


def load() -> tuple[dict, dict]:
    gold = json.loads((GOLD_DIR / "summary.json").read_text())
    silver = json.loads((SILVER_DIR / "validation.json").read_text())
    return gold, silver


def chart_data(gold: dict) -> dict:
    by_type = pd.read_csv(GOLD_DIR / "03_unmatched_by_property_type.csv")
    by_new = pd.read_csv(GOLD_DIR / "04_unmatched_by_new_build.csv")
    strata = {s["stratum"]: s for s in
              gold["new_build_effect"]["adjusted_for_property_type"]["strata"]}
    cross = pd.read_csv(GOLD_DIR / "06_unmatched_by_property_type_and_new_build.csv")
    ci = {row["label"]: row for _, row in cross.iterrows()}

    fig1 = [
        {"label": STRATUM_LABELS.get(r.property_type, r.label), "pct": r.unmatched_pct,
         "n": int(r.transactions), "lo": r.unmatched_ci_low_pct, "hi": r.unmatched_ci_high_pct}
        for _, r in by_type.iterrows()
    ]

    source_labels = by_type.set_index("property_type")["label"].to_dict()

    def cell(prop: str, arm: str) -> dict:
        """arm is 'Established' or 'New build'; CI comes from the 06 cut."""
        row = ci[f"{source_labels[prop]} · {arm}"]
        return {"pct": row["unmatched_pct"], "n": int(row["transactions"]),
                "lo": row["unmatched_ci_low_pct"], "hi": row["unmatched_ci_high_pct"]}

    overall = {arm: by_new[by_new.label == arm].iloc[0] for arm in ("Established", "New build")}
    fig2 = [{
        "label": "All transactions", "rule": True,
        "est": {"pct": overall["Established"].unmatched_pct,
                "n": int(overall["Established"].transactions),
                "lo": overall["Established"].unmatched_ci_low_pct,
                "hi": overall["Established"].unmatched_ci_high_pct},
        "nb": {"pct": overall["New build"].unmatched_pct,
               "n": int(overall["New build"].transactions),
               "lo": overall["New build"].unmatched_ci_low_pct,
               "hi": overall["New build"].unmatched_ci_high_pct},
    }] + [
        {"label": STRATUM_LABELS[p], "est": cell(p, "Established"), "nb": cell(p, "New build")}
        for p in STRATUM_ORDER
    ]

    houses = {"S", "T", "D"}
    fig3 = [r for r in fig2 if r["label"] in {STRATUM_LABELS[p] for p in houses}]

    crude = gold["new_build_effect"]["crude"]
    fig4 = [{
        "label": "All transactions", "crude": True,
        "rr": round(crude["crude_risk_ratio"], 2),
        "lo": crude["ci_low"], "hi": crude["ci_high"],
    }] + [
        {"label": STRATUM_LABELS[p], "rr": strata[p]["stratum_risk_ratio"],
         "lo": strata[p]["stratum_rr_ci_low"], "hi": strata[p]["stratum_rr_ci_high"]}
        for p in STRATUM_ORDER
    ]
    return {"fig1": fig1, "fig2": fig2, "fig3": fig3, "fig4": fig4}


def tokens(gold: dict, silver: dict, data: dict) -> dict:
    by_type = {r["label"]: r for r in data["fig1"]}
    other, semi = by_type["Other — land / garages"], by_type["Semi-detached"]
    strata = {s["stratum"]: s for s in
              gold["new_build_effect"]["adjusted_for_property_type"]["strata"]}
    adjusted = gold["new_build_effect"]["adjusted_for_property_type"]
    het = adjusted["heterogeneity"]
    crude = gold["new_build_effect"]["crude"]
    cardinality = silver["grain_and_cardinality"]["cardinality_uprn_to_transaction"]
    gate = silver["validation_gate"]
    cramers = {t["variable"]: t["cramers_v"] for t in gold["independence"]}

    est_total = sum(r["est"]["n"] for r in data["fig2"] if not r.get("rule"))
    nb_total = sum(r["nb"]["n"] for r in data["fig2"] if not r.get("rule"))
    other_row = next(r for r in data["fig2"] if r["label"] == "Other — land / garages")

    return {
        "PUBLICATION_DATE": "28 August 2026",
        "DATA_MONTH": datetime.strptime(gate["reconciliation_month"], "%Y-%m").strftime("%B %Y"),
        "ANALYSIS_N": f"{gold['analysis_rows']:,}",
        "RELEASE_N": f"{gold['analysis_rows'] + gold['deletions_excluded']:,}",
        "DELETIONS_N": f"{gold['deletions_excluded']:,}",
        "UNMATCHED_PCT": pct(gold["unmatched_pct"]),
        "TILE_OTHER_PCT": f"{other['pct']:.1f}%",
        "TILE_SEMI_PCT": f"{semi['pct']:.1f}%",
        "MANY_UPRN": f"{gold['cardinality']['many_uprns']:,}",
        "OTHER_VS_SEMI": f"{other['pct'] / semi['pct']:.0f}",
        "CRAMERS_PROPERTY": f"{cramers['property_type']}",
        "NB_PCT": pct(crude["exposed_unmatched_pct"]),
        "EST_PCT": pct(crude["unexposed_unmatched_pct"]),
        "CRUDE_RR": f"{crude['crude_risk_ratio']:.2f}",
        "CRAMERS_OLDNEW": f"{cramers['old_new']}",
        "OTHER_SHARE_EST": f"{100 * other_row['est']['n'] / est_total:.1f}%",
        "OTHER_SHARE_NB": f"{100 * other_row['nb']['n'] / nb_total:.1f}%",
        "SEMI_RR": f"{strata['S']['stratum_risk_ratio']:.1f}",
        "Q": f"{het['cochran_q']}",
        "DOF": f"{het['dof']}",
        "P_SCI": sci(het["p_value"]),
        "RR_MIN": f"{het['stratum_risk_ratio_min']}",
        "RR_MAX": f"{het['stratum_risk_ratio_max']}",
        "MH_RR": f"{adjusted['adjusted_risk_ratio']:.2f}",
        "GATE_N": f"{gate['actual']:,}",
        "REPEAT_UPRNS": f"{cardinality['uprns_with_multiple_transactions']:,}",
        "MAX_TX_PER_UPRN": f"{cardinality['max_transactions_per_uprn']}",
        "GENERATED_AT": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "DATA_JSON": json.dumps(data, separators=(",", ":")),
    }


def main() -> None:
    gold, silver = load()
    if not silver["validation_gate"]["passed"]:
        raise RuntimeError("Silver validation gate did not pass; refusing to publish figures")

    data = chart_data(gold)
    values = tokens(gold, silver, data)

    html = TEMPLATE.read_text()
    html = re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: values[m.group(1)], html)

    leftover = re.findall(r"\{\{[A-Z_]+\}\}", html)
    if leftover:
        raise RuntimeError(f"unsubstituted tokens remain: {sorted(set(leftover))}")

    OUT_PATH.write_text(html)
    print(f"[report] {OUT_PATH.relative_to(REPO_ROOT)} ({len(html):,} bytes)")
    for key in ("UNMATCHED_PCT", "TILE_OTHER_PCT", "CRUDE_RR", "SEMI_RR", "GATE_N", "MANY_UPRN"):
        print(f"[report]   {key} = {values[key]}")


if __name__ == "__main__":
    main()
