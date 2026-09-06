"""Forensic attribution of empty-supplier and unclassified rows (GH#10).

Proposes recoveries for two kinds of gaps in a staged frame:

* ``supplier`` — rows whose supplier cell is empty. Methods, by evidence
  strength: a known supplier name appearing inside the row text
  (``substring``); a twin attributed row — same amount and similar item —
  paying the same order (``twin_row``); a supplier that overwhelmingly
  dominates the row's cost category (``category_dominance``).
* ``stage`` — rows left ``unclassified`` (dominant stage of the same
  supplier, ``supplier_stage``) and mold-deposit lines the keyword
  classifier misplaced (``stage_hint``).

Every proposal carries concrete evidence read from the data; rows without
evidence are left untouched. Nothing is applied automatically — the output
is a review list.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pandas as pd

from action_figures.attribution import application_rows

UNCLASSIFIED = "unclassified"

PROPOSAL_COLUMNS = [
    "line_id", "field", "current", "proposed", "confidence", "method", "evidence",
]

CONF_RANK = {"high": 3, "medium": 2, "low": 1}
METHOD_PRIORITY = {"substring": 30, "twin_row": 20, "category_dominance": 10}

# Sourcing channels recorded in the supplier column — real counterpart names
# never surface as text hits for these.
CHANNEL_SUPPLIERS = {"外购", "外发"}

# Twin (counterpart) rules.
MIN_TWIN_AMOUNT = 100.0  # petty amounts coincide by luck, not by identity
NEAR_AMOUNT_RATIO = 0.98
TWIN_MIN_SCORE = 4
TWIN_HIGH_SCORE = 5

# Category dominance rules: (category, item keywords).
CATEGORY_RULES = (
    ("design_drawing", ("画图",)),
    ("sampling_prototypes", ("样办", "做办", "做样")),
)
DOMINANT_SHARE = 0.8
DOMINANT_MIN_ROWS = 5
PERFECT_MIN_ROWS = 3  # 100% share with a small pool still earns a low proposal
STAGE_LOW_SHARE = 0.6  # low tier of supplier_stage; needs DOMINANT_MIN_ROWS too

# Audit-local stage hints (vocabulary the taxonomy misses).
MOLD_KEYWORDS = ("合金模", "塑胶模", "模定金", "模订金", "开模")

# Why a remaining empty-supplier row cannot be attributed (report text).
REASON_RULES = (
    (("合金模", "塑胶模", "模定金", "模订金", "木头枪", "木枪"),
     "prepayment for molds / wood tooling — counterparty never named in the "
     "data (tail payments fall outside the data window)"),
    (("油费", "高速费", "出差"),
     "travel / fuel overhead — these rows never carry a supplier in this ledger"),
    (("寄件", "快递"),
     "outgoing courier — carrier identity not recoverable from the text"),
    (("餐", "饮茶", "年饭"),
     "meals / entertainment — no supplier by design"),
    (("尾款", "货款", "定金", "订金"),
     "payment without a counterpart row in the data"),
)

_MONTH_RE = re.compile(r"^(\d{4})-(\d{1,2})$")


# --- text helpers --------------------------------------------------------

def _s(value) -> str:
    """Scalar -> stripped string; NaN/None -> empty string."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _is_zh(ch: str) -> bool:
    return "一" <= ch <= "鿿"


def zh_bigrams(text) -> set[str]:
    """Chinese-character bigrams of a string — robust item similarity unit."""
    t = _s(text)
    return {t[i : i + 2] for i in range(len(t) - 1) if _is_zh(t[i]) and _is_zh(t[i + 1])}


def normalize_style(value) -> set[str]:
    """Style tokens: split on '/', drop the UD prefix and float tails.

    ``UD9062`` and ``9062.0`` both reduce to ``{"9062"}`` so mixed sheet
    conventions still overlap.
    """
    tokens: set[str] = set()
    for tok in _s(value).split("/"):
        tok = tok.strip()
        if tok.endswith(".0"):
            tok = tok[:-2]
        if tok[:2].upper() == "UD" and len(tok) > 2:
            tok = tok[2:]
        if any(c.isdigit() for c in tok):
            tokens.add(tok)
    return tokens


def month_distance(a, b) -> int | None:
    """Distance in months between ``YYYY-M`` strings, or None if unparseable."""
    ma, mb = _MONTH_RE.match(_s(a)), _MONTH_RE.match(_s(b))
    if not (ma and mb):
        return None
    ya, moa = int(ma.group(1)), int(ma.group(2))
    yb, mob = int(mb.group(1)), int(mb.group(2))
    return abs((yb * 12 + mob) - (ya * 12 + moa))


def _amount(rec: dict) -> float:
    try:
        return float(rec.get("amount") or 0.0)
    except (TypeError, ValueError):
        return 0.0


# --- supplier recovery methods ------------------------------------------

def find_substring(rec: dict, known_suppliers: set[str]) -> dict | None:
    """A known supplier name literally appears in the row's text fields."""
    hits: list[tuple[str, str]] = []
    for col in ("item", "purpose", "remarks"):
        text = _s(rec.get(col))
        for name in known_suppliers:
            if len(name) >= 2 and name in text:
                hits.append((name, col))
    if not hits:
        return None
    name, col = max(hits, key=lambda h: (len(h[0]), h[0]))
    return {
        "proposed": name,
        "confidence": "medium" if len(name) <= 2 else "high",
        "evidence": f"supplier name '{name}' appears in {col}",
    }


def _twin_score(rec: dict, other: dict) -> tuple[int, list[str]]:
    """Similarity score between an empty row and an attributed row.

    Gates on content similarity (amount signal or shared bigrams) so rows
    that merely share a month never match.
    """
    score = 0
    facts: list[str] = []
    a1, a2 = _amount(rec), _amount(other)
    amount_signal = 0
    if a1 >= MIN_TWIN_AMOUNT and a2 >= MIN_TWIN_AMOUNT:
        if a1 == a2:
            amount_signal = 2
            facts.append(f"same amount {a1:,.2f}")
        elif min(a1, a2) / max(a1, a2) >= NEAR_AMOUNT_RATIO:
            amount_signal = 1
            facts.append(f"near amount {a1:,.2f} ~ {a2:,.2f}")
    bg = zh_bigrams(rec.get("item")) & zh_bigrams(other.get("item"))
    if len(bg) >= 4:
        score += 2
    elif len(bg) >= 2:
        score += 1
    if bg:
        facts.append(f"{len(bg)} shared item bigrams")
    if not amount_signal and not bg:
        return 0, facts
    score += amount_signal
    if normalize_style(rec.get("style_no")) & normalize_style(other.get("style_no")):
        score += 1
        facts.append("same style")
    if _s(rec.get("purpose")) and _s(rec.get("purpose")) == _s(other.get("purpose")):
        score += 1
        facts.append("same purpose")
    if _s(rec.get("remarks")) and _s(rec.get("remarks")) == _s(other.get("remarks")):
        score += 1
        facts.append("same remarks")
    dist = month_distance(rec.get("month"), other.get("month"))
    if dist is not None and dist <= 3:
        score += 1
        facts.append(f"months {dist} apart")
    return score, facts


def find_twin(rec: dict, attr_records: list[dict]) -> dict | None:
    """Best twin (counterpart) attributed row for an empty-supplier row.

    Twin candidates sourced through a channel (外购/外发) are skipped: a
    channel is not a counterparty name, and the twin method exists to name
    counterparties. (category_dominance may still propose a channel — there
    the channel is the recorded answer for the whole category.)
    """
    if _s(rec.get("stage")) == "logistics_freight":
        return None  # courier identity is not inferable from equal freight lines
    best_score = 0
    best: tuple[str, str, list[str]] | None = None
    tied_suppliers: set[str] = set()
    for other in attr_records:
        supplier = _s(other.get("supplier"))
        if supplier in CHANNEL_SUPPLIERS:
            continue
        score, facts = _twin_score(rec, other)
        if score < TWIN_MIN_SCORE:
            continue
        if score > best_score:
            best_score = score
            best = (supplier, _s(other.get("line_id")), facts)
            tied_suppliers = {supplier}
        elif score == best_score:
            tied_suppliers.add(supplier)
    if best is None or len(tied_suppliers) != 1:
        return None  # no twin, or equally good twins with different suppliers
    supplier, twin_id, facts = best
    # Only an exact-amount counterpart is strong enough for "high": a twin
    # matched on text alone may be a sibling line of the same order, not the
    # paired payment.
    exact_amount = any(f.startswith("same amount") for f in facts)
    confidence = (
        "high" if best_score >= TWIN_HIGH_SCORE and exact_amount else "medium"
    )
    return {
        "proposed": supplier,
        "confidence": confidence,
        "evidence": f"twin line {twin_id}: " + "; ".join(facts),
    }


def find_category_dominance(rec: dict, attr_records: list[dict]) -> dict | None:
    """One supplier overwhelmingly serves the row's cost category."""
    item = _s(rec.get("item"))
    for category, keywords in CATEGORY_RULES:
        if not any(kw in item for kw in keywords):
            continue
        pool = [
            r for r in attr_records
            if any(kw in _s(r.get("item")) for kw in keywords)
        ]
        n = len(pool)
        if not n:
            continue
        supplier, k = Counter(_s(r.get("supplier")) for r in pool).most_common(1)[0]
        share = k / n
        if share >= DOMINANT_SHARE and n >= DOMINANT_MIN_ROWS:
            confidence = "medium"
        elif share == 1.0 and n >= PERFECT_MIN_ROWS:
            confidence = "low"
        else:
            continue
        return {
            "proposed": supplier,
            "confidence": confidence,
            "evidence": (
                f"category '{category}': supplier '{supplier}' serves "
                f"{k}/{n} attributed rows ({share:.0%})"
            ),
        }
    return None


def _supplier_candidate(rec, attr_records, known_suppliers):
    candidates = []
    for method, finder in (
        ("substring", lambda: find_substring(rec, known_suppliers)),
        ("twin_row", lambda: find_twin(rec, attr_records)),
        ("category_dominance", lambda: find_category_dominance(rec, attr_records)),
    ):
        found = finder()
        if found:
            candidates.append((method, found))
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda mf: (CONF_RANK[mf[1]["confidence"]], METHOD_PRIORITY[mf[0]]),
    )


# --- stage recovery methods ---------------------------------------------

def find_stage_by_supplier(rec: dict, attr_records: list[dict]) -> dict | None:
    """Unclassified row with a supplier: dominant stage of that supplier.

    Both tiers require at least ``DOMINANT_MIN_ROWS`` attributed rows —
    even a low-confidence proposal must rest on a defensible pool, and a
    2-of-3 majority is not one.
    """
    supplier = _s(rec.get("supplier"))
    if _s(rec.get("stage")) != UNCLASSIFIED or not supplier:
        return None
    pool = [
        r for r in attr_records
        if _s(r.get("supplier")) == supplier and _s(r.get("stage")) != UNCLASSIFIED
    ]
    n = len(pool)
    if n < DOMINANT_MIN_ROWS:
        return None
    stage, k = Counter(_s(r.get("stage")) for r in pool).most_common(1)[0]
    share = k / n
    if share >= DOMINANT_SHARE:
        confidence = "medium"
    elif share >= STAGE_LOW_SHARE:
        confidence = "low"
    else:
        return None
    return {
        "proposed": stage,
        "confidence": confidence,
        "evidence": (
            f"supplier '{supplier}': {k}/{n} attributed rows are "
            f"'{stage}' ({share:.0%})"
        ),
    }


def find_stage_hint(rec: dict) -> dict | None:
    """Item names a mold purchase/deposit but the stage is not tooling."""
    item = _s(rec.get("item"))
    hit = next((kw for kw in MOLD_KEYWORDS if kw in item), None)
    if hit is None or _s(rec.get("stage")) == "tooling_molds":
        return None
    return {
        "proposed": "tooling_molds",
        "confidence": "medium",
        "evidence": f"item contains '{hit}' (mold purchase/deposit vocabulary)",
    }


# --- proposal assembly ---------------------------------------------------

def build_proposals(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Build the review list for one staged frame.

    Returns ``(proposals, stats)``: proposals follow ``PROPOSAL_COLUMNS``;
    stats carry the recovery totals used by the report.
    """
    records = df.to_dict("records")
    attr = [r for r in records if _s(r.get("supplier"))]
    known = {_s(r.get("supplier")) for r in attr} - CHANNEL_SUPPLIERS - {""}

    proposals: list[dict] = []
    for rec in records:
        line_id = _s(rec.get("line_id"))
        if not _s(rec.get("supplier")):
            candidate = _supplier_candidate(rec, attr, known)
            if candidate:
                method, found = candidate
                proposals.append({
                    "line_id": line_id,
                    "field": "supplier",
                    "current": "",
                    "proposed": found["proposed"],
                    "confidence": found["confidence"],
                    "method": method,
                    "evidence": found["evidence"],
                })
        # stage: explicit vocabulary beats supplier statistics
        hint = find_stage_hint(rec)
        found = hint or find_stage_by_supplier(rec, attr)
        if found:
            proposals.append({
                "line_id": line_id,
                "field": "stage",
                "current": _s(rec.get("stage")),
                "proposed": found["proposed"],
                "confidence": found["confidence"],
                "method": "stage_hint" if hint is found else "supplier_stage",
                "evidence": found["evidence"],
            })

    proposals.sort(key=lambda p: (p["line_id"], p["field"]))
    prop_df = pd.DataFrame(proposals, columns=PROPOSAL_COLUMNS)
    return prop_df, _stats(df, prop_df)


def _stats(df: pd.DataFrame, prop_df: pd.DataFrame) -> dict:
    amounts = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    empty = df["supplier"].fillna("").astype(str).str.strip() == ""
    empty_total = float(amounts[empty].sum())
    amount_by_id = dict(zip(df["line_id"].astype(str), amounts, strict=True))

    supplier = prop_df[prop_df["field"] == "supplier"] if len(prop_df) else prop_df
    by_confidence = {}
    for conf in ("high", "medium", "low"):
        rows = supplier[supplier["confidence"] == conf]
        by_confidence[conf] = {
            "rows": int(len(rows)),
            "amount": float(sum(amount_by_id.get(str(x), 0.0) for x in rows["line_id"])),
        }
    recovered = by_confidence["high"]["amount"] + by_confidence["medium"]["amount"]
    # Structural ceiling: prepayments whose counterpart is never named in the
    # data (mold / wood tooling deposits with tails outside the window).
    attributed_ids = set(
        prop_df[prop_df["field"] == "supplier"]["line_id"].astype(str)
    ) if len(prop_df) else set()
    structural = float(sum(
        amt
        for is_empty, lid, amt, item in zip(
            empty, df["line_id"].astype(str), amounts, df["item"].astype(str),
            strict=False,
        )
        if is_empty and lid not in attributed_ids
        and _left_reason(item).startswith("prepayment")
    ))
    addressable = empty_total - structural
    return {
        "total_rows": int(len(df)),
        "empty_supplier_rows": int(empty.sum()),
        "empty_supplier_amount": empty_total,
        "unclassified_rows": int((df["stage"].astype(str) == UNCLASSIFIED).sum()),
        "supplier_by_confidence": by_confidence,
        "recovered_medium_plus_amount": recovered,
        "recovered_medium_plus_share": recovered / empty_total if empty_total else 0.0,
        "structural_unattributable_amount": structural,
        "addressable_amount": addressable,
        "recovered_share_addressable": recovered / addressable if addressable else 0.0,
        "stage_proposals": int((prop_df["field"] == "stage").sum()) if len(prop_df) else 0,
    }


# --- report rendering ----------------------------------------------------

def _left_reason(item: str) -> str:
    for keywords, why in REASON_RULES:
        if any(kw in item for kw in keywords):
            return why
    return "no counterpart evidence in the data"


def _report_md(prop_df: pd.DataFrame, stats: dict, df: pd.DataFrame) -> str:
    by_conf = stats["supplier_by_confidence"]
    total = stats["empty_supplier_amount"]
    md = [
        "# Attribution audit — empty suppliers & unclassified lines",
        "",
        f"- Scope: **{stats['total_rows']}** staged rows. Empty supplier: "
        f"**{stats['empty_supplier_rows']}** lines (**¥{total:,.2f}**). "
        f"Unclassified: **{stats['unclassified_rows']}** lines.",
        f"- Proposals: **{len(prop_df)}** "
        f"({int((prop_df['field'] == 'stage').sum())} stage, "
        f"{int((prop_df['field'] == 'supplier').sum())} supplier). "
        "Each row carries its evidence; nothing is applied automatically.",
        "",
        "## Supplier recovery by confidence",
        "",
        "| Confidence | Lines | Amount, CNY | Share of empty-supplier amount |",
        "|---|---:|---:|---:|",
    ]
    for conf in ("high", "medium", "low"):
        c = by_conf[conf]
        share = c["amount"] / total * 100 if total else 0.0
        md.append(f"| {conf} | {c['rows']} | {c['amount']:,.2f} | {share:.1f}% |")
    plus = by_conf["high"]["rows"] + by_conf["medium"]["rows"]
    share = stats["recovered_medium_plus_share"] * 100
    md += [
        f"| **medium+ total** | **{plus}** | **{stats['recovered_medium_plus_amount']:,.2f}** "
        f"| **{share:.1f}%** |",
        "",
        f"Goal from the issue: ≥50% of empty-supplier value at medium+. "
        f"Reached: **{share:.1f}%**.",
        "",
    ]
    struct_share = (
        stats["structural_unattributable_amount"] / total * 100 if total else 0.0
    )
    md += [
        f"**Structural ceiling.** ¥{stats['structural_unattributable_amount']:,.2f} "
        f"({struct_share:.1f}% of the empty-supplier amount) is prepayment for "
        "molds / wood tooling whose counterparty is never named anywhere in the "
        "data — their tail payments fall outside the data window, so no in-data "
        "method can name them. Against the remaining addressable pool of "
        f"¥{stats['addressable_amount']:,.2f} the medium+ recovery is "
        f"**{stats['recovered_share_addressable'] * 100:.1f}%**.",
        "",
        "## Methods",
        "",
        "- `substring` — a known supplier name appears inside the row's "
        "item/purpose/remarks.",
        "- `twin_row` — an attributed row with the same amount and similar "
        "item/style/purpose pays the same order (counterpart payment).",
        "- `category_dominance` — one supplier overwhelmingly serves the "
        "row's cost category in attributed rows.",
        "- `stage_hint` — item names a mold purchase/deposit the keyword "
        "classifier misplaced.",
        "- `supplier_stage` — for unclassified rows: dominant stage of the "
        "same supplier's attributed rows.",
        "",
    ]
    if len(prop_df):
        counts = prop_df.groupby(["field", "method"]).size().reset_index(name="n")
        md.append("| Field | Method | Proposals |")
        md.append("|---|---|---:|")
        for r in counts.itertuples():
            md.append(f"| {r.field} | {r.method} | {r.n} |")
        md.append("")

    examples = prop_df[prop_df["field"] == "supplier"]
    examples = examples.assign(
        _rank=examples["confidence"].map(CONF_RANK)
    ).sort_values("_rank", ascending=False).head(8)
    if len(examples):
        md += ["## Example supplier proposals", "",
               "| line_id | proposed | confidence | method | evidence |",
               "|---|---|---|---|---|"]
        for r in examples.itertuples():
            ev = str(r.evidence)
            ev = ev if len(ev) <= 110 else ev[:107] + "..."
            md.append(f"| {r.line_id} | {r.proposed} | {r.confidence} | {r.method} | {ev} |")
        md.append("")

    amounts = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    empty = df["supplier"].fillna("").astype(str).str.strip() == ""
    attributed_ids = set(
        prop_df[prop_df["field"] == "supplier"]["line_id"].astype(str)
    ) if len(prop_df) else set()
    left = df[empty & ~df["line_id"].astype(str).isin(attributed_ids)].copy()
    left["sort_amt"] = amounts[empty & ~df["line_id"].astype(str).isin(attributed_ids)]
    left = left.nlargest(10, "sort_amt")
    if len(left):
        md += ["## Largest lines left unattributed", "",
               "| line_id | month | item | amount | why |",
               "|---|---|---|---:|---|"]
        for lid, month, item, amt in zip(
            left["line_id"], left["month"], left["item"], left["sort_amt"], strict=False
        ):
            md.append(
                f"| {lid} | {month} | {str(item)[:40]} | {amt:,.2f} "
                f"| {_left_reason(str(item))} |"
            )
        md.append("")

    stage_props = prop_df[prop_df["field"] == "stage"] if len(prop_df) else prop_df
    if len(stage_props):
        md += ["## Stage proposals", "",
               "| line_id | current | proposed | confidence | method | evidence |",
               "|---|---|---|---|---|---|"]
        for r in stage_props.itertuples():
            ev = str(r.evidence)
            ev = ev if len(ev) <= 100 else ev[:97] + "..."
            md.append(f"| {r.line_id} | {r.current} | {r.proposed} | "
                      f"{r.confidence} | {r.method} | {ev} |")
        md.append("")

    md += [
        "## Notes",
        "",
        "- All amounts and names above come from the staged data itself; the "
        "report is generated into the gitignored `reports/` tree.",
        "- Uncertainty is preserved: ambiguous twins (two equally good "
        "counterpart rows with different suppliers) and weak category "
        "majorities produce no proposal at all.",
    ]
    return "\n".join(md) + "\n"


def _application_md(previous: pd.DataFrame, staged: pd.DataFrame) -> str:
    """GH#39 section: status of the previous run's proposals after the
    attribution application layer (rules + overrides)."""
    rows = application_rows(previous, staged)
    if not rows:
        return ""
    medium_plus = [r for r in rows if r["confidence"] in ("medium", "high")]
    applied = [r for r in medium_plus if r["status"] == "applied"]
    skipped = [r for r in medium_plus if r["status"] != "applied"]
    md = [
        "## GH#39 proposal application status",
        "",
        f"- Medium+ proposals from the previous forensic run: "
        f"**{len(medium_plus)}** — applied **{len(applied)}** "
        f"({sum(1 for r in applied if r['mechanism'] == 'rule')} via generic "
        f"keyword rules, {sum(1 for r in applied if r['mechanism'] == 'override')} "
        f"via exact-name overrides, "
        f"{sum(1 for r in applied if r['mechanism'] == 'taxonomy')} via taxonomy), "
        f"skipped **{len(skipped)}** (each with a written reason below).",
        "",
        "| line_id | field | proposed | confidence | status | mechanism | reason |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        md.append(
            f"| {r['line_id']} | {r['field']} | {r['proposed']} "
            f"| {r['confidence']} | {r['status']} | {r['mechanism'] or '—'} "
            f"| {r['reason'] or '—'} |"
        )
    md.append("")
    return "\n".join(md)


def write_reports(prop_df: pd.DataFrame, stats: dict, df: pd.DataFrame,
                  out_dir: Path | str, previous: pd.DataFrame | None = None) -> None:
    """Write attribution_proposals.csv + attribution_report.md.

    ``previous`` — the prior forensic run's proposals (read before the CSV
    is overwritten). When given, the report gains the GH#39 application
    status section for every previous proposal.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prop_df.to_csv(out_dir / "attribution_proposals.csv", index=False)
    md = _report_md(prop_df, stats, df)
    if previous is not None and len(previous):
        section = _application_md(previous, df)
        if section:
            md = md.rstrip("\n") + "\n\n" + section + "\n"
    (out_dir / "attribution_report.md").write_text(md, encoding="utf-8")
