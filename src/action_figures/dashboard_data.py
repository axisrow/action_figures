"""Pure functions: reports CSVs (+optional pkl) -> one JSON-safe dict for the dashboard.

Every loader reads a CSV written by the audit/benchmarks/optimization/translation
report steps and returns plain JSON-safe types (str/int/float/list/dict), so the
result can be embedded verbatim into dist/index.html by build_dashboard.py.

Expected CSV layout under ``reports_dir`` (headers are the contract):

- audit/stage_summary.csv     stage,n_lines,amount_cny,share_pct
- audit/by_month_stage.csv    month,stage,amount_cny
- audit/by_style_stage.csv    style_no,stage,amount_cny
- audit/by_style_timeline.csv style_no,stage,start_date,end_date
- audit/by_supplier_stage.csv supplier,stage,month,amount_cny
- benchmarks/benchmarks.csv   stage,metric,our_value,market_low,market_high,unit,
                              source_title,source_url,accessed_on
- optimization/optimizations.csv id,title,stage,baseline_cny,saving_cny,proof
- translation/glossary.csv    zh,en,explanation

All files are optional-ish: a missing file yields empty rows (skeleton phase —
the dashboard renders on whatever exists). Synthetic tests use the same schema.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _f(value: str) -> float:
    return float(value)


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


def load_by_month_stage(path: Path) -> list[dict]:
    return [
        {"month": r["month"], "stage": r["stage"], "amount_cny": _f(r["amount_cny"])}
        for r in _read_csv(path)
    ]


def load_by_style_stage(path: Path) -> list[dict]:
    return [
        {"style_no": r["style_no"], "stage": r["stage"], "amount_cny": _f(r["amount_cny"])}
        for r in _read_csv(path)
    ]


def load_by_style_timeline(path: Path) -> list[dict]:
    rows = [
        {
            "style_no": r["style_no"],
            "stage": r["stage"],
            "start_date": r["start_date"],
            "end_date": r["end_date"],
            "duration_days": _d(r["start_date"], r["end_date"]),
        }
        for r in _read_csv(path)
    ]
    return sorted(rows, key=lambda r: (r["style_no"], r["start_date"]))


def load_suppliers(path: Path) -> list[dict]:
    """Aggregate by_supplier_stage.csv: totals, stage mix, months; total desc."""
    agg: dict[str, dict] = {}
    for r in _read_csv(path):
        name = r["supplier"]
        entry = agg.setdefault(
            name, {"supplier": name, "amount_cny": 0.0, "stage_mix": {}, "months": set()}
        )
        amount = _f(r["amount_cny"])
        entry["amount_cny"] += amount
        entry["stage_mix"][r["stage"]] = entry["stage_mix"].get(r["stage"], 0.0) + amount
        if r.get("month"):
            entry["months"].add(r["month"])
    rows = [
        {**e, "months": sorted(e["months"])}
        for e in agg.values()
    ]
    return sorted(rows, key=lambda r: r["amount_cny"], reverse=True)


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


# --- aggregate -----------------------------------------------------------


def build_dashboard_data(reports_dir: Path) -> dict:
    """One JSON-safe dict consumed by build_dashboard.render_html()."""
    reports_dir = Path(reports_dir)
    stages = load_stage_summary(reports_dir / "audit" / "stage_summary.csv")
    by_month = load_by_month_stage(reports_dir / "audit" / "by_month_stage.csv")
    by_style = load_by_style_stage(reports_dir / "audit" / "by_style_stage.csv")
    timeline = load_by_style_timeline(reports_dir / "audit" / "by_style_timeline.csv")
    suppliers = load_suppliers(reports_dir / "audit" / "by_supplier_stage.csv")
    benchmarks = load_benchmarks(reports_dir / "benchmarks" / "benchmarks.csv")
    optimizations = load_optimizations(
        reports_dir / "optimization" / "optimizations.csv"
    )
    glossary = load_glossary(reports_dir / "translation" / "glossary.csv")

    total_spend = sum(r["amount_cny"] for r in stages)
    months = sorted({r["month"] for r in by_month})
    stage_names = [r["stage"] for r in stages]
    styles = sorted({r["style_no"] for r in by_style})

    # heatmap cells: [month, stage, value] with month/stage as labels
    cell_map = {(r["month"], r["stage"]): r["amount_cny"] for r in by_month}
    cells = [
        [m, s, cell_map.get((m, s), 0.0)] for m in months for s in stage_names
    ]

    # gantt: per style, stages sorted by start; styles by total duration desc
    per_style: dict[str, list[dict]] = {}
    for row in timeline:
        per_style.setdefault(row["style_no"], []).append(row)
    gantt = [
        {
            "style_no": style_no,
            "stages": stages_rows,
            "total_days": _d(
                min(s["start_date"] for s in stages_rows),
                max(s["end_date"] for s in stages_rows),
            ),
        }
        for style_no, stages_rows in per_style.items()
    ]
    gantt = sorted(gantt, key=lambda g: g["total_days"], reverse=True)

    # sankey: Spend -> stage -> supplier
    supplier_stage: dict[tuple[str, str], float] = {}
    supplier_rows = _read_csv(reports_dir / "audit" / "by_supplier_stage.csv")
    for r in supplier_rows:
        key = (r["supplier"], r["stage"])
        supplier_stage[key] = supplier_stage.get(key, 0.0) + _f(r["amount_cny"])
    nodes = [{"name": "Spend"}]
    nodes += [{"name": s} for s in stage_names]
    nodes += [{"name": s["supplier"]} for s in suppliers]
    links = [{"source": "Spend", "target": r["stage"], "value": r["amount_cny"]}
             for r in stages]
    links += [
        {"source": stage, "target": supplier, "value": value}
        for (supplier, stage), value in supplier_stage.items()
    ]

    top3 = [
        {"title": c["title"], "saving_cny": c["saving_cny"], "proof": c["proof"]}
        for c in optimizations[:3]
    ]

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
            "sankey": {"nodes": nodes, "links": links},
        },
        "cost_structure": {
            "stages": stages,
            "by_month": by_month,
            "months": months,
            "heatmap": {"months": months, "stages": stage_names, "cells": cells},
        },
        "timelines": {"gantt": gantt},
        "suppliers": {"all": suppliers, "top": suppliers[:10]},
        "benchmarks": {"rows": benchmarks},
        "optimizations": {"cards": optimizations},
        "glossary": {"rows": glossary},
    }
