"""Build the single-file static dashboard dist/index.html (stdlib only).

Usage:
    python dashboard/build_dashboard.py [--reports DIR] [--out FILE]

``--reports`` defaults to the main checkout's ``reports/`` (absolute path per
project rules). When it is missing (skeleton phase — audits not finished yet)
the builder falls back to MOCK synthetic CSVs with the exact same schema, so
swapping in real data later is trivial and the JSON payload shape is identical.

ECharts loads from a CDN; every chart also has an HTML-table twin rendered
server-side, so the page stays readable offline / with JS disabled.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from action_figures.dashboard_data import build_dashboard_data  # noqa: E402

MAIN_CHECKOUT_REPORTS = Path("/Users/axisrow/Projects/action_figures/reports")

# ---------------------------------------------------------------------------
# Mock synthetic reports (same CSV schema as the real report steps; FAKE data)
# ---------------------------------------------------------------------------

MOCK_STAGE_SUMMARY = """stage,n_lines,amount_cny,share_pct
tooling_molds,141,182000.00,28.4
painting_printing,203,164000.00,25.6
raw_materials,167,121000.00,18.9
injection_molding,98,74000.00,11.5
packaging,72,47000.00,7.3
logistics_freight,53,28000.00,4.4
assembly_processing,29,15000.00,2.3
qc_testing,11,9000.00,1.4
design_prototyping,4,2000.00,0.2
"""

MOCK_BY_MONTH_STAGE = """month,stage,amount_cny
2026-01,tooling_molds,82000.00
2026-01,painting_printing,31000.00
2026-01,raw_materials,40000.00
2026-01,injection_molding,22000.00
2026-01,packaging,9000.00
2026-01,logistics_freight,6000.00
2026-02,tooling_molds,70000.00
2026-02,painting_printing,48000.00
2026-02,raw_materials,36000.00
2026-02,injection_molding,24000.00
2026-02,packaging,14000.00
2026-02,logistics_freight,8000.00
2026-03,tooling_molds,30000.00
2026-03,painting_printing,51000.00
2026-03,raw_materials,29000.00
2026-03,injection_molding,16000.00
2026-03,packaging,12000.00
2026-03,logistics_freight,7000.00
2026-04,painting_printing,34000.00
2026-04,raw_materials,16000.00
2026-04,injection_molding,12000.00
2026-04,packaging,12000.00
2026-04,logistics_freight,7000.00
"""

MOCK_BY_STYLE_STAGE = """style_no,stage,amount_cny
AF-1001,tooling_molds,91000.00
AF-1001,painting_printing,82000.00
AF-1001,raw_materials,60000.00
AF-1001,injection_molding,37000.00
AF-1001,packaging,23000.00
AF-1002,tooling_molds,61000.00
AF-1002,painting_printing,54000.00
AF-1002,raw_materials,41000.00
AF-1002,injection_molding,25000.00
AF-1002,packaging,16000.00
AF-1003,tooling_molds,30000.00
AF-1003,painting_printing,28000.00
AF-1003,raw_materials,20000.00
AF-1003,injection_molding,12000.00
AF-2001,painting_printing,0.00
AF-2001,raw_materials,0.00
"""

MOCK_BY_STYLE_TIMELINE = """style_no,stage,start_date,end_date
AF-1001,design_prototyping,2026-01-05,2026-01-19
AF-1001,tooling_molds,2026-01-20,2026-03-15
AF-1001,injection_molding,2026-03-16,2026-04-30
AF-1001,painting_printing,2026-04-01,2026-05-20
AF-1001,assembly_processing,2026-05-21,2026-06-10
AF-1002,design_prototyping,2026-02-02,2026-02-13
AF-1002,tooling_molds,2026-02-14,2026-04-05
AF-1002,injection_molding,2026-04-06,2026-05-25
AF-1002,painting_printing,2026-05-01,2026-06-15
AF-1003,tooling_molds,2026-03-02,2026-04-20
AF-1003,painting_printing,2026-04-21,2026-06-01
AF-2001,design_prototyping,2026-05-06,2026-05-30
"""

MOCK_BY_SUPPLIER_STAGE = """supplier,stage,month,amount_cny
Ningbo Tooling Co,tooling_molds,2026-01,45000.00
Ningbo Tooling Co,tooling_molds,2026-02,38000.00
Ningbo Tooling Co,tooling_molds,2026-03,15000.00
Dongguan Precision,tooling_molds,2026-01,37000.00
Dongguan Precision,tooling_molds,2026-02,32000.00
Dongguan Precision,injection_molding,2026-01,10000.00
Dongguan Precision,injection_molding,2026-02,11000.00
Dongguan Precision,injection_molding,2026-03,8000.00
Shenzhen Colorworks,painting_printing,2026-01,31000.00
Shenzhen Colorworks,painting_printing,2026-02,48000.00
Shenzhen Colorworks,painting_printing,2026-03,51000.00
Shenzhen Colorworks,painting_printing,2026-04,34000.00
Hangzhou Plastics,raw_materials,2026-01,40000.00
Hangzhou Plastics,raw_materials,2026-02,36000.00
Hangzhou Plastics,raw_materials,2026-03,29000.00
Hangzhou Plastics,raw_materials,2026-04,16000.00
Guangyi Packaging,packaging,2026-01,9000.00
Guangyi Packaging,packaging,2026-02,14000.00
Guangyi Packaging,packaging,2026-03,12000.00
Guangyi Packaging,packaging,2026-04,12000.00
Ningbo Freight,logistics_freight,2026-01,6000.00
Ningbo Freight,logistics_freight,2026-02,8000.00
Ningbo Freight,logistics_freight,2026-03,7000.00
Ningbo Freight,logistics_freight,2026-04,7000.00
Wenzhou Assembly,assembly_processing,2026-05,15000.00
Suzhou QC Lab,qc_testing,2026-06,9000.00
Shanghai Sculpt Studio,design_prototyping,2026-01,1200.00
Shanghai Sculpt Studio,design_prototyping,2026-02,800.00
Yiwu Textile,textile_accessories,2026-03,3000.00
"""

MOCK_BENCHMARKS = """stage,metric,our_value,market_low,market_high,unit,source_title,source_url,accessed_on
tooling_molds,steel_mold_cost,152000,36000,144000,CNY,toyyie.com tooling guide,https://www.toyyie.com/tooling,2026-09-03
tooling_molds,lead_time_days,55,35,50,days,newmiho.com manufacturing,https://newmiho.com/timelines,2026-09-03
raw_materials,pvc_price_per_kg,3.1,7.2,21.6,CNY/kg,tenacioustoys.com materials,https://tenacioustoys.com/materials,2026-09-03
painting_printing,share_of_final_price,25.6,60,70,pct,newmiho.com cost breakdown,https://newmiho.com/costs,2026-09-03
packaging,packaging_per_unit,2.9,7.2,36.0,CNY/unit,toyyie.com packaging,https://www.toyyie.com/packaging,2026-09-03
qc_testing,compliance_lab_per_sku,9000,10800,28800,CNY/SKU,newmiho.com compliance,https://newmiho.com/compliance,2026-09-03
"""

MOCK_OPTIMIZATIONS = """id,title,stage,baseline_cny,saving_cny,proof
1,Switch premium steel molds to rapid aluminum tooling for short-run styles,tooling_molds,182000,72800,Rapid tooling is ~40% cheaper for runs under 5k units (https://www.rapiddirect.com/rapid-tooling, accessed 2026-09-03)
2,Replace hand painting with spray masks + tampo printing,painting_printing,164000,49200,Hand painting is ~60-70% of collectible price; masks cut paint labor dramatically (https://newmiho.com/costs, accessed 2026-09-03)
3,Negotiate PVC resin to bulk contract price,raw_materials,121000,24200,PVC trades at 1-3 USD/kg bulk vs spot (https://tenacioustoys.com/materials, accessed 2026-09-03)
4,Consolidate freight to monthly Full-Container-Load shipments,logistics_freight,28000,8400,LTL-to-FCL consolidation typically saves ~30% (https://www.toyyie.com/logistics, accessed 2026-09-03)
5,Universal mold base with swappable inserts across styles,tooling_molds,182000,54600,Insert-only tooling saves ~30% vs full molds (https://newmiho.com/tooling, accessed 2026-09-03)
"""

MOCK_GLOSSARY = """zh,en,explanation
开模,Tooling / mold making,Cutting the metal mold used to shape plastic parts; the big one-time cost before mass production.
注塑,Injection molding,Melting plastic and injecting it into the mold to form the figure's parts.
喷油,Spray painting,Spraying paint onto molded parts, usually with a spray gun and masks.
丝印,Screen printing / tampo,Printing fine details (eyes, logos) onto the part surface.
组装,Assembly,Joining painted parts into the finished figure.
包装,Packaging,Blister, color box and master carton that protect and present the product.
运费,Freight / shipping cost,Paying a logistics company to move goods.
原料,Raw materials,Plastic resin, paint, glue and other input materials.
检测,Testing / QC,Laboratory checks for safety standards (e.g. EN71, ASTM).
款号,Style number,The product code of one figure design (our internal SKU).
"""

MOCK_FILES = {
    "audit/stage_summary.csv": MOCK_STAGE_SUMMARY,
    "audit/by_month_stage.csv": MOCK_BY_MONTH_STAGE,
    "audit/by_style_stage.csv": MOCK_BY_STYLE_STAGE,
    "audit/by_style_timeline.csv": MOCK_BY_STYLE_TIMELINE,
    "audit/by_supplier_stage.csv": MOCK_BY_SUPPLIER_STAGE,
    "benchmarks/benchmarks.csv": MOCK_BENCHMARKS,
    "optimization/optimizations.csv": MOCK_OPTIMIZATIONS,
    "translation/glossary.csv": MOCK_GLOSSARY,
}


def build_mock_data() -> dict:
    """Dashboard data over synthetic CSVs with the production schema."""
    with tempfile.TemporaryDirectory(prefix="af_mock_reports_") as tmp:
        root = Path(tmp)
        for rel, text in MOCK_FILES.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return build_dashboard_data(root)


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

STAGES = "stages"
CDN = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"

STAGE_COLORS = {
    "tooling_molds": "#6c5ce7",
    "design_prototyping": "#00cec9",
    "injection_molding": "#0984e3",
    "painting_printing": "#e17055",
    "assembly_processing": "#fdcb6e",
    "raw_materials": "#00b894",
    "textile_accessories": "#e84393",
    "packaging": "#d63031",
    "qc_testing": "#2d3436",
    "logistics_freight": "#636e72",
    "admin_other": "#b2bec3",
}

STAGE_LABELS = {
    "tooling_molds": "Tooling & molds",
    "design_prototyping": "Design & prototyping",
    "injection_molding": "Injection molding",
    "painting_printing": "Painting & printing",
    "assembly_processing": "Assembly & processing",
    "raw_materials": "Raw materials",
    "textile_accessories": "Textile & accessories",
    "packaging": "Packaging",
    "qc_testing": "QC & testing",
    "logistics_freight": "Logistics & freight",
    "admin_other": "Admin / other",
}


def _fmt_cny(v: float) -> str:
    return f"¥{v:,.0f}"


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _label(stage: str) -> str:
    return STAGE_LABELS.get(stage, stage)


def _stage_palette(names: list[str]) -> list[str]:
    fallback = ["#74b9ff", "#55efc4", "#ffeaa7", "#fab1a0", "#a29bfe"]
    out, i = [], 0
    for n in names:
        out.append(STAGE_COLORS.get(n) or fallback[i % len(fallback)])
        i += n not in STAGE_COLORS
    return out


def _table(headers: list[str], rows: list[list[str]], cls: str = "fallback") -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
    )
    return f'<table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _section(tab_id: str, title: str, body: str, active: bool = False) -> str:
    cls = "tab-panel active" if active else "tab-panel"
    return (
        f'<section id="{tab_id}" class="{cls}" role="tabpanel">'
        f"<h2>{title}</h2>{body}</section>"
    )


def _chart(id_: str, height: int = 420) -> str:
    return (
        f'<div class="chart" id="chart-{id_}" style="height:{height}px"></div>'
    )


# --- per-tab renderers ----------------------------------------------------


def _render_overview(d: dict) -> str:
    ov = d["overview"]
    tiles = ov["tiles"]
    ex = ov.get("executive") or {}
    tiles_html = "".join(
        f'<div class="tile"><div class="tile-num">{val}</div>'
        f"<div class=\"tile-label\">{label}</div></div>"
        for label, val in [
            ("Total spend", _fmt_cny(tiles["total_spend_cny"])),
            ("Reimbursement lines", str(tiles["total_lines"])),
            ("Styles tracked", str(tiles["num_styles"])),
            ("Top stage", _label(tiles["top_stage"])),
        ]
    )
    exec_html = ""
    if ex.get("bullets"):
        items = "".join(f"<li>{_esc(b)}</li>" for b in ex["bullets"])
        exec_html = (
            "<h3>Executive summary — the main takeaways</h3>"
            f'<ul class="exec">{items}</ul>'
        )
    uncls = ov.get("unclassified") or {}
    note = ""
    if uncls.get("n_lines"):
        note = (
            f'<p class="lead">Data quality: {uncls["n_lines"]} expense lines '
            f"({_fmt_cny(uncls['amount_cny'])}) could not be classified into "
            "a production stage — see the audit report.</p>"
        )
    cards = "".join(
        f'<div class="opt-card"><h4>{_esc(c["title"])}</h4>'
        f'<div class="saving">saves ~{_fmt_cny(c["saving_cny"])}</div>'
        f'<div class="proof">{_esc(c["proof"])}</div></div>'
        for c in ov["summary"]["top3_optimizations"]
    )
    fallback = _table(
        ["Stage", "Total", "Share"],
        [
            [_label(r["stage"]), _fmt_cny(r["amount_cny"]), f'{r["share_pct"]:.1f}%']
            for r in d["cost_structure"][STAGES]
        ],
    )
    return (
        '<p class="lead">Where the money goes across production stages and '
        "suppliers. All amounts in CNY (¥).</p>"
        + exec_html
        + note
        + f'<div class="tiles">{tiles_html}</div>'
        + "<h3>Money flow: spend → stages → suppliers</h3>"
        + _chart("sankey", 480)
        + "<details open><summary>Table (no-JS fallback)</summary>"
        + fallback
        + "</details>"
        "<h3>Top optimization opportunities</h3>"
        f'<div class="cards">{cards}</div>'
    )


def _render_cost(d: dict) -> str:
    cs = d["cost_structure"]
    stage_rows = [
        [_label(r["stage"]), _fmt_cny(r["amount_cny"]), f'{r["share_pct"]:.1f}%', str(r["n_lines"])]
        for r in cs[STAGES]
    ]
    month_rows = [
        [
            m,
            *[
                _fmt_cny(
                    next(
                        (
                            r["amount_cny"]
                            for r in cs["by_month"]
                            if r["month"] == m and r["stage"] == s
                        ),
                        0.0,
                    )
                )
                for s in cs["heatmap"]["stages"]
            ],
        ]
        for m in cs["months"]
    ]
    return (
        "<p>Three views of the same numbers: bars by stage, stacked by month, "
        "treemap share and a month×stage heatmap.</p>"
        + _chart("bar")
        + _chart("stack")
        + _chart("treemap")
        + _chart("heatmap")
        + "<details open><summary>Tables (no-JS fallback)</summary>"
        + _table(["Stage", "Total", "Share", "Lines"], stage_rows)
        + _table(["Month", *[_label(s) for s in cs["heatmap"]["stages"]]], month_rows)
        + "</details>"
    )


def _render_timelines(d: dict) -> str:
    rows = []
    for g in d["timelines"]["gantt"]:
        stages = " → ".join(
            f'{_label(s["stage"])} ({s["start_date"]}..{s["end_date"]})'
            for s in g["stages"]
        )
        rows.append([g["style_no"], str(g["total_days"]), stages])
    note = ""
    if d["timelines"].get("gantt_truncated"):
        note = (
            '<p class="lead">Showing the 25 longest cycles; shorter styles are '
            "in the audit CSVs.</p>"
        )
    return (
        "<p>Stage bars per style, drawn from payment dates; styles sorted by "
        "total span (longest first).</p>"
        + note
        + _chart("gantt", max(360, 60 * len(d["timelines"]["gantt"])))
        + "<details open><summary>Table (no-JS fallback)</summary>"
        + _table(["Style", "Span (days)", "Stages"], rows)
        + "</details>"
    )


def _render_suppliers(d: dict) -> str:
    sup = d["suppliers"]
    rows = [
        [
            s["supplier"],
            _fmt_cny(s["amount_cny"]),
            ", ".join(_label(k) for k in sorted(s["stage_mix"], key=s["stage_mix"].get, reverse=True)),
            ", ".join(s["months"]),
        ]
        for s in sup["all"]
    ]
    table = _table(
        ["Supplier", "Total", "Stages", "Months"], rows, cls="supplier-table"
    )
    card_parts = []
    for s in sup["top"]:
        stages_attr = ";".join(s["stage_mix"])
        months_attr = ";".join(s["months"])
        mix_html = "".join(
            f'<div class="mix-row"><span>{_label(k)}</span>'
            f"<span>{_fmt_cny(v)}</span></div>"
            for k, v in sorted(s["stage_mix"].items(), key=lambda kv: kv[1], reverse=True)
        )
        card_parts.append(
            f'<div class="sup-card" data-name="{_esc(s["supplier"].lower())}" '
            f'data-stages="{stages_attr}" data-months="{months_attr}">'
            f"<h4>{_esc(s['supplier'])}</h4>"
            f'<div class="tile-num">{_fmt_cny(s["amount_cny"])}</div>'
            f"{mix_html}</div>"
        )
    cards = "".join(card_parts)
    return (
        "<p>Full supplier directory with client-side search (no server needed). "
        "Top-10 cards show each supplier's stage mix.</p>"
        '<div class="filters">'
        '<input id="sup-search" type="search" placeholder="Search supplier…" '
        'aria-label="Search supplier">'
        '<select id="sup-stage" aria-label="Filter by stage">'
        '<option value="">All stages</option></select>'
        '<select id="sup-month" aria-label="Filter by month">'
        '<option value="">All months</option></select>'
        "</div>"
        f'<h3>Top {len(sup["top"])} suppliers</h3>'
        f'<div class="cards" id="sup-cards">{cards}</div>'
        + table
    )


def _render_benchmarks(d: dict) -> str:
    bm = d["benchmarks"]
    parts = [
        "<p>Market price ranges and lead times for every production stage, "
        "gathered from public sources (every source opened and verified "
        "2026-09-05). Each card lists the key ranges and their sources.</p>"
    ]
    if bm["rows"]:
        rows = [
            [
                _label(r["stage"]),
                _esc(r["metric"]),
                f'{r["our_value"]:,.1f}',
                f'{r["market_low"]:,.1f} – {r["market_high"]:,.1f}',
                _esc(r["unit"]),
                f'<a href="{_esc(r["source_url"])}" target="_blank" '
                f'rel="noopener">{_esc(r["source_title"])}</a> '
                f'({_esc(r["accessed_on"])})',
                ("within market"
                 if r["market_low"] <= r["our_value"] <= r["market_high"]
                 else ("above market" if r["our_value"] > r["market_high"]
                       else "below market")),
            ]
            for r in bm["rows"]
        ]
        parts += [
            _chart("bench", 360),
            _table(["Stage", "Metric", "Ours", "Market range", "Unit", "Source",
                    "Verdict"], rows),
        ]
    cards = []
    for s in bm["stages"]:
        highs = "".join(f"<li>{_esc(h)}</li>" for h in s["highlights"])
        srcs = " · ".join(
            f'<a href="{_esc(src["url"])}" target="_blank" '
            f'rel="noopener">{_esc(src["title"])}</a>'
            for src in s["sources"]
        )
        cards.append(
            f'<div class="bench-card"><h4>{_esc(s["title"])}</h4>'
            f'<p class="lead">{_esc(s["intro"])}</p>'
            + (f"<ul>{highs}</ul>" if highs else "")
            + (f'<div class="srcs">{srcs}</div>' if srcs else "")
            + "</div>"
        )
    if cards:
        parts.append('<div class="cards">' + "".join(cards) + "</div>")

    comp = d["optimizations"].get("market_comparison") or []
    if comp:
        parts.append("<h3>Our stage shares vs the market</h3>")
        parts.append(_table(
            ["Stage", "Our share", "H1-2026 spend", "Market reference"],
            [
                [_label(r["stage"]), f'{r["our_share_pct"]:.1f}%',
                 _fmt_cny(r["h1_2026_cny"]), _esc(r["market_ref"])]
                for r in comp
            ],
        ))
    return "".join(parts)


def _render_optimizations(d: dict) -> str:
    cards = "".join(
        f'<div class="opt-card"><h4>#{_esc(c["id"])} {_esc(c["title"])}</h4>'
        + (f'<div class="base">baseline {_fmt_cny(c["baseline_cny"])} '
           f'({_label(c["stage"])})</div>'
           if c.get("baseline_cny") else "")
        + (f'<div class="base">{_esc(c["baseline"])}</div>'
           if c.get("baseline") else "")
        + f'<div class="saving">estimated saving ~{_fmt_cny(c["saving_cny"])}'
        + (f' / 6 months (probability {c["prob"]:.0%}, effort {c["effort"]}, '
           f'saves {c["time_saved"]})' if c.get("prob") is not None else "")
        + "</div>"
        + (f'<div class="proof">{_esc(c["market_range"])}</div>'
           if c.get("market_range") else "")
        + (f'<div class="proof">{_esc(c["math"])}</div>' if c.get("math") else "")
        + (f'<div class="proof">{_esc(c["proof"])}</div>' if c.get("proof") else "")
        + "</div>"
        for c in d["optimizations"]["cards"]
    )
    rows = [
        [c["id"], _esc(c["title"]),
         _label(c["stage"]) if c.get("stage") else "",
         _fmt_cny(c["baseline_cny"]) if c.get("baseline_cny") else "",
         _fmt_cny(c["saving_cny"]),
         c.get("prob", ""), c.get("effort", ""), c.get("time_saved", "")]
        for c in d["optimizations"]["cards"]
    ]
    insights = d["optimizations"].get("insights") or []
    ins_html = ""
    if insights:
        ins_html = ("<h3>Why these, in plain words</h3><ul>"
                    + "".join(f"<li>{_esc(i)}</li>" for i in insights)
                    + "</ul>")
    return (
        "<p>Concrete saving opportunities, ranked by score "
        "(saving × probability ÷ effort). Each card shows the baseline cost, "
        "the saving estimate and the supporting evidence.</p>"
        f'<div class="cards">{cards}</div>'
        + ins_html
        + _table(["#", "Recommendation", "Stage", "Baseline", "Saving (6-mo)",
                  "Prob.", "Effort", "Time saved"], rows)
    )


def _render_glossary(d: dict) -> str:
    rows = [[r["zh"], r["en"], r["explanation"]] for r in d["glossary"]["rows"]]
    return (
        "<p>Chinese terms from the source spreadsheets, translated and "
        "explained in plain English.</p>"
        + _table(["中文 (zh)", "English", "What it means"], rows)
    )


TABS = [
    ("overview", "Overview", _render_overview),
    ("cost", "Cost structure", _render_cost),
    ("timelines", "Product timelines", _render_timelines),
    ("suppliers", "Suppliers", _render_suppliers),
    ("benchmarks", "Benchmarks", _render_benchmarks),
    ("optimizations", "Optimizations", _render_optimizations),
    ("glossary", "Glossary", _render_glossary),
]

CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; font: 15px/1.55 -apple-system, "Segoe UI", Roboto, sans-serif;
       background: #f5f7fa; color: #2d3436; }
header { background: #2d3436; color: #fff; padding: 14px 24px; position: sticky;
         top: 0; z-index: 5; }
header h1 { margin: 0; font-size: 18px; }
header .sub { opacity: .7; font-size: 12px; }
nav { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 10px; }
nav button { border: 0; background: #454d50; color: #dfe6e9; padding: 7px 14px;
             border-radius: 6px 6px 0 0; cursor: pointer; font-size: 14px; }
nav button.active { background: #f5f7fa; color: #2d3436; font-weight: 600; }
main { max-width: 1180px; margin: 0 auto; padding: 20px 24px 60px; }
.tab-panel { display: none; }
.tab-panel.active { display: block; }
h2 { margin: 8px 0 12px; } h3 { margin: 22px 0 8px; }
.lead { color: #636e72; }
.exec { background: #fff; border-left: 4px solid #6c5ce7; border-radius: 8px;
        padding: 14px 20px; margin: 10px 0; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.exec li { margin: 6px 0; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px,1fr));
         gap: 12px; margin: 14px 0; }
.tile, .opt-card, .sup-card, .bench-card { background: #fff; border-radius: 10px; padding: 14px 16px;
         box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.bench-card ul { margin: 6px 0; padding-left: 20px; }
.bench-card .srcs { font-size: 12px; color: #0984e3; margin-top: 8px; }
.tile-num { font-size: 24px; font-weight: 700; }
.tile-label { color: #636e72; font-size: 12px; text-transform: uppercase;
              letter-spacing: .04em; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px,1fr));
         gap: 12px; margin: 12px 0; }
.opt-card .saving { color: #00b894; font-weight: 700; margin: 6px 0; }
.opt-card .base, .proof { color: #636e72; font-size: 13px; }
.mix-row { display: flex; justify-content: space-between; font-size: 13px; }
.chart { background: #fff; border-radius: 10px; margin: 10px 0;
         box-shadow: 0 1px 3px rgba(0,0,0,.08); }
table { border-collapse: collapse; width: 100%; background: #fff; font-size: 13.5px;
        margin: 8px 0 18px; box-shadow: 0 1px 3px rgba(0,0,0,.08); border-radius: 8px; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid #ecf0f1; }
th { background: #dfe6e9; position: sticky; top: 0; }
details summary { cursor: pointer; font-weight: 600; margin: 8px 0; }
.filters { display: flex; gap: 10px; margin: 10px 0; flex-wrap: wrap; }
.filters input, .filters select { padding: 8px 10px; border: 1px solid #b2bec3;
                                  border-radius: 6px; font-size: 14px; }
.hidden { display: none !important; }
footer { text-align: center; color: #b2bec3; font-size: 12px; padding: 20px; }
"""


def render_html(data: dict, generated_from: str) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    payload = payload.replace("<", "\\u003c")  # safe inside <script>
    palette = _stage_palette(data["cost_structure"]["heatmap"]["stages"])
    months = data["cost_structure"]["months"]
    period = f"{months[0]}…{months[-1]}" if months else ""
    tabs_html = "".join(
        _section(tid, title, fn(data), active=(i == 0))
        for i, (tid, title, fn) in enumerate(TABS)
    )
    nav_html = "".join(
        f'<button role="tab" data-tab="{tid}" '
        f'{"active" if i == 0 else ""}>{title}</button>'
        for i, (tid, title, _fn) in enumerate(TABS)
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Action Figures — Production Cost Dashboard</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>Action Figures — Production Cost Dashboard</h1>
  <div class="sub">Data source: {generated_from} · {period} · all amounts in CNY</div>
  <nav id="tabs">{nav_html}</nav>
</header>
<main>
{tabs_html}
</main>
<footer>Generated by dashboard/build_dashboard.py · ECharts 5 (CDN) · HTML tables work without JS</footer>
<script id="dash-data" type="application/json">{payload}</script>
<script src="{CDN}"></script>
<script>
(function () {{
  var DATA = JSON.parse(document.getElementById('dash-data').textContent);
  var charts = [];

  function init() {{
    if (typeof echarts === 'undefined') return;  // offline: tables remain
    var cs = DATA.cost_structure;
    var stageNames = cs.heatmap.stages;
    var palette = {json.dumps(palette)};
    var labelMap = {json.dumps(STAGE_LABELS)};

    function mk(id, option) {{
      var el = document.getElementById('chart-' + id);
      if (!el) return;
      var c = echarts.init(el);
      c.setOption(option);
      charts.push(c);
    }}
    function tooltip() {{
      return {{ trigger: 'item', formatter: function (p) {{
        return p.name + '<br>¥' + Number(p.value).toLocaleString();
      }} }};
    }}

    // Overview sankey
    mk('sankey', {{
      tooltip: {{ trigger: 'item' }},
      series: [{{ type: 'sankey', left: 10, right: 120, top: 10, bottom: 10,
        emphasis: {{ focus: 'adjacency' }},
        label: {{ fontSize: 12 }},
        data: DATA.overview.sankey.nodes,
        links: DATA.overview.sankey.links }}]
    }});

    // Cost structure: bars / stacked / treemap / heatmap
    var stageTotals = cs.stages.map(function (r) {{ return r.amount_cny; }});
    mk('bar', {{
      tooltip: tooltip(),
      grid: {{ left: 60 }},
      xAxis: {{ type: 'category', data: stageNames.map(function(s){{return labelMap[s]||s;}}),
               axisLabel: {{ rotate: 30 }} }},
      yAxis: {{ type: 'value', name: 'CNY' }},
      series: [{{ type: 'bar', data: stageTotals, itemStyle: {{ color: function (p) {{ return palette[p.dataIndex % palette.length]; }} }} }}]
    }});
    var byStage = {{}};
    cs.by_month.forEach(function (r) {{
      (byStage[r.stage] = byStage[r.stage] || {{}})[r.month] = r.amount_cny;
    }});
    mk('stack', {{
      tooltip: {{ trigger: 'axis' }},
      legend: {{ bottom: 0, type: 'scroll' }},
      grid: {{ left: 60, bottom: 60 }},
      xAxis: {{ type: 'category', data: cs.months }},
      yAxis: {{ type: 'value', name: 'CNY' }},
      series: stageNames.map(function (s, i) {{
        return {{ name: labelMap[s] || s, type: 'bar', stack: 'm',
                 color: palette[i % palette.length],
                 data: cs.months.map(function (m) {{ return (byStage[s] || {{}})[m] || 0; }}) }};
      }})
    }});
    mk('treemap', {{
      tooltip: tooltip(),
      series: [{{ type: 'treemap', roam: false, breadcrumb: {{ show: true, bottom: 0 }},
        label: {{ show: true, formatter: '{{b}}' }},
        data: cs.stages.map(function (r, i) {{
          return {{ name: labelMap[r.stage] || r.stage, value: r.amount_cny,
                   itemStyle: {{ color: palette[i % palette.length] }} }};
        }}) }}]
    }});
    var mi = cs.heatmap.months.indexOf.bind(cs.heatmap.months);
    var si = cs.heatmap.stages.indexOf.bind(cs.heatmap.stages);
    var hmData = cs.heatmap.cells.map(function (c) {{ return [mi(c[0]), si(c[1]), c[2]]; }});
    var hmMax = Math.max.apply(null, hmData.map(function (c) {{ return c[2]; }}).concat([1]));
    mk('heatmap', {{
      tooltip: {{ position: 'top' }},
      grid: {{ left: 120, bottom: 70, right: 30 }},
      xAxis: {{ type: 'category', data: cs.months, splitArea: {{ show: true }} }},
      yAxis: {{ type: 'category', data: cs.heatmap.stages.map(function(s){{return labelMap[s]||s;}}),
               axisLabel: {{ fontSize: 11 }} }},
      visualMap: {{ min: 0, max: hmMax, calculable: true, orient: 'horizontal',
        left: 'center', bottom: 0, inRange: {{ color: ['#dfe6e9', '#6c5ce7'] }} }},
      series: [{{ type: 'heatmap', data: hmData,
        label: {{ show: true, formatter: function (p) {{ return p.value[2] ? Math.round(p.value[2]/1000) + 'k' : ''; }} }} }}]
    }});

    // Gantt: custom series, one row per style
    var g = DATA.timelines.gantt;
    var start = Math.min.apply(null, g.flatMap(function (row) {{
      return row.stages.map(function (s) {{ return +new Date(s.start_date); }});
    }}));
    var end = Math.max.apply(null, g.flatMap(function (row) {{
      return row.stages.map(function (s) {{ return +new Date(s.end_date); }});
    }}));
    var renderGantt = {{ type: 'custom', renderItem: function (params, api) {{
      var yIdx = api.value(0), s = +new Date(api.value(1)), e = +new Date(api.value(2));
      var ptS = api.coord([s, yIdx]), ptE = api.coord([e, yIdx]);
      var h = Math.min(ptE[0] - ptS[0] - 2, 20);
      var rect = {{ type: 'rect', shape: {{ x: ptS[0], y: ptS[1] - h / 2, width: Math.max(ptE[0] - ptS[0], 2), height: h }},
        style: {{ fill: api.visual('color') }} }};
      return {{ type: 'group', children: [rect] }};
    }}}};
    mk('gantt', {{
      tooltip: {{ formatter: function (p) {{
        return p.name + '<br>' + new Date(p.value[1]).toISOString().slice(0,10)
          + ' → ' + new Date(p.value[2]).toISOString().slice(0,10);
      }} }},
      grid: {{ left: 90, right: 20 }},
      xAxis: {{ type: 'time', min: start, max: end }},
      yAxis: {{ type: 'category', data: g.map(function (r) {{ return r.style_no; }}) }},
      series: stageNames.map(function (st, i) {{
        return Object.assign({{}}, renderGantt, {{
          name: labelMap[st] || st, color: palette[i % palette.length],
          encode: {{ x: [1, 2], y: 0 }},
          data: g.flatMap(function (row, ri) {{
            return row.stages.filter(function (s) {{ return s.stage === st; }})
              .map(function (s) {{
                return {{ value: [ri, s.start_date, s.end_date, row.style_no + ' ' + (labelMap[st]||st)],
                         name: row.style_no + ' · ' + (labelMap[st]||st) }};
              }});
          }})
        }});
      }})
    }});

    // Benchmarks: ours vs market range (only when CSV rows exist)
    var bm = DATA.benchmarks.rows || [];
    if (bm.length) mk('bench', {{
      tooltip: {{ trigger: 'axis' }},
      grid: {{ left: 70, bottom: 90 }},
      xAxis: {{ type: 'category',
        data: bm.map(function (r) {{ return (labelMap[r.stage]||r.stage) + ' / ' + r.metric; }}),
        axisLabel: {{ rotate: 35, fontSize: 10 }} }},
      yAxis: {{ type: 'value', name: bm.length ? bm[0].unit : '' }},
      series: [
        {{ name: 'Our value', type: 'bar', data: bm.map(function (r) {{ return r.our_value; }}),
           itemStyle: {{ color: '#6c5ce7' }} }},
        {{ name: 'Market range', type: 'custom', renderItem: function (params, api) {{
          var lo = api.coord([params.dataIndex, api.value(1)]);
          var hi = api.coord([params.dataIndex, api.value(2)]);
          return {{ type: 'group', children: [
            {{ type: 'rect', shape: {{ x: lo[0] - 1, y: hi[1], width: 2, height: lo[1] - hi[1] }},
               style: {{ fill: '#00b894' }} }},
            {{ type: 'rect', shape: {{ x: lo[0] - 8, y: hi[1] - 1, width: 16, height: 2 }},
               style: {{ fill: '#00b894' }} }},
            {{ type: 'rect', shape: {{ x: lo[0] - 8, y: lo[1] - 1, width: 16, height: 2 }},
               style: {{ fill: '#00b894' }} }}] }};
        }}, data: bm.map(function (r) {{ return [r.market_low, r.market_high]; }}),
           encode: {{ x: -1, y: [1, 2] }} }}
      ]
    }});

    window.addEventListener('resize', function () {{
      charts.forEach(function (c) {{ c.resize(); }});
    }});
  }}

  // Tabs
  var nav = document.getElementById('tabs');
  nav.addEventListener('click', function (e) {{
    var btn = e.target.closest('button[data-tab]');
    if (!btn) return;
    nav.querySelectorAll('button').forEach(function (b) {{ b.classList.remove('active'); }});
    btn.classList.add('active');
    document.querySelectorAll('.tab-panel').forEach(function (p) {{
      p.classList.toggle('active', p.id === btn.dataset.tab);
    }});
    charts.forEach(function (c) {{ c.resize(); }});
  }});

  // Supplier search / filters (client-side)
  var search = document.getElementById('sup-search');
  var stageSel = document.getElementById('sup-stage');
  var monthSel = document.getElementById('sup-month');
  if (search) {{
    var seen = {{}};
    DATA.suppliers.all.forEach(function (s) {{
      Object.keys(s.stage_mix).forEach(function (st) {{ seen[st] = 1; }});
      s.months.forEach(function (m) {{ seen[m] = 1; }});
    }});
    Object.keys(seen).sort().forEach(function (v) {{
      var o1 = document.createElement('option'); o1.value = v; o1.textContent = v;
      var o2 = document.createElement('option'); o2.value = v; o2.textContent = v;
      stageSel.appendChild(o1); monthSel.appendChild(o2);
    }});
    function apply() {{
      var q = search.value.trim().toLowerCase();
      var st = stageSel.value, mo = monthSel.value;
      document.querySelectorAll('#sup-cards .sup-card').forEach(function (card) {{
        var ok = !q || card.dataset.name.indexOf(q) >= 0;
        if (st) ok = ok && card.dataset.stages.split(';').indexOf(st) >= 0;
        if (mo) ok = ok && card.dataset.months.split(';').indexOf(mo) >= 0;
        card.classList.toggle('hidden', !ok);
      }});
    }}
    search.addEventListener('input', apply);
    stageSel.addEventListener('change', apply);
    monthSel.addEventListener('change', apply);
  }}

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
}})();
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--reports",
        type=Path,
        default=MAIN_CHECKOUT_REPORTS,
        help="reports/ directory with audit/benchmarks/optimization/translation CSVs",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "dist" / "index.html",
    )
    args = ap.parse_args(argv)

    if (args.reports / "audit" / "stage_summary.csv").exists():
        data = build_dashboard_data(args.reports)
        src = f"reports/ ({args.reports})"
    else:
        data = build_mock_data()
        src = "MOCK synthetic data (real reports not ready yet)"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_html(data, src), encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size:,} bytes) from {src}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
