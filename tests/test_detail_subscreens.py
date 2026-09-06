"""EI-4 (GH#29): Optimization & Benchmark detail sub-screens.

Payload sections ``optimization_pages`` (keyed by rec id) and
``benchmark_pages`` (keyed by stage_id), the extended optimization.md
parsing (what to do / time / effort / risks / evidence links with access
dates), the clickable cards and the client-side sub-screens, and the
no-JS full-text fallback tables. Fixtures are synthetic minis with the
exact real report structure.
"""

import json
import sys
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
sys.path.insert(0, str(DASHBOARD_DIR))

import build_dashboard as bd  # noqa: E402
from test_dashboard_data_real_formats import fixture_real_reports  # noqa: E402

from action_figures.dashboard_data import (  # noqa: E402
    build_benchmark_pages,
    build_dashboard_data,
    build_optimization_pages,
    load_optimizations_md,
)

# One recommendation section carrying EVERY detail label (real structure;
# dates follow links as "acc. YYYY-MM-DD" / "accessed YYYY-MM-DD").
REC_SECTION = """
**What to do (plain words):** get 2–3 competing quotes per job.

**Our baseline:** H1-2026 assembly = **¥59,180** (23% of the half-year).

**Market range:** finished garment **$1.70–2.35/pc (≈¥12–17)** ([alibaba](https://alibaba.com/x), acc. 2026-09-05); sewing labor $1–2 ([pluckyreach](https://pluckyreach.com/y), acc. 2026-09-05).

**Savings math:** 15% × ¥59,180 = **≈¥8,900**. Range ¥5,900–11,800.

**Time:** compresses garment cycles by 2–4 weeks.

**Effort:** M — RFQ 5 recurring job types to 2 new shops.

**Risks:** new shop quality ramp; losing volume discounts.
"""

OPT_MD_FULL = """# Production Optimization Recommendations — action figures

Intro. Baseline: H1 2026 spend = ¥255,002.

## 2. Recommendations (ranked; details below)

| # | Recommendation | 6-mo saving est. (¥) | Prob. | Score = (¥×prob)/effort | Time saved | Effort |
|---|---|---:|---:|---:|---|---|
| 1 | RFQ the sewing/assembly chain | 8,900 | 0.7 | **3,100** | 2–4 wks/style | M |
| 2 | Buy textile trims at MOQ | 4,800 | 0.8 | **1,900** | 1–2 wks lead | M |

### 1) RFQ the sewing/assembly chain against market rates
""" + REC_SECTION + """
### 2) Buy textile trims at MOQ and pool purchases across styles

**What to do:** combine same-material needs into one MOQ order.

**Our baseline:** 146 textile lines, ¥43,220 H1-2026.

**Market range:** woven labels $0.025–0.08/pc ([made-in-china](https://mic.com/labels), accessed 2026-09-05).

**Savings math:** ¥43,220 × 0.40 × 0.25 ≈ **¥4,800**.

**Risks:** cash tied up in inventory.
"""

BENCH_MD_FULL = """# Benchmark: Tooling & Molds (stage `tooling_molds`, zh: 开模)

All URLs opened and confirmed on-page; accessed / re-verified 2026-09-05.

## 1. Normalized summary

- Simple steel mold **¥8,000–30,000** ([Zhihu](https://zhihu.com/p/1))
- Aluminum rapid tooling **¥1,000–10,000** ([Asiamold](https://asiamold.com/2))
"""


def _mk_bench(d: Path, stems: list[str]) -> None:
    bdir = d / "benchmarks"
    bdir.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        text = BENCH_MD_FULL.replace("tooling_molds", stem)
        (bdir / f"{stem}.md").write_text(text, encoding="utf-8")


TEN_STAGES = [
    "raw_materials", "tooling_molds", "injection_molding",
    "painting_printing", "textile_accessories", "assembly_processing",
    "packaging", "qc_testing", "logistics_freight", "design_prototyping",
]


# --- optimization.md detail parsing -----------------------------------------


def test_optimizations_md_extracts_detail_fields(tmp_path):
    p = tmp_path / "optimization.md"
    p.write_text(OPT_MD_FULL, encoding="utf-8")
    cards = load_optimizations_md(p)["cards"]
    c = cards[0]
    assert c["what_to_do"].startswith("get 2–3 competing quotes")
    assert c["time_note"].startswith("compresses garment cycles")
    assert c["effort_detail"].startswith("M — RFQ 5 recurring job types")
    assert c["risks"].startswith("new shop quality ramp")
    # section Effort detail does not clobber the table's S/M/L letter
    assert c["effort"] == "M"


def test_optimizations_md_extracts_evidence_with_access_dates(tmp_path):
    p = tmp_path / "optimization.md"
    p.write_text(OPT_MD_FULL, encoding="utf-8")
    ev = load_optimizations_md(p)["cards"][0]["evidence"]
    assert ev == [
        {"title": "alibaba", "url": "https://alibaba.com/x",
         "accessed_on": "2026-09-05"},
        {"title": "pluckyreach", "url": "https://pluckyreach.com/y",
         "accessed_on": "2026-09-05"},
    ]
    # "accessed" spelling works too
    ev2 = load_optimizations_md(p)["cards"][1]["evidence"]
    assert ev2[0]["title"] == "made-in-china"
    assert ev2[0]["accessed_on"] == "2026-09-05"


# --- review on PR 35: parser edge cases --------------------------------------


SAME_LINE_AND_TAIL_MD = """# Production Optimization Recommendations

## 2. Recommendations (ranked; details below)

| # | Recommendation | 6-mo saving est. (¥) | Prob. | Score | Time saved | Effort |
|---|---|---:|---:|---:|---|---|
| 7 | Consolidate courier shipments | 1,100 | 0.9 | **490** | days | S |

### 7) Consolidate courier shipments

**What to do:** batch sample sends into fixed courier days.

**Our baseline:** 278 freight lines with avg **¥25/shipment** — inside the band.

**Effort:** S. **Risks:** consolidated parcels delay urgent samples — keep an express lane.

## 3. RFQ list (known data gaps)

Prices not publicly verifiable; see the [RFQ guide](https://rfq.example.com/guide) before quoting.
"""


def test_same_line_labels_do_not_bleed(tmp_path):
    """Rec 7 writes 'Effort:' and 'Risks:' on one line — the Effort value
    must stop at the Risks label, not swallow the risks text."""
    p = tmp_path / "optimization.md"
    p.write_text(SAME_LINE_AND_TAIL_MD, encoding="utf-8")
    c = load_optimizations_md(p)["cards"][0]
    assert c["effort_detail"] == "S."
    assert c["risks"].startswith("consolidated parcels delay urgent samples")
    assert "Risks:" not in c["effort_detail"]
    # bold values inside a label paragraph are not treated as labels
    assert "¥25/shipment" in c["baseline"]


def test_section_ends_at_next_h2_no_evidence_bleed(tmp_path):
    """The last '### N)' section runs to EOF — links in the following '## '
    sections (RFQ list, assumptions) must not land in its evidence."""
    p = tmp_path / "optimization.md"
    p.write_text(SAME_LINE_AND_TAIL_MD, encoding="utf-8")
    c = load_optimizations_md(p)["cards"][0]
    assert c["evidence"] == []
    assert "rfq.example.com" not in str(c)


def test_client_escT_also_escapes_quotes():
    """escT output lands in double-quoted href attributes — it must escape
    the double-quote char like the server-side _esc does."""
    html = bd.render_html(bd.build_mock_data(), "MOCK (test)")
    js = html.split("function escT(", 1)[1].split("function kv(", 1)[0]
    assert "replace(/\"/g, '&quot;')" in js


# --- page builders -----------------------------------------------------------


def test_build_optimization_pages_keyed_by_id():
    p = {
        "1": {"id": "1", "title": "RFQ", "saving_cny": 8900.0},
        "2": {"id": "2", "title": "MOQ", "saving_cny": 4800.0},
    }
    # accepts both a list of cards and an already-keyed dict
    assert build_optimization_pages(list(p.values())) == p
    assert build_optimization_pages(p) == p


def test_build_benchmark_pages_join_market_comparison():
    stages = [
        {"stage": "tooling_molds", "title": "Tooling & Molds",
         "intro": "i", "highlights": ["h"], "sources": [{"title": "s",
         "url": "https://x"}], "accessed_on": "2026-09-05"},
    ]
    comp = [{"stage": "tooling_molds", "our_share_pct": 19.0,
             "h1_2026_cny": 48280.0, "market_ref": "ref"}]
    pages = build_benchmark_pages(stages, comp)
    page = pages["tooling_molds"]
    assert page["accessed_on"] == "2026-09-05"
    assert page["our"]["share_pct"] == 19.0
    assert page["our"]["h1_2026_cny"] == 48280.0
    # a stage absent from the comparison still gets a page, our = None
    stages2 = stages + [{"stage": "packaging", "title": "Packaging",
                         "intro": "", "highlights": [], "sources": [],
                         "accessed_on": ""}]
    pages2 = build_benchmark_pages(stages2, comp)
    assert set(pages2) == {"tooling_molds", "packaging"}
    assert pages2["packaging"]["our"] is None


# --- aggregate: 7 + 10 sub-screens over a real-format tree -------------------


def test_build_dashboard_data_has_seven_and_ten_pages(tmp_path):
    d = tmp_path / "reports"
    fixture_real_reports(d)
    (d / "optimization" / "optimization.md").write_text(
        OPT_MD_FULL, encoding="utf-8"
    )
    _mk_bench(d, TEN_STAGES)
    data = build_dashboard_data(d)

    opt_pages = data["optimization_pages"]
    assert sorted(opt_pages) == ["1", "2"]
    assert opt_pages["1"]["risks"].startswith("new shop quality ramp")
    assert opt_pages["1"]["evidence"][0]["accessed_on"] == "2026-09-05"

    bench_pages = data["benchmark_pages"]
    assert len(bench_pages) == 10
    page = bench_pages["tooling_molds"]
    assert page["accessed_on"] == "2026-09-05"
    assert page["sources"] and page["sources"][0]["url"].startswith("https://")
    assert json.loads(json.dumps(data)) == data  # JSON-safe


def test_mock_data_also_has_page_sections():
    data = bd.build_mock_data()
    assert set(data["optimization_pages"]) == {
        c["id"] for c in data["optimizations"]["cards"]
    }
    assert set(data["benchmark_pages"]) == {
        s["stage"] for s in data["benchmarks"]["stages"]
    }


# --- HTML: clickable cards, sub-screens, router, no-JS fallbacks -------------

def _real_html(tmp_path):
    d = tmp_path / "reports"
    fixture_real_reports(d)
    (d / "optimization" / "optimization.md").write_text(
        OPT_MD_FULL, encoding="utf-8"
    )
    _mk_bench(d, TEN_STAGES)
    return bd.render_html(build_dashboard_data(d), "reports/ (test)")


def test_html_links_cards_to_subscreens(tmp_path):
    html = _real_html(tmp_path)
    assert 'href="#/optimization/1"' in html
    assert 'href="#/optimization/2"' in html
    assert 'href="#/bench/tooling_molds"' in html


def test_html_has_detail_subscreen_sections():
    html = bd.render_html(bd.build_mock_data(), "MOCK (test)")
    for sid in ("opt-view", "bench-view"):
        assert f'<section id="{sid}"' in html
        view = html.split(f'id="{sid}"', 1)[1].split("</section>", 1)[0]
        assert "← Back" in view
        assert 'id="' + sid.replace("-view", "-detail") + '"' in view


def test_html_router_knows_detail_routes(tmp_path):
    html = _real_html(tmp_path)
    router = html.split("function route()", 1)[1].split(
        "window.addEventListener('hashchange'", 1
    )[0]
    assert "#\\/optimization\\/" in router
    assert "#\\/bench\\/" in router
    assert "optimization_pages" in html  # payload section is consumed
    assert "benchmark_pages" in html


def test_html_nojs_fallback_full_detail_tables(tmp_path):
    """No-JS fallback: the optimization table carries the full text of each
    recommendation (what to do, math, risks), benchmark table carries
    ranges + sources with access dates."""
    html = _real_html(tmp_path)
    opt_table = html.split('id="opt-fallback"', 1)[1]
    opt_table = opt_table.split("</table>", 1)[0]
    assert "What to do" in opt_table and "Risks" in opt_table
    assert "get 2–3 competing quotes" in opt_table
    assert "new shop quality ramp" in opt_table
    assert "15% × ¥59,180" in opt_table

    bench_table = html.split('id="bench-fallback"', 1)[1]
    bench_table = bench_table.split("</table>", 1)[0]
    assert "2026-09-05" in bench_table
    assert 'href="https://zhihu.com/p/1"' in bench_table
    assert "¥8,000–30,000" in bench_table
