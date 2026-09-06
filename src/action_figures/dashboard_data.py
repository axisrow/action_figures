"""Pure functions: reports CSVs (+optional pkl) -> one JSON-safe dict for the dashboard.

Every loader reads a CSV written by the audit/benchmarks/optimization/translation
report steps and returns plain JSON-safe types (str/int/float/list/dict), so the
result can be embedded verbatim into dist/index.html by build_dashboard.py.

Expected CSV layout under ``reports_dir`` (headers are the contract):

- audit/stage_summary.csv     stage,n_lines,amount_cny,share_pct
- audit/stages.csv            stage_id,order,label_en,description_en,zh_keys
- audit/by_month_stage.csv    month,stage,amount_cny
- audit/by_style_stage.csv    style_no,stage,amount_cny
- audit/by_style_timeline.csv style_no,stage,start_date,end_date
- audit/by_supplier_stage.csv supplier,stage,month,amount_cny
- benchmarks/benchmarks.csv   stage,metric,our_value,market_low,market_high,unit,
                              source_title,source_url,accessed_on
- optimization/optimizations.csv id,title,stage,baseline_cny,saving_cny,proof
- translation/glossary.csv    zh,en,explanation

REAL report formats (what the finished report steps actually write) are also
supported and auto-detected; when the CSV variant is absent the builder reads:

- audit/by_month_stage.csv    month,stage,n_lines,amount_cny
- audit/by_style_timeline.csv style_no,stage,start_date,end_date,n_lines,amount_cny
- audit/by_supplier_stage.csv supplier,stage,amount_cny,n_lines,months_active
                              (pre-aggregated; months_active is a ";"-joined list)
- audit/unclassified.csv      line_id,month,date,style_no,item,purpose,supplier,amount
- benchmarks/<stage>.md       per-stage markdown with bold ranges + source links
- optimization/optimization.md ranked recommendation table + per-rec sections
- translation/glossary.md     | zh | en | explanation | markdown table

Optional separate input: the supplier translation dict CSV (data/dict/
translation.csv; columns zh,en,column_hint,n_occurrences,status), passed as
``supplier_translations_path`` — rows with column_hint=supplier turn sankey
supplier names into 'English Name (中文原文)'.

All files are optional-ish: a missing file yields empty rows (skeleton phase —
the dashboard renders on whatever exists). Synthetic tests use the same schema.
"""

from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _f(value: str) -> float:
    return float(value)


def _money(value: str) -> float:
    """'8,900' / '**3,100**' / '19.0%' -> float (commas, bold, % stripped)."""
    return float(re.sub(r"[,:%*]", "", value.strip()))


def _norm_style(value: str) -> str:
    """'9052.0' -> '9052' (float-string style numbers from the audit)."""
    s = (value or "").strip().strip('"')
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def _d(start: str, end: str) -> int:
    """Inclusive day count between two ISO dates."""
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


# --- loaders -------------------------------------------------------------


def load_stage_summary(path: Path) -> list[dict]:
    """Stage rows sorted by total spend, descending."""
    rows = [
        {
            "stage": r["stage"],
            "amount_cny": _f(r["amount_cny"]),
            "share_pct": _f(r["share_pct"]),
            "n_lines": int(r["n_lines"]),
        }
        for r in _read_csv(path)
    ]
    return sorted(rows, key=lambda r: r["amount_cny"], reverse=True)


SERVICE_STAGES = frozenset({"admin_other", "unclassified"})


def load_stages_meta(path: Path) -> list[dict]:
    """stages.csv -> stage metadata rows in production order (PE-1 export).

    Columns: stage_id, order (1-12), label_en, description_en, zh_keys
    (';'-joined). zh_keys becomes a list; ``service`` marks the two
    non-production buckets that close the menu as an Other block.
    """
    rows = [
        {
            "stage_id": r["stage_id"].strip(),
            "order": int(r["order"]),
            "label_en": r["label_en"].strip(),
            "description_en": r["description_en"].strip(),
            "zh_keys": [k.strip() for k in r["zh_keys"].split(";") if k.strip()],
            "service": r["stage_id"].strip() in SERVICE_STAGES,
        }
        for r in _read_csv(path)
    ]
    return sorted(rows, key=lambda r: r["order"])


def load_by_month_stage(path: Path) -> list[dict]:
    return [
        {"month": r["month"], "stage": r["stage"], "amount_cny": _f(r["amount_cny"])}
        for r in _read_csv(path)
    ]


def load_by_style_stage(path: Path) -> list[dict]:
    return [
        {
            "style_no": _norm_style(r["style_no"]),
            "stage": r["stage"],
            "amount_cny": _f(r["amount_cny"]),
        }
        for r in _read_csv(path)
    ]


def load_by_style_timeline(path: Path) -> list[dict]:
    """Timeline rows; optional real-format n_lines/amount_cny default to 1/0.0."""
    rows = [
        {
            "style_no": _norm_style(r["style_no"]),
            "stage": r["stage"],
            "start_date": r["start_date"],
            "end_date": r["end_date"],
            "duration_days": _d(r["start_date"], r["end_date"]),
            "n_lines": int(r["n_lines"]) if r.get("n_lines") else 1,
            "amount_cny": _f(r["amount_cny"]) if r.get("amount_cny") else 0.0,
        }
        for r in _read_csv(path)
    ]
    return sorted(rows, key=lambda r: (r["style_no"], r["start_date"]))


UNATTRIBUTED = "Unattributed"


def load_suppliers(path: Path) -> list[dict]:
    """by_supplier_stage.csv in either format; totals + stage mix + months, desc.

    Legacy per-month:  supplier,stage,month,amount_cny
    Real aggregated:   supplier,stage,amount_cny,n_lines,months_active
    Blank supplier names become ``UNATTRIBUTED`` and are pinned LAST
    regardless of amount (data-quality bucket, not a real vendor).
    """
    rows = _read_csv(path)
    agg: dict[str, dict] = {}
    aggregated = bool(rows) and "months_active" in rows[0]
    for r in rows:
        name = r["supplier"].strip() or UNATTRIBUTED
        entry = agg.setdefault(
            name,
            {
                "supplier": name,
                "amount_cny": 0.0,
                "stage_mix": {},
                "months": set(),
                "n_lines": 0,
            },
        )
        amount = _f(r["amount_cny"])
        entry["amount_cny"] += amount
        entry["stage_mix"][r["stage"]] = entry["stage_mix"].get(r["stage"], 0.0) + amount
        if aggregated:
            entry["months"].update(m for m in r["months_active"].split(";") if m)
            entry["n_lines"] += int(r["n_lines"])
        else:
            entry["months"].add(r["month"])
            entry["n_lines"] += 1
    out = [{**e, "months": sorted(e["months"])} for e in agg.values()]
    out.sort(key=lambda r: r["amount_cny"], reverse=True)
    named = [r for r in out if r["supplier"] != UNATTRIBUTED]
    unattr = [r for r in out if r["supplier"] == UNATTRIBUTED]
    return named + unattr


def load_supplier_translations(path: Path) -> dict[str, str]:
    """translation dict CSV (zh,en,column_hint,n_occurrences,status) -> {zh: en}.

    Only rows with column_hint == "supplier" and a non-empty en value;
    everything else falls back to the raw zh name at lookup time.
    """
    return {
        r["zh"].strip(): r["en"].strip()
        for r in _read_csv(path)
        if r.get("column_hint", "").strip() == "supplier" and r.get("en", "").strip()
    }


def load_unclassified(path: Path) -> dict:
    """audit/unclassified.csv -> line count + total amount (data-quality note)."""
    rows = _read_csv(path)
    return {
        "n_lines": len(rows),
        "amount_cny": sum(_f(r["amount"]) for r in rows),
    }


def load_benchmarks(path: Path) -> list[dict]:
    return [
        {
            "stage": r["stage"],
            "metric": r["metric"],
            "our_value": _f(r["our_value"]),
            "market_low": _f(r["market_low"]),
            "market_high": _f(r["market_high"]),
            "unit": r["unit"],
            "source_title": r["source_title"],
            "source_url": r["source_url"],
            "accessed_on": r["accessed_on"],
        }
        for r in _read_csv(path)
    ]


def load_optimizations(path: Path) -> list[dict]:
    """Cards sorted by estimated saving, descending."""
    rows = [
        {
            "id": r["id"],
            "title": r["title"],
            "stage": r["stage"],
            "baseline_cny": _f(r["baseline_cny"]),
            "saving_cny": _f(r["saving_cny"]),
            "proof": r["proof"],
        }
        for r in _read_csv(path)
    ]
    return sorted(rows, key=lambda r: r["saving_cny"], reverse=True)


def load_glossary(path: Path) -> list[dict]:
    return [
        {"zh": r["zh"], "en": r["en"], "explanation": r["explanation"]}
        for r in _read_csv(path)
    ]


# --- markdown loaders (real report formats) ---------------------------------

_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BARE_URL_ITEM_RE = re.compile(r"^\d+\.\s+(https?://\S+)\s+—\s+(.+?)\s*$", re.M)
_BOLD_RANGE_RE = re.compile(r"\*\*([^*]*\d[^*]*)\*\*")


def _strip_md(text: str) -> str:
    """Plain text from a markdown fragment: drop bold/code, links -> title."""
    out = _LINK_RE.sub(lambda m: m.group(1), text)
    out = out.replace("**", "").replace("`", "").replace("*", "")
    return out.strip().lstrip("- ").strip()


def load_benchmarks_md(benchmarks_dir: Path) -> list[dict]:
    """benchmarks/<stage>.md -> one card per stage.

    Card = {stage, title, intro, highlights, sources}:
    - title from the H1 (after 'Benchmark: ', parenthetical suffix dropped)
    - intro = paragraphs before the first '## ' heading (plain text)
    - highlights = lines carrying a bold numeric range ('**$1,000–5,000**'),
      markdown-stripped, capped at 12 per stage
    - sources = all http(s) links (title, url), deduped by url, first-seen
      order; bare 'N. url — description' list items also count
    """
    benchmarks_dir = Path(benchmarks_dir)
    if not benchmarks_dir.is_dir():
        return []
    cards = []
    for path in sorted(benchmarks_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()

        m = re.match(r"#\s+Benchmark:\s*(.+)", lines[0] if lines else "")
        title = re.sub(r"\s*[(（].*$", "", m.group(1)).strip() if m else path.stem

        intro_lines: list[str] = []
        for line in lines[1:]:
            if line.startswith("##"):
                break
            if line.strip() and not line.startswith("#"):
                intro_lines.append(_strip_md(line))
        intro = " ".join(intro_lines)

        highlights = []
        for line in lines:
            s = line.strip()
            if not s or s.startswith(("#", "|", ">")):
                continue
            if _BOLD_RANGE_RE.search(s):
                highlights.append(_strip_md(s))
        highlights = highlights[:12]

        sources: list[dict] = []
        seen: set[str] = set()
        pairs = [(t, u) for t, u in _LINK_RE.findall(text)]
        pairs += [(desc.strip(), u) for u, desc in _BARE_URL_ITEM_RE.findall(text)]
        for title_text, url in pairs:
            if url not in seen:
                seen.add(url)
                sources.append({"title": title_text.strip(), "url": url})

        cards.append(
            {
                "stage": path.stem,
                "title": title,
                "intro": intro,
                "highlights": highlights,
                "sources": sources,
            }
        )
    return cards


def _md_table_rows(text: str, header_keyword: str) -> list[list[str]]:
    """Rows (as raw cell strings) of the first markdown table whose header
    line contains header_keyword."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("|") and header_keyword in line:
            rows = []
            for row in lines[i + 1:]:
                if not row.startswith("|"):
                    break
                cells = [c.strip() for c in row.strip().strip("|").split("|")]
                if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    continue  # alignment separator
                rows.append(cells)
            return rows
    return []


def load_optimizations_md(path: Path) -> dict:
    """optimization/optimization.md -> {cards, market_comparison, insights}.

    - cards: ranked table ('Recommendation' header) + the matching '### N)'
      sections' Our baseline / Market range / Savings math paragraphs
    - market_comparison: the stage-share table ('Our share' header)
    - insights: numbered bold deviation items + the '**Reading:**' verdict
    """
    if not path.exists():
        return {"cards": [], "market_comparison": [], "insights": []}
    text = path.read_text(encoding="utf-8")

    # ranked recommendations table
    table = _md_table_rows(text, "Recommendation")
    cards = []
    for cells in table:
        if len(cells) < 7:
            continue
        cards.append(
            {
                "id": cells[0],
                "title": _strip_md(cells[1]),
                "saving_cny": _money(cells[2]),
                "prob": _money(cells[3]),
                "score": _money(cells[4]),
                "time_saved": cells[5],
                "effort": cells[6],
                "baseline": "",
                "market_range": "",
                "math": "",
            }
        )

    # per-recommendation sections: '### N) Title ... **Label:** text'
    sections = re.split(r"^###\s+\d+\)\s+", text, flags=re.M)[1:]
    label_re = re.compile(
        r"\*\*(?:Our baseline|Market range|Savings math):\*\*\s*(.+)"
    )
    field_of = {"Our baseline": "baseline", "Market range": "market_range",
                "Savings math": "math"}
    for section in sections:
        first_line = section.splitlines()[0]
        fields = {}
        for m in label_re.finditer(section):
            for label, field in field_of.items():
                if m.group(0).startswith(f"**{label}:**"):
                    fields[field] = _strip_md(m.group(1))
        for card in cards:
            if card["title"].lower() in first_line.lower():
                card.update(fields)
                break

    # stage shares vs market table
    market_comparison = [
        {
            "stage": cells[0],
            "our_share_pct": _money(cells[1]),
            "h1_2026_cny": _money(cells[2]),
            "market_ref": _strip_md(cells[3]) if len(cells) > 3 else "",
        }
        for cells in _md_table_rows(text, "Our share")
        if len(cells) >= 3
    ]

    # plain-English insights: Reading verdict + numbered bold deviations
    insights = []
    for m in re.finditer(r"\*\*Reading:\*\*\s*(.+)", text):
        insights.append(_strip_md(m.group(1)))
    tail = text.split("are our candidates", 1)
    if len(tail) == 2:
        for m in re.finditer(r"^\d+\.\s+\*\*(.+?)\*\*(.+)$", tail[1], flags=re.M):
            insights.append(_strip_md(f"{m.group(1)}{m.group(2)}"))

    return {
        "cards": cards,
        "market_comparison": market_comparison,
        "insights": insights,
    }


def load_glossary_md(path: Path) -> list[dict]:
    """translation/glossary.md '| zh | en | explanation |' table."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [
        {"zh": cells[0], "en": cells[1], "explanation": cells[2]}
        for cells in _md_table_rows(text, "zh")
        if len(cells) >= 3
    ]


# --- aggregate -----------------------------------------------------------


def _benchmarks_stages_from_rows(rows: list[dict]) -> list[dict]:
    """Derive per-stage benchmark cards from the legacy CSV rows (mock path)."""
    by_stage: dict[str, dict] = {}
    for r in rows:
        card = by_stage.setdefault(
            r["stage"],
            {"stage": r["stage"], "title": r["stage"], "intro": "",
             "highlights": [], "sources": []},
        )
        card["highlights"].append(
            f"{r['metric']}: ours {r['our_value']:,.1f} vs market "
            f"{r['market_low']:,.1f}–{r['market_high']:,.1f} {r['unit']}"
        )
        card["sources"].append(
            {"title": r["source_title"], "url": r["source_url"]}
        )
    return list(by_stage.values())


SANKEY_TOP_N = 10


def _supplier_label(zh: str, translations: dict[str, str]) -> str:
    """Display label 'English Name (中文原文)'; raw zh when untranslated."""
    en = translations.get(zh)
    return f"{en} ({zh})" if en else zh


def build_sankey(
    suppliers: list[dict], stages: list[dict], translations: dict[str, str]
) -> dict:
    """Overview sankey payload: Spend -> stages -> top-10 suppliers + Others.

    Suppliers outside the top-10 (by total amount) collapse into a single
    'Others (N suppliers)' node with one aggregated link per stage. The
    blank-supplier bucket (``UNATTRIBUTED``) never joins the ranking: it is
    always its own node, pinned last among supplier nodes. Flow invariant:
    Σ spend→stage links == Σ stage→supplier links == grand total. Nodes are
    Spend, then stages, then suppliers (all by value, desc), Unattributed
    last; links are sorted by value desc. Also returns ``top_suppliers``
    fallback rows (top-10 + Others + Unattributed) with stage mix, totals
    and share of grand total.
    """
    named = [s for s in suppliers if s["supplier"] != UNATTRIBUTED]
    unattr = [s for s in suppliers if s["supplier"] == UNATTRIBUTED]
    unattr_mix = unattr[0]["stage_mix"] if unattr else {}
    top_rows = named[:SANKEY_TOP_N]
    tail_rows = named[SANKEY_TOP_N:]
    label_of = {
        s["supplier"]: _supplier_label(s["supplier"], translations)
        for s in named
    }
    top_names = {s["supplier"] for s in top_rows}
    others_name = f"Others ({len(tail_rows)} suppliers)" if tail_rows else None

    nodes = [{"name": "Spend"}]
    nodes += [{"name": r["stage"]} for r in stages]
    nodes += [{"name": label_of[s["supplier"]]} for s in top_rows]
    if others_name:
        nodes.append({"name": others_name})
    if unattr:
        nodes.append({"name": UNATTRIBUTED})

    per_stage_top: dict[str, list[tuple[str, float]]] = {}
    per_stage_others: dict[str, float] = {}
    for s in named:
        bucket = per_stage_top if s["supplier"] in top_names else None
        for stage_name, amount in s["stage_mix"].items():
            if bucket is None:
                per_stage_others[stage_name] = (
                    per_stage_others.get(stage_name, 0.0) + amount
                )
            else:
                bucket.setdefault(stage_name, []).append((s["supplier"], amount))

    links = [
        {"source": "Spend", "target": r["stage"], "value": r["amount_cny"]}
        for r in stages
    ]
    links += [
        {"source": stage_name, "target": label_of[supplier], "value": amount}
        for stage_name, pairs in per_stage_top.items()
        for supplier, amount in pairs
    ]
    if others_name:
        links += [
            {"source": stage_name, "target": others_name, "value": amount}
            for stage_name, amount in per_stage_others.items()
        ]
    links += [
        {"source": stage_name, "target": UNATTRIBUTED, "value": amount}
        for stage_name, amount in unattr_mix.items()
    ]
    links.sort(key=lambda ln: ln["value"], reverse=True)

    total = sum(r["amount_cny"] for r in stages)

    def _share(amount: float) -> float:
        # denominator is the stage_summary total, which can drift below the
        # supplier-CSV amounts — clamp like the callout so the page stays
        # self-consistent
        return min(round(amount / total * 100, 1), 100.0) if total else 0.0

    fallback_rows = [
        {
            "supplier": label_of[s["supplier"]],
            "stages": sorted(
                s["stage_mix"], key=lambda st: s["stage_mix"][st], reverse=True
            ),
            "total_cny": s["amount_cny"],
            "share_pct": _share(s["amount_cny"]),
        }
        for s in top_rows
    ]
    if others_name:
        others_total = sum(per_stage_others.values())
        fallback_rows.append(
            {
                "supplier": others_name,
                "stages": sorted(
                    per_stage_others,
                    key=lambda st: per_stage_others[st],
                    reverse=True,
                ),
                "total_cny": others_total,
                "share_pct": _share(others_total),
            }
        )
    if unattr:
        unattr_total = sum(unattr_mix.values())
        fallback_rows.append(
            {
                "supplier": UNATTRIBUTED,
                "stages": sorted(
                    unattr_mix, key=lambda st: unattr_mix[st], reverse=True
                ),
                "total_cny": unattr_total,
                "share_pct": _share(unattr_total),
            }
        )
    return {"nodes": nodes, "links": links, "top_suppliers": fallback_rows}


def build_dashboard_data(
    reports_dir: Path, supplier_translations_path: Path | None = None
) -> dict:
    """One JSON-safe dict consumed by build_dashboard.render_html()."""
    reports_dir = Path(reports_dir)
    translations = (
        load_supplier_translations(supplier_translations_path)
        if supplier_translations_path
        else {}
    )
    stages = load_stage_summary(reports_dir / "audit" / "stage_summary.csv")
    # stage menu (Process Explorer): stages.csv metadata in process order,
    # amounts merged from stage_summary — a stage missing from the summary
    # (qc_testing in the real data) keeps its menu row at zero
    summary_by_stage = {r["stage"]: r for r in stages}
    stage_menu = []
    for meta in load_stages_meta(reports_dir / "audit" / "stages.csv"):
        s = summary_by_stage.get(meta["stage_id"])
        stage_menu.append(
            {
                **meta,
                "amount_cny": s["amount_cny"] if s else 0.0,
                "share_pct": s["share_pct"] if s else 0.0,
                "n_lines": s["n_lines"] if s else 0,
            }
        )
    by_month = load_by_month_stage(reports_dir / "audit" / "by_month_stage.csv")
    by_style = load_by_style_stage(reports_dir / "audit" / "by_style_stage.csv")
    timeline = load_by_style_timeline(reports_dir / "audit" / "by_style_timeline.csv")
    suppliers = load_suppliers(reports_dir / "audit" / "by_supplier_stage.csv")
    unclassified = load_unclassified(reports_dir / "audit" / "unclassified.csv")

    bench_csv = reports_dir / "benchmarks" / "benchmarks.csv"
    if bench_csv.exists():
        bench_rows = load_benchmarks(bench_csv)
        bench_stages = _benchmarks_stages_from_rows(bench_rows)
    else:
        bench_rows = []
        bench_stages = load_benchmarks_md(reports_dir / "benchmarks")

    opt_csv = reports_dir / "optimization" / "optimizations.csv"
    if opt_csv.exists():
        opt_cards = load_optimizations(opt_csv)
        opt = {"cards": opt_cards, "market_comparison": [], "insights": []}
    else:
        opt = load_optimizations_md(
            reports_dir / "optimization" / "optimization.md"
        )

    gloss_csv = reports_dir / "translation" / "glossary.csv"
    glossary = (
        load_glossary(gloss_csv) if gloss_csv.exists()
        else load_glossary_md(reports_dir / "translation" / "glossary.md")
    )

    total_spend = sum(r["amount_cny"] for r in stages)
    months = sorted({r["month"] for r in by_month})
    stage_names = [r["stage"] for r in stages]
    styles = sorted({r["style_no"] for r in by_style})

    # heatmap cells: [month, stage, value] with month/stage as labels
    cell_map = {(r["month"], r["stage"]): r["amount_cny"] for r in by_month}
    cells = [
        [m, s, cell_map.get((m, s), 0.0)] for m in months for s in stage_names
    ]

    # gantt: attributed styles only — empty style_no rows are a data-quality
    # footnote, not a product; spans come from attributed rows alone
    linked = [r for r in timeline if r["style_no"]]
    unlinked_rows = [r for r in timeline if not r["style_no"]]
    per_style: dict[str, list[dict]] = {}
    for row in linked:
        per_style.setdefault(row["style_no"], []).append(row)
    gantt = [
        {
            "style_no": style_no,
            "stages": stages_rows,
            "total_days": _d(
                min(s["start_date"] for s in stages_rows),
                max(s["end_date"] for s in stages_rows),
            ),
            "total_cny": sum(s["amount_cny"] for s in stages_rows),
        }
        for style_no, stages_rows in per_style.items()
    ]
    gantt.sort(key=lambda g: (g["total_cny"], g["total_days"]), reverse=True)
    gantt_total_styles = len(gantt)
    gantt_truncated = gantt_total_styles > 25
    gantt = gantt[:25]

    # blank-supplier bucket stats for the data-quality callout / explainer
    unattr_rows = [s for s in suppliers if s["supplier"] == UNATTRIBUTED]
    unattributed = None
    if unattr_rows:
        ua = unattr_rows[0]
        # percentage is unattributed amount (by_supplier_stage) over the
        # stage_summary total — two files that can drift apart, so clamp:
        # a >100% share must never reach the page
        unattributed = {
            "n_lines": ua["n_lines"],
            "amount_cny": ua["amount_cny"],
            "share_pct": min(round(ua["amount_cny"] / total_spend * 100, 1), 100.0)
            if total_spend
            else 0.0,
        }

    # sankey: Spend -> stage -> supplier (top-10 + Others, EN labels when known)
    sankey = build_sankey(suppliers, stages, translations)

    # executive summary: the main takeaways in plain English, one screen
    top3_cards = sorted(opt["cards"], key=lambda c: c["saving_cny"],
                        reverse=True)[:3]
    top3 = [
        {"title": c["title"], "saving_cny": c["saving_cny"],
         "proof": c.get("math") or c.get("proof", "")}
        for c in top3_cards
    ]
    top3_savings = sum(c["saving_cny"] for c in top3)
    bullets = []
    if months:
        bullets.append(
            f"Total spend ¥{total_spend:,.0f} over {months[0]}…{months[-1]} "
            f"({len(months)} months), {sum(r['n_lines'] for r in stages)} "
            f"expense lines, {len(styles)} styles."
        )
    if stages:
        top3_stages_txt = ", ".join(
            f"{r['stage'].replace('_', ' ')} {r['share_pct']:.0f}%"
            for r in stages[:3]
        )
        bullets.append(f"Biggest cost stages: {top3_stages_txt}.")
    if top3:
        titles = "; ".join(c["title"] for c in top3)
        bullets.append(
            f"Top 3 saving opportunities add up to ~¥{top3_savings:,.0f} per "
            f"6 months: {titles}."
        )
    bullets.extend(opt["insights"][:4])
    executive = {
        "bullets": bullets,
        "total_spend_cny": total_spend,
        "months_range": [months[0], months[-1]] if months else [],
        "top3_stages": [
            {"stage": r["stage"], "share_pct": r["share_pct"],
             "amount_cny": r["amount_cny"]}
            for r in stages[:3]
        ],
        "top3_optimizations": top3,
        "top3_savings_cny": top3_savings,
    }

    return {
        "overview": {
            "summary": {
                "top_stage": stages[0]["stage"] if stages else "",
                "stage_count": len(stages),
                "top3_optimizations": top3,
            },
            "tiles": {
                "total_spend_cny": total_spend,
                "total_lines": sum(r["n_lines"] for r in stages),
                "num_styles": len(styles),
                "top_stage": stages[0]["stage"] if stages else "",
            },
            "unclassified": unclassified,
            "unattributed": unattributed,
            "executive": executive,
            "sankey": sankey,
        },
        "cost_structure": {
            "stages": stages,
            "by_month": by_month,
            "months": months,
            "heatmap": {"months": months, "stages": stage_names, "cells": cells},
        },
        "timelines": {
            "gantt": gantt,
            "gantt_truncated": gantt_truncated,
            "gantt_total_styles": gantt_total_styles,
            "unlinked": {
                "n_lines": sum(r["n_lines"] for r in unlinked_rows),
                "amount_cny": sum(r["amount_cny"] for r in unlinked_rows),
            },
        },
        "suppliers": {
            "all": suppliers,
            "top": suppliers[:10],
            "unattributed": unattributed,
        },
        "benchmarks": {"rows": bench_rows, "stages": bench_stages},
        "optimizations": opt,
        "glossary": {"rows": glossary},
        "stages": stage_menu,
    }
