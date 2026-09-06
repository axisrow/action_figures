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
from urllib.parse import quote

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from action_figures.dashboard_data import (  # noqa: E402
    build_dashboard_data,
    load_supplier_translations,
)

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
textile_accessories,18,5000.00,0.8
admin_other,9,3000.00,0.5
unclassified,7,1200.00,0.2
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
2026-01,design_prototyping,1200.00
2026-02,design_prototyping,800.00
2026-03,textile_accessories,3000.00
2026-05,assembly_processing,15000.00
2026-02,admin_other,1500.00
2026-03,admin_other,1500.00
2026-04,unclassified,1200.00
"""

MOCK_BY_DAY_STAGE = """date,stage,amount_cny,n_lines
2026-01-05,tooling_molds,45000.00,18
2026-01-25,tooling_molds,37000.00,13
2026-02-08,tooling_molds,38000.00,12
2026-02-28,tooling_molds,32000.00,10
2026-03-15,tooling_molds,15000.00,8
2026-01-06,painting_printing,31000.00,40
2026-02-11,painting_printing,48000.00,52
2026-03-09,painting_printing,51000.00,60
2026-04-12,painting_printing,34000.00,51
2026-01-08,raw_materials,40000.00,42
2026-02-09,raw_materials,36000.00,38
2026-03-10,raw_materials,29000.00,31
2026-04-08,raw_materials,16000.00,24
2026-01-12,injection_molding,22000.00,25
2026-02-14,injection_molding,35000.00,31
2026-03-16,injection_molding,8000.00,14
2026-04-09,injection_molding,9000.00,28
2026-01-14,packaging,9000.00,18
2026-02-16,packaging,14000.00,22
2026-03-11,packaging,12000.00,16
2026-04-10,packaging,12000.00,16
2026-01-15,logistics_freight,6000.00,12
2026-02-17,logistics_freight,8000.00,14
2026-03-12,logistics_freight,7000.00,13
2026-04-11,logistics_freight,7000.00,14
2026-01-20,design_prototyping,1200.00,2
2026-02-18,design_prototyping,800.00,2
2026-03-18,textile_accessories,3000.00,6
2026-05-22,assembly_processing,15000.00,29
2026-02-25,admin_other,1500.00,4
2026-03-27,admin_other,1500.00,5
2026-04-15,unclassified,1200.00,7
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

# Stage metadata for the Process Explorer menu (canonical taxonomy copy —
# labels/descriptions are project text, not financial data), orders 1-12.
MOCK_STAGES = """stage_id,order,label_en,description_en,zh_keys
design_prototyping,1,Design & Prototyping,"Design and prototyping: artists draw and sculpt every part digitally, then sample parts are 3D printed and revised until approved. It is paid per model before any production can start, so it does not get cheaper with bigger orders.",画图;扫描;打样;做样;样办;打版;打印;3D;修精细;改神态;拆件;设计;雕刻
tooling_molds,2,Tooling & Molds,"Tooling and molds: steel, aluminum or resin molds are made before any plastic part can be mass-produced. The project's largest one-off investment — many small cheap molds instead of a few expensive ones, typical for small-batch production.",开模;模具;模费;搪胶模;合金模;铜模;模芯;做模;冲模;线割;钢模;铝模
raw_materials,3,Raw Materials,"Raw materials and consumables: plastic compound, paint, glue, thinner, screws, magnets and other workshop supplies consumed by production and assembly.",原料;材料;辅料;PVC;塑胶;颜料;胶水;开油水;酒精;焊锡;螺丝;磁铁;铜管;铜片;五金;海绵;软胶;红蜡;胶片;钻头;钻嘴;美纹纸;插销;弹簧;保险销;配件
injection_molding,4,Injection Molding,"Molded parts production: factory runs that inject, cast or rotocast plastic parts — soles, buckles, weapons, helmets — from the molds. Paid per part, so it scales with the size of the production run.",啤货;注塑;模压;成型;搪胶;头雕货款;头仔货款;手臂;手枪;压铸
painting_printing,5,Painting & Printing,"Painting and printing: spray-painted parts, hand-painted head sculpts, fabric printing, decals and plating. Very labor-intensive, which makes it a major per-unit cost for collectible figures.",喷油;喷漆;上色;丝印;移印;印刷;印花;电镀;涂装;水贴;植毛;植绒;染色
textile_accessories,6,Textiles & Accessories,"Textiles and garment accessories: fabric, leather, thread, zippers, buttons and woven labels for the figures' outfits. Tailoring is the backbone of cost for clothed 1/6 scale figures.",布;线;织唛;织带;皮;拉链;扣;鸡眼;服装;么术贴;橡筋;丈巾;棉带;绳;枪带
assembly_processing,7,Assembly & Handwork,"Assembly and handwork: cutting fabric, sewing garments, trimming threads, turning metal parts and gluing everything into the finished figure. Mostly manual labor paid per unit or per operation.",手工费;做手工;剪线;切割;车件;折弯;组装;装配;加工;冲压;焊接;焊扣;焊配;塞棉;烫片;绣花;过朴;木枪;木头;做头发
packaging,8,Packaging,"Packaging: boxes, cartons, blister trays and manuals. Almost absent in this project — figures ship as collectibles without retail boxes.",包装;彩盒;纸箱;封箱;泡壳;吸塑;说明书;防潮珠;贴纸
qc_testing,9,QC & Testing,"Quality control and testing: product inspections and laboratory safety tests. Billed per report or per inspection day, so it costs relatively more on small production runs.",检测;测试;验货
logistics_freight,10,Logistics & Freight,"Logistics and freight: courier and shipping fees for samples, parts and materials moving between the studio and outsourcing partners. Many small shipments — each cheap, but very frequent.",运费;快递;物流;寄件;寄付;到付;邮费;邮寄;寄货
admin_other,11,Admin & Other,"Admin and office overhead: business trips, fuel, tolls, office equipment and meals — everything not part of physically making the figures.",出差;油费;高速费;办公;空调;年饭;午餐;餐饮;红酒;路由器;维修;车间修
unclassified,12,Unclassified,Lines the taxonomy could not classify with confidence; reviewed manually in unclassified.csv.,
"""

MOCK_FILES = {
    "audit/stage_summary.csv": MOCK_STAGE_SUMMARY,
    "audit/stages.csv": MOCK_STAGES,
    "audit/by_month_stage.csv": MOCK_BY_MONTH_STAGE,
    "audit/by_day_stage.csv": MOCK_BY_DAY_STAGE,
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

# Tab icon: orange "A" + amber "F" on the dashboard-blue tile (32x32, palette
# colors from CSS/PALETTE). Inlined as a percent-encoded SVG data URI so the
# page makes no /favicon.ico request — nothing to 404, no extra file to ship.
FAVICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
    "<rect width='32' height='32' rx='7' fill='#0984e3'/>"
    "<path d='M5 24 11 8 17 24 M8 18h6' fill='none' stroke='#e17055' "
    "stroke-width='3' stroke-linecap='round' stroke-linejoin='round'/>"
    "<path d='M21 24V8h7M21 16h6' fill='none' stroke='#fdcb6e' "
    "stroke-width='3' stroke-linecap='round'/>"
    "</svg>"
)
FAVICON = "data:image/svg+xml," + quote(FAVICON_SVG, safe="'/:=,")

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


def _stage_menu_item(s: dict) -> str:
    return (
        f'<li><a class="stage-link" href="#/stage/{_esc(s["stage_id"])}">'
        f'<span class="stage-no">{s["order"]}</span>'
        f'<span class="stage-name">{_esc(s["label_en"])}</span>'
        f'<span class="stage-amount">{_fmt_cny(s["amount_cny"])} · '
        f"{s['share_pct']:.1f}%</span></a>"
        f'<p class="hint">{_esc(s["description_en"])}</p></li>'
    )


def _render_stage_menu(d: dict) -> str:
    """Process Explorer menu: the production stages in process order, the two
    service buckets collapsed into Other, plus a static no-JS table twin."""
    menu_stages = d.get("stages") or []
    if not menu_stages:
        return ""
    production = [s for s in menu_stages if not s["service"]]
    service = [s for s in menu_stages if s["service"]]
    other = ""
    if service:
        amount = sum(s["amount_cny"] for s in service)
        share = sum(s["share_pct"] for s in service)
        other = (
            f'<details id="stage-other"><summary>Other — admin &amp; '
            f"unclassified ({_fmt_cny(amount)}, {share:.1f}% of spend)</summary>"
            '<ol class="stage-menu">'
            + "".join(_stage_menu_item(s) for s in service)
            + "</ol></details>"
        )
    table = _table(
        ["#", "Stage", "What it is", "Total", "Share"],
        [
            [
                str(s["order"]),
                _esc(s["label_en"]),
                _esc(s["description_en"]),
                _fmt_cny(s["amount_cny"]),
                f'{s["share_pct"]:.1f}%',
            ]
            for s in menu_stages
        ],
    )
    return (
        f"<h3>How an action figure is made — {len(production)} stages</h3>"
        '<p class="hint">The real production order, from first sketch to '
        "shipped carton. Click a stage to open its page.</p>"
        '<ol class="stage-menu" id="stage-menu">'
        + "".join(_stage_menu_item(s) for s in production)
        + "</ol>"
        + other
        + "<details><summary>Stage menu (no-JS fallback)</summary>"
        + table
        + "</details>"
    )


def _render_ideal_timeline(d: dict) -> str:
    """PE-4: reference Gantt of the ideal production cycle on the Overview.

    Static benchmark durations (issue #8): ECharts custom-series chart with a
    no-JS table twin (stage → week range → typical duration → source link).
    Clicking a bar is routed client-side to the stage page.
    """
    it = d.get("ideal_timeline") or {}
    bars = it.get("bars") or []
    if not bars:
        return ""
    rows = [
        [
            _esc(b["label"] + (f" ({b['variant']})" if b["variant"] else "")),
            f'{b["start_week"]}–{b["end_week"]}',
            f'{b["min_weeks"]}–{b["max_weeks"]} wks',
            f'<a href="{_esc(b["source_url"])}" target="_blank" '
            f'rel="noopener">{_esc(b["source_file"])}</a>',
        ]
        for b in bars
    ]
    lo, hi = it["total_weeks"]
    return (
        "<h3>Ideal production timeline (reference)</h3>"
        f'<p class="hint">{_esc(it["disclaimer"])}. Weeks are counted from '
        f"project start on a fixed 0–{it['weeks_axis'][1]} axis; overlapping "
        "bars run in parallel. Whole cycle envelope: "
        f"{lo}–{hi} weeks. Sources per stage are linked below.</p>"
        + _chart("ideal", max(240, 46 * len(it["rows"]) + 70))
        + "<details><summary>Ideal timeline (no-JS fallback)</summary>"
        + _table(["Stage", "Weeks (start–end)", "Typical duration", "Source"], rows)
        + "</details>"
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
    ua = ov.get("unattributed") or {}
    if ua.get("n_lines"):
        note += (
            f'<p class="lead">Data quality: {ua["share_pct"]:.1f}% of spend is '
            "unattributed to a supplier "
            f"({_fmt_cny(ua['amount_cny'])} across {ua['n_lines']} lines) — "
            "shown as Unattributed everywhere.</p>"
        )
    cards = "".join(
        f'<div class="opt-card"><h4>{_esc(c["title"])}</h4>'
        f'<div class="saving">saves ~{_fmt_cny(c["saving_cny"])}</div>'
        f'<div class="proof">{_esc(c["proof"])}</div></div>'
        for c in ov["summary"]["top3_optimizations"]
    )
    fallback_suppliers = [
        [
            _esc(r["supplier"]),
            ", ".join(_label(s) for s in r["stages"]),
            _fmt_cny(r["total_cny"]),
            f'{r["share_pct"]:.1f}%',
        ]
        for r in ov["sankey"].get("top_suppliers", [])
    ]
    fallback = (
        "<h4>By stage</h4>"
        + _table(
            ["Stage", "Total", "Share"],
            [
                [
                    _label(r["stage"]),
                    _fmt_cny(r["amount_cny"]),
                    f'{r["share_pct"]:.1f}%',
                ]
                for r in d["cost_structure"][STAGES]
            ],
        )
        + "<h4>Top suppliers</h4>"
        + _table(
            ["Supplier", "Stages", "Total", "Share"], fallback_suppliers
        )
    )
    return (
        '<p class="lead">Where the money goes across production stages and '
        "suppliers. All amounts in CNY (¥).</p>"
        + exec_html
        + note
        + f'<div class="tiles">{tiles_html}</div>'
        + _render_stage_menu(d)
        + _render_ideal_timeline(d)
        + "<h3>Money flow: spend → stages → suppliers</h3>"
        + '<p class="hint">Read left to right: each stage\'s spend splits into '
        "the suppliers paid for it — top 10 individually, the rest lumped "
        "into Others.</p>"
        + _chart("sankey", 640)
        + "<details open><summary>Tables (no-JS fallback)</summary>"
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
        "<p>Four views of the same numbers: totals, monthly trend, shares and "
        "a month×stage matrix.</p>"
        + "<h3>Total spend by stage</h3>"
        + '<p class="hint">One bar per production stage — taller means more '
        "spend over the whole period.</p>"
        + _chart("bar")
        + "<h3>Monthly spend by stage</h3>"
        + '<p class="hint">Each column is one month, split by stage — watch '
        "the mix shift over time.</p>"
        + _chart("stack")
        + "<h3>Share of total spend</h3>"
        + '<p class="hint">Each block\'s area is that stage\'s slice of the '
        "total.</p>"
        + _chart("treemap")
        + "<h3>Month × stage heatmap</h3>"
        + '<p class="hint">Darker cells mark the months where a stage cost '
        "the most.</p>"
        + _chart("heatmap")
        + "<details open><summary>Tables (no-JS fallback)</summary>"
        + _table(["Stage", "Total", "Share", "Lines"], stage_rows)
        + _table(["Month", *[_label(s) for s in cs["heatmap"]["stages"]]], month_rows)
        + "</details>"
    )


def _render_timelines(d: dict) -> str:
    tl = d["timelines"]
    rows = []
    for g in tl["gantt"]:
        stages = " → ".join(
            f'{_label(s["stage"])} ({s["start_date"]}..{s["end_date"]})'
            for s in g["stages"]
        )
        rows.append([g["style_no"], str(g["total_days"]), stages])
    notes = ""
    if tl.get("gantt_truncated"):
        notes += (
            f'<p class="lead">Showing top {len(tl["gantt"])} of '
            f'{tl.get("gantt_total_styles", len(tl["gantt"]))} styles by spend '
            "— full list in by_style_timeline.csv.</p>"
        )
    un = tl.get("unlinked") or {}
    if un.get("n_lines"):
        amount = f" / {_fmt_cny(un['amount_cny'])}" if un["amount_cny"] else ""
        notes += (
            f'<p class="lead">{un["n_lines"]} lines{amount} not linked to a '
            "style — excluded from the chart above.</p>"
        )
    return (
        "<p>When each style moved through production, drawn from payment dates.</p>"
        + "<h3>Production timeline per style</h3>"
        + '<p class="hint">Each row is a style; bars show when every stage '
        "was paid. Re-sort the rows by total spend or by duration below.</p>"
        + notes
        + '<div class="filters"><select id="gantt-sort" aria-label="Sort styles by">'
        '<option value="spend">By total spend</option>'
        '<option value="duration">By duration</option></select></div>'
        + _chart("gantt", max(360, 60 * len(tl["gantt"])))
        + "<details open><summary>Table (no-JS fallback)</summary>"
        + _table(["Style", "Span (days)", "Stages"], rows)
        + "</details>"
    )


def _render_suppliers(d: dict) -> str:
    sup = d["suppliers"]
    ua = sup.get("unattributed") or {}
    explainer = ""
    if ua.get("n_lines"):
        amount = f" / {_fmt_cny(ua['amount_cny'])}" if ua["amount_cny"] else ""
        explainer = (
            f'<p class="lead">{ua["n_lines"]} rows{amount} '
            f'({ua["share_pct"]:.1f}% of spend) have no supplier recorded '
            "— lump-sum internal payments. They are shown as Unattributed "
            "and pinned last.</p>"
        )
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
        + explainer
        + '<div class="filters">'
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
            "<h3>Ours vs market range</h3>"
            '<p class="hint">Purple bars are our values; green brackets show '
            "the market range — a bar inside its bracket is within market.</p>",
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
.hint { color: #636e72; font-size: 13.5px; margin: 4px 0 8px; }
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
.stage-menu { list-style: none; margin: 10px 0; padding: 0; }
.stage-menu li { background: #fff; border-radius: 10px; margin: 8px 0;
                 box-shadow: 0 1px 3px rgba(0,0,0,.08); padding: 10px 14px; }
.stage-link { display: flex; align-items: center; gap: 10px; text-decoration: none;
              color: #2d3436; font-weight: 600; }
.stage-link:hover .stage-name { color: #0984e3; }
.stage-no { background: #dfe6e9; border-radius: 50%; min-width: 26px; height: 26px;
            display: inline-flex; align-items: center; justify-content: center;
            font-size: 13px; flex: none; }
.stage-name { flex: 1 1 auto; }
.stage-amount { color: #636e72; font-weight: 400; font-size: 13.5px; }
.stage-menu .hint { margin: 4px 0 0 36px; font-size: 13px; }
a.back { display: inline-block; margin: 6px 0 10px; color: #0984e3;
         text-decoration: none; }
a.back:hover { text-decoration: underline; }
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
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
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
<section id="stage-view" class="tab-panel" role="region" aria-label="Stage detail">
  <p><a class="back" href="#/overview">← Back to overview</a></p>
  <h2 id="stage-title"></h2>
  <p id="stage-desc" class="lead"></p>
  <div id="stage-stats" class="tiles"></div>
  <p class="hint">These are payments by date, not the physical production cycle — a bar means the month the invoice was paid, not when the work happened.</p>
  <p class="lead" id="stage-plate" hidden><strong>Not booked in this expense ledger.</strong> Costs for this stage are tracked outside these spreadsheets (forensic review), so the charts are hidden. Any rows in the tables below are residual entries, not the real cost of this stage.</p>
  <div class="cards">
    <div class="opt-card" id="stage-slot-monthly"><h4>Spend by month</h4>
      <div class="chart" id="stage-chart-monthly" style="height:300px"></div></div>
    <div class="opt-card" id="stage-slot-daily"><h4>Spend by day (7-day average)</h4>
      <div class="chart" id="stage-chart-daily" style="height:300px"></div></div>
    <div class="opt-card" id="stage-slot-suppliers"><h4>Top suppliers</h4>
      <div id="stage-tbl-suppliers"></div></div>
    <div class="opt-card" id="stage-slot-styles"><h4>Top styles</h4>
      <div id="stage-tbl-styles"></div></div>
  </div>
</section>
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

    // Overview sankey: Spend -> stages (colored) -> top suppliers + Others (gray)
    mk('sankey', {{
      tooltip: {{ trigger: 'item', formatter: function (p) {{
        return (labelMap[p.name] || p.name) + '<br>¥' + Number(p.value).toLocaleString();
      }} }},
      series: [{{ type: 'sankey', left: 10, right: 180, top: 10, bottom: 10,
        nodeAlign: 'justify', nodeWidth: 14, nodeGap: 8,
        emphasis: {{ focus: 'adjacency' }},
        label: {{ fontSize: 11, overflow: 'truncate', width: 170,
          formatter: function (p) {{ return labelMap[p.name] || p.name; }} }},
        lineStyle: {{ color: 'source', opacity: 0.35 }},
        levels: [{{ depth: 2, itemStyle: {{ color: '#b2bec3' }} }}],
        data: DATA.overview.sankey.nodes.map(function (n) {{
          var si = stageNames.indexOf(n.name);
          if (n.name === 'Spend')
            return Object.assign({{}}, n, {{ itemStyle: {{ color: '#2d3436' }} }});
          if (si >= 0)
            return Object.assign({{}}, n, {{ itemStyle: {{ color: palette[si % palette.length] }} }});
          return n;  // suppliers + Others stay gray via levels
        }}),
        links: DATA.overview.sankey.links }}]
    }});

    // Ideal production timeline (reference): custom-series Gantt, weeks 0-26.
    // Light band = fastest→slowest envelope, solid bar = fastest scenario;
    // variants (steel/aluminum tooling) overlay on one row, a parallel window
    // shares start weeks. Clicking a bar opens the stage page.
    var it = DATA.ideal_timeline;
    var idealEl = document.getElementById('chart-ideal');
    if (it && it.bars && it.bars.length && idealEl) {{
      var stageColor = {{}};
      stageNames.forEach(function (s, i) {{
        stageColor[s] = palette[i % palette.length];
      }});
      var idealBars = it.bars;
      var idealChart = echarts.init(idealEl);
      idealChart.setOption({{
        tooltip: {{ formatter: function (p) {{ return p.name; }} }},
        grid: {{ left: 160, right: 30, top: 10, bottom: 30 }},
        xAxis: {{ type: 'value', min: it.weeks_axis[0], max: it.weeks_axis[1],
                  name: 'week', interval: 2 }},
        yAxis: {{ type: 'category', inverse: true,
                  data: it.rows.map(function (r) {{ return r.label; }}),
                  axisLabel: {{ fontSize: 11 }} }},
        series: [{{
          type: 'custom',
          encode: {{ x: [1, 3], y: 0 }},
          data: idealBars.map(function (b) {{
            var label = b.label + (b.variant ? ' (' + b.variant + ')' : '');
            return {{
              value: [b.row, b.start_week, b.min_end_week, b.end_week],
              name: label + ' · weeks ' + b.start_week + '–' + b.end_week +
                    ' (typical ' + b.min_weeks + '–' + b.max_weeks + ' wks)'
            }};
          }}),
          renderItem: function (params, api) {{
            var row = api.value(0);
            var b = idealBars[params.dataIndex];
            var color = stageColor[b.stage_id] || '#74b9ff';
            var s = api.coord([api.value(1), row]);
            var fast = api.coord([api.value(2), row]);
            var slow = api.coord([api.value(3), row]);
            var h = 18;
            return {{ type: 'group', children: [
              {{ type: 'rect', transition: ['shape'],
                 shape: {{ x: s[0], y: s[1] - h / 2,
                           width: Math.max(slow[0] - s[0], 2), height: h }},
                 style: {{ fill: color, opacity: 0.3 }} }},
              {{ type: 'rect', transition: ['shape'],
                 shape: {{ x: s[0], y: s[1] - h / 4,
                           width: Math.max(fast[0] - s[0], 2), height: h / 2 }},
                 style: {{ fill: color }} }}
            ] }};
          }}
        }}]
      }});
      idealChart.on('click', function (p) {{
        var b = idealBars[p.dataIndex];
        if (b) location.hash = '#/stage/' + b.stage_id;
      }});
      charts.push(idealChart);
    }}

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

    // Gantt: custom series, one row per style; re-sortable by spend/duration
    var ganttRows = DATA.timelines.gantt;
    var renderGantt = {{ type: 'custom', renderItem: function (params, api) {{
      var yIdx = api.value(0), s = +new Date(api.value(1)), e = +new Date(api.value(2));
      var ptS = api.coord([s, yIdx]), ptE = api.coord([e, yIdx]);
      var h = Math.min(ptE[0] - ptS[0] - 2, 20);
      var rect = {{ type: 'rect', shape: {{ x: ptS[0], y: ptS[1] - h / 2, width: Math.max(ptE[0] - ptS[0], 2), height: h }},
        style: {{ fill: api.visual('color') }} }};
      return {{ type: 'group', children: [rect] }};
    }}}};
    function ganttOption(rows) {{
      var start = Math.min.apply(null, rows.flatMap(function (row) {{
        return row.stages.map(function (s) {{ return +new Date(s.start_date); }});
      }}));
      var end = Math.max.apply(null, rows.flatMap(function (row) {{
        return row.stages.map(function (s) {{ return +new Date(s.end_date); }});
      }}));
      return {{
        tooltip: {{ formatter: function (p) {{
          return p.name + '<br>' + new Date(p.value[1]).toISOString().slice(0,10)
            + ' → ' + new Date(p.value[2]).toISOString().slice(0,10);
        }} }},
        grid: {{ left: 90, right: 20 }},
        xAxis: {{ type: 'time', min: start, max: end }},
        yAxis: {{ type: 'category', data: rows.map(function (r) {{ return r.style_no; }}) }},
        series: stageNames.map(function (st, i) {{
          return Object.assign({{}}, renderGantt, {{
            name: labelMap[st] || st, color: palette[i % palette.length],
            encode: {{ x: [1, 2], y: 0 }},
            data: rows.flatMap(function (row, ri) {{
              return row.stages.filter(function (s) {{ return s.stage === st; }})
                .map(function (s) {{
                  return {{ value: [ri, s.start_date, s.end_date, row.style_no + ' ' + (labelMap[st]||st)],
                           name: row.style_no + ' · ' + (labelMap[st]||st) }};
                }});
            }})
          }});
        }})
      }};
    }}
    var ganttEl = document.getElementById('chart-gantt');
    if (ganttEl) {{
      var ganttChart = echarts.init(ganttEl);
      ganttChart.setOption(ganttOption(ganttRows));
      charts.push(ganttChart);
      var sortSel = document.getElementById('gantt-sort');
      if (sortSel) sortSel.addEventListener('change', function () {{
        var key = this.value === 'duration' ? 'total_days' : 'total_cny';
        var sorted = ganttRows.slice().sort(function (a, b) {{ return b[key] - a[key]; }});
        ganttChart.setOption(ganttOption(sorted), {{ notMerge: true }});
      }});
    }}

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
  function showTab(id) {{
    document.querySelectorAll('.tab-panel').forEach(function (p) {{
      p.classList.toggle('active', p.id === id);
    }});
    nav.querySelectorAll('button').forEach(function (b) {{
      b.classList.toggle('active', b.dataset.tab === id);
    }});
    charts.forEach(function (c) {{ c.resize(); }});
  }}
  nav.addEventListener('click', function (e) {{
    var btn = e.target.closest('button[data-tab]');
    if (!btn) return;
    showTab(btn.dataset.tab);
    if (location.hash.indexOf('#/stage/') === 0) {{
      // leaving a stage page via the tab bar: normalize the URL without a
      // history entry (file:// browsers may refuse replaceState — ignore)
      try {{ history.replaceState(null, '', '#/overview'); }} catch (err) {{}}
    }}
  }});

  // Hash router (Process Explorer): '#/overview' <-> '#/stage/<stage_id>'.
  // back/forward buttons work via the hashchange listener; a stage id the
  // payload does not know simply leaves the tab UI untouched.
  var stagesById = {{}};
  (DATA.stages || []).forEach(function (s) {{ stagesById[s.stage_id] = s; }});

  function fillStage(s) {{
    document.getElementById('stage-title').textContent =
      'Stage ' + s.order + ' — ' + s.label_en;
    document.getElementById('stage-desc').textContent = s.description_en;
    var page = (DATA.stage_pages || {{}})[s.stage_id] || {{}};
    var stats = page.stats || {{
      total_cny: s.amount_cny, share_pct: s.share_pct,
      n_lines: s.n_lines, avg_line_cny: 0
    }};
    document.getElementById('stage-stats').innerHTML =
      '<div class="tile"><div class="tile-num">¥' + Number(stats.total_cny).toLocaleString() +
      '</div><div class="tile-label">Stage total</div></div>' +
      '<div class="tile"><div class="tile-num">' + stats.share_pct.toFixed(1) +
      '%</div><div class="tile-label">Share of spend</div></div>' +
      '<div class="tile"><div class="tile-num">' + stats.n_lines +
      '</div><div class="tile-label">Expense lines</div></div>' +
      '<div class="tile"><div class="tile-num">¥' + Number(stats.avg_line_cny).toLocaleString() +
      '</div><div class="tile-label">Avg per line</div></div>';

    // GH#16 verdict stages render an explainer plate instead of charts
    var plate = document.getElementById('stage-plate');
    var showCharts = !page.not_booked && typeof echarts !== 'undefined';
    plate.hidden = !page.not_booked;
    ['stage-chart-monthly', 'stage-chart-daily'].forEach(function (id) {{
      document.getElementById(id).hidden = !showCharts;
    }});
    if (showCharts) {{
      if (!stageCharts.m) {{
        stageCharts.m = echarts.init(document.getElementById('stage-chart-monthly'));
        stageCharts.d = echarts.init(document.getElementById('stage-chart-daily'));
        charts.push(stageCharts.m, stageCharts.d);
      }}
      stageCharts.m.resize(); stageCharts.d.resize();
      stageCharts.m.setOption({{
        tooltip: {{ trigger: 'axis' }},
        grid: {{ left: 60, right: 20 }},
        xAxis: {{ type: 'category', data: (page.months || []).map(function (m) {{ return m.month; }}) }},
        yAxis: {{ type: 'value', name: 'CNY' }},
        series: [{{ type: 'bar', data: (page.months || []).map(function (m) {{ return m.amount_cny; }}),
                   itemStyle: {{ color: '#0984e3' }} }}]
      }}, true);
      stageCharts.d.setOption(dailyOption(page.days || []), true);
    }}

    fillStageTable('stage-tbl-suppliers', ['Supplier', 'Total', 'Share'],
      (page.top_suppliers || []).map(function (r) {{
        return [r.supplier, '¥' + Number(r.amount_cny).toLocaleString(),
                r.share_pct.toFixed(1) + '%'];
      }}));
    fillStageTable('stage-tbl-styles', ['Style', 'Total', 'Share'],
      (page.top_styles || []).map(function (r) {{
        return [r.style_no, '¥' + Number(r.amount_cny).toLocaleString(),
                r.share_pct.toFixed(1) + '%'];
      }}));
  }}

  var stageCharts = {{}};
  function fillStageTable(id, headers, rows) {{
    var html = '<table class="fallback"><thead><tr>' +
      headers.map(function (h) {{ return '<th>' + h + '</th>'; }}).join('') +
      '</tr></thead><tbody>' +
      rows.map(function (r) {{
        return '<tr>' + r.map(function (c) {{ return '<td>' + c + '</td>'; }}).join('') + '</tr>';
      }}).join('') + '</tbody></table>';
    document.getElementById(id).innerHTML = rows.length ? html :
      '<p class="hint">Nothing booked for this stage.</p>';
  }}

  function dailyOption(days) {{
    // a stage booked in stage_summary but absent from by_day_stage gets an
    // empty-but-valid option — days[0] must never be dereferenced blindly
    if (!days.length) return {{ series: [] }};
    // calendar-fill between the first and last payment date, then a 7-day
    // moving average over the filled series (ma7)
    var map = {{}};
    days.forEach(function (d) {{ map[d.date] = d.amount_cny; }});
    var dates = [], vals = [], ma = [], win = [];
    var t = new Date(days[0].date).getTime();
    var last = new Date(days[days.length - 1].date).getTime();
    for (; t <= last; t += 86400000) {{
      var ds = new Date(t).toISOString().slice(0, 10);
      var v = map[ds] || 0;
      dates.push(ds); vals.push(v); win.push(v);
      if (win.length > 7) win.shift();
      ma.push(Math.round(win.reduce(function (a, b) {{ return a + b; }}, 0) / win.length));
    }}
    return {{
      tooltip: {{ trigger: 'axis' }},
      legend: {{ bottom: 0 }},
      grid: {{ left: 60, right: 20, bottom: 40 }},
      xAxis: {{ type: 'category', data: dates }},
      yAxis: {{ type: 'value', name: 'CNY' }},
      series: [
        {{ name: 'Paid that day', type: 'bar', data: vals,
           itemStyle: {{ color: '#b2bec3' }} }},
        {{ name: '7-day average', type: 'line', data: ma, smooth: true,
           showSymbol: false, lineStyle: {{ width: 2, color: '#0984e3' }} }}
      ]
    }};
  }}

  function route() {{
    var m = location.hash.match(/^#\\/stage\\/([A-Za-z0-9_-]+)$/);
    if (m && stagesById[m[1]]) {{
      fillStage(stagesById[m[1]]);
      document.querySelectorAll('.tab-panel').forEach(function (p) {{
        p.classList.toggle('active', p.id === 'stage-view');
      }});
      nav.querySelectorAll('button').forEach(function (b) {{ b.classList.remove('active'); }});
      window.scrollTo(0, 0);
      return;
    }}
    // '#/overview', the empty hash (entry URL after Back from a stage page)
    // and any stray hash all land on the overview tab — the server-rendered
    // initial state
    showTab('overview');
  }}
  window.addEventListener('hashchange', route);
  route();

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
        # supplier translation dict lives next to reports/ in the data home
        # (gitignored, see config/paths.yaml); optional — raw zh when absent
        dict_csv = args.reports.parent / "data" / "dict" / "translation.csv"
        has_dict = dict_csv.exists()
        if has_dict:
            n_entries = len(load_supplier_translations(dict_csv))
            print(f"supplier dictionary: {n_entries} entries ({dict_csv})")
        else:
            print(
                f"supplier dictionary: missing ({dict_csv}) — raw zh supplier labels"
            )
        data = build_dashboard_data(
            args.reports,
            supplier_translations_path=dict_csv if has_dict else None,
        )
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
