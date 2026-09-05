"""TDD tests for the REAL report formats (as produced by audit/benchmarks/
optimization/translation steps in the main checkout):

- audit CSVs: extra columns (n_lines), aggregated supplier CSV with
  months_active ";"-lists and blank supplier names, float style numbers.
- benchmarks/*.md, optimization/optimization.md, translation/glossary.md.

All fixtures are synthetic minis with the exact real headers/structure.
"""

import json
from pathlib import Path

from action_figures.dashboard_data import (
    build_dashboard_data,
    load_benchmarks_md,
    load_glossary_md,
    load_optimizations_md,
    load_suppliers,
    load_unclassified,
)

BENCH_MD = """# Benchmark: Tooling & Molds (tooling_molds · zh: 开模)

Stage: cutting the metal molds. All prices USD unless noted.

## 1. Normalized summary

- Small single-cavity molds **$1,000–5,000** ([Rex Plastics](https://rexplastics.com/molds))
- Steel/complex molds **$5,000–100,000** for 10,000+ units ([Formlabs](https://formlabs.com/im))
- Same source twice: ([Rex Plastics](https://rexplastics.com/molds))
- No-range bullet that must be skipped.

## 2. Lead times

Aluminum tools T1 in **7–14 days** vs steel 20–45 ([rapidaplus](https://rapidaplus.com/al)).
"""

OPT_MD = """# Production Optimization Recommendations — action figures

Intro line. Baseline: H1 2026 spend = ¥255,002.

---

## 1. First sanity check: our stage shares vs the market

The rule of thumb says **painting + assembly = 60–70% of unit cost** ([newmiho](https://newmiho.com/guide)). We are nowhere near that:

| Stage | Our share (full audit) | H1-2026 ¥ | Market reference |
|---|---:|---:|---|
| tooling_molds | 19.0% | 48,280 | molds are a one-time block ([formlabs](https://formlabs.com/im)) |
| painting_printing | **7.8%** | 15,796 | $0.80–6.00/piece ([edntoy](https://edntoy.com/paint)) |

**Reading:** paint is not our lever.

The **deviations from the market norm are our candidates**:

1. **Tooling is a recurring cost for us** (19%) — factories treat molds as one-off NRE.
2. **Garment chain = 39.8% of all spend** (textile + hand sewing + materials).

---

## 2. Recommendations (ranked; details below)

| # | Recommendation | 6-mo saving est. (¥) | Prob. | Score = (¥×prob)/effort | Time saved | Effort |
|---|---|---:|---:|---:|---|---|
| 1 | RFQ the sewing/assembly chain | 8,900 | 0.7 | **3,100** | 2–4 wks/style | M |
| 2 | Buy textile trims at MOQ | 4,800 | 0.8 | **1,900** | 1–2 wks lead | M |

---

### 1) RFQ the sewing/assembly chain against market rates

**What to do (plain words):** get 2–3 competing quotes per job.

**Our baseline:** H1-2026 assembly = **¥59,180** (23% of the half-year).

**Market range:** finished garment **$1.70–2.35/pc (≈¥12–17)** ([alibaba](https://alibaba.com/x), acc. 2026-09-05).

**Savings math:** 15% × ¥59,180 = **≈¥8,900**. Range ¥5,900–11,800.

**Risks:** new shop quality ramp.
"""

GLOSSARY_MD = """# Figure Production Glossary (zh → en)

Intro line.

| zh | en | Simple explanation |
|---|---|---|
| 大货 | mass production | The full production run (not samples). |
| 开模 | mold making (tooling) | Paying a shop to cut a steel mold for a part. |
"""


def fixture_real_reports(d: Path) -> Path:
    """reports/ tree in the REAL formats (synthetic mini content)."""
    audit = d / "audit"
    audit.mkdir(parents=True)
    (audit / "stage_summary.csv").write_text(
        "stage,n_lines,amount_cny,share_pct\n"
        "tooling_molds,4,10000.00,50.0\n"
        "assembly_processing,3,6000.00,30.0\n"
        "painting_printing,3,4000.00,20.0\n",
        encoding="utf-8",
    )
    (audit / "by_month_stage.csv").write_text(
        "month,stage,n_lines,amount_cny\n"
        "2026-01,tooling_molds,2,6000.00\n"
        "2026-02,tooling_molds,2,4000.00\n"
        "2026-01,assembly_processing,3,6000.00\n"
        "2026-02,painting_printing,3,4000.00\n",
        encoding="utf-8",
    )
    (audit / "by_style_stage.csv").write_text(
        "style_no,stage,amount_cny\n"
        "AF-1001,tooling_molds,10000.00\n"
        "AF-1001,painting_printing,1000.00\n"
        "AF-1002,assembly_processing,6000.00\n"
        "AF-1002,painting_printing,3000.00\n",
        encoding="utf-8",
    )
    (audit / "by_style_timeline.csv").write_text(
        "style_no,stage,start_date,end_date,n_lines,amount_cny\n"
        "AF-1001,tooling_molds,2026-01-05,2026-02-20,4,10000.00\n"
        "AF-1001,painting_printing,2026-02-21,2026-03-10,3,1000.00\n"
        "AF-1002,assembly_processing,2026-01-10,2026-01-25,3,6000.00\n",
        encoding="utf-8",
    )
    (audit / "by_supplier_stage.csv").write_text(
        "supplier,stage,amount_cny,n_lines,months_active\n"
        "测试供应商,injection_molding,39526.00,23,2026-01;2026-03\n"
        ",tooling_molds,43630.00,13,2026-01;2026-02\n",
        encoding="utf-8",
    )
    (audit / "unclassified.csv").write_text(
        "line_id,month,date,style_no,item,purpose,supplier,amount\n"
        "abc,2026-02,2026-02-04,AF-1003,测试配件,示例用途,测试供应商,68.0\n"
        "def,2026-03,2026-03-14,,测试耗材,示例用途,测试工厂,15.0\n",
        encoding="utf-8",
    )
    bench = d / "benchmarks"
    bench.mkdir()
    (bench / "tooling_molds.md").write_text(BENCH_MD, encoding="utf-8")
    opt = d / "optimization"
    opt.mkdir()
    (opt / "optimization.md").write_text(OPT_MD, encoding="utf-8")
    tr = d / "translation"
    tr.mkdir()
    (tr / "glossary.md").write_text(GLOSSARY_MD, encoding="utf-8")
    return d


# --- real-format loaders ----------------------------------------------------


def test_suppliers_real_aggregated_format():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "by_supplier_stage.csv"
        p.write_text(
            "supplier,stage,amount_cny,n_lines,months_active\n"
            "测试供应商,injection_molding,39526.00,23,2026-01;2026-03\n"
            ",tooling_molds,43630.00,13,2026-01;2026-02\n",
            encoding="utf-8",
        )
        rows = load_suppliers(p)
    assert rows[0]["supplier"] == "(unknown)"  # blank name, biggest total
    assert rows[0]["amount_cny"] == 43630.0
    assert rows[0]["stage_mix"] == {"tooling_molds": 43630.0}
    assert rows[0]["months"] == ["2026-01", "2026-02"]
    assert rows[1]["supplier"] == "测试供应商"
    assert rows[1]["months"] == ["2026-01", "2026-03"]


def test_benchmarks_md_extracts_ranges_and_sources(tmp_path):
    stages = load_benchmarks_md(tmp_path)
    assert stages == []  # empty dir → no crash

    stages = load_benchmarks_md(Path(tmp_path) / "empty")
    # dir does not exist → empty
    assert stages == []

    bdir = tmp_path / "benchmarks"
    bdir.mkdir()
    (bdir / "tooling_molds.md").write_text(BENCH_MD, encoding="utf-8")
    stages = load_benchmarks_md(bdir)
    assert len(stages) == 1
    s = stages[0]
    assert s["stage"] == "tooling_molds"
    assert "Tooling & Molds" in s["title"]
    assert s["intro"].startswith("Stage: cutting")
    assert len(s["highlights"]) == 3  # bullets with a bold range only
    assert "$1,000–5,000" in s["highlights"][0]
    assert "**" not in s["highlights"][0]
    urls = [src["url"] for src in s["sources"]]
    assert urls == [  # deduped, first-seen order
        "https://rexplastics.com/molds",
        "https://formlabs.com/im",
        "https://rapidaplus.com/al",
    ]
    assert all(src["title"] for src in s["sources"])


def test_optimizations_md_cards_comparison_insights(tmp_path):
    p = tmp_path / "optimization.md"
    p.write_text(OPT_MD, encoding="utf-8")
    opt = load_optimizations_md(p)
    cards = opt["cards"]
    assert [c["id"] for c in cards] == ["1", "2"]
    c = cards[0]
    assert c["title"] == "RFQ the sewing/assembly chain"
    assert c["saving_cny"] == 8900.0
    assert c["prob"] == 0.7
    assert c["score"] == 3100.0
    assert c["time_saved"] == "2–4 wks/style"
    assert c["effort"] == "M"
    assert "¥59,180" in c["baseline"]
    assert "¥12–17" in c["market_range"]
    assert "8,900" in c["math"]

    comp = opt["market_comparison"]
    assert comp[0]["stage"] == "tooling_molds"
    assert comp[0]["our_share_pct"] == 19.0
    assert comp[0]["h1_2026_cny"] == 48280.0
    assert "formlabs" in comp[0]["market_ref"]

    assert any("Tooling is a recurring cost" in i for i in opt["insights"])
    assert any("Garment chain" in i for i in opt["insights"])


def test_glossary_md_table(tmp_path):
    p = tmp_path / "glossary.md"
    p.write_text(GLOSSARY_MD, encoding="utf-8")
    rows = load_glossary_md(p)
    assert rows[0] == {
        "zh": "大货",
        "en": "mass production",
        "explanation": "The full production run (not samples).",
    }
    assert len(rows) == 2


def test_unclassified_count(tmp_path):
    p = tmp_path / "unclassified.csv"
    p.write_text(
        "line_id,month,date,style_no,item,purpose,supplier,amount\n"
        "a,2026-02,2026-02-04,AF-1003,测试配件,示例用途,测试供应商,68.0\n"
        "b,2026-03,2026-03-14,,测试耗材,示例用途,测试工厂,15.0\n",
        encoding="utf-8",
    )
    got = load_unclassified(p)
    assert got == {"n_lines": 2, "amount_cny": 83.0}
    assert load_unclassified(tmp_path / "missing.csv") == {
        "n_lines": 0,
        "amount_cny": 0.0,
    }


# --- aggregate over the full real-format tree --------------------------------


def test_build_dashboard_data_real_formats(tmp_path):
    d = fixture_real_reports(tmp_path / "reports")
    data = build_dashboard_data(d)

    # style numbers normalized: float-string forms collapse to plain labels
    styles = {g["style_no"] for g in data["timelines"]["gantt"]}
    assert styles == {"AF-1001", "AF-1002"}

    # benchmarks came from md, not csv
    assert data["benchmarks"]["rows"] == []
    assert data["benchmarks"]["stages"][0]["stage"] == "tooling_molds"

    # optimizations came from md with market comparison + insights
    assert data["optimizations"]["cards"][0]["saving_cny"] == 8900.0
    assert data["optimizations"]["market_comparison"]
    assert data["optimizations"]["insights"]

    # glossary came from md
    assert data["glossary"]["rows"][0]["zh"] == "大货"

    # unclassified surfaced on overview
    assert data["overview"]["unclassified"]["n_lines"] == 2

    # executive summary: plain-English bullets + numbers
    ex = data["overview"]["executive"]
    assert ex["total_spend_cny"] == 20000.0
    assert ex["months_range"] == ["2026-01", "2026-02"]
    assert ex["top3_stages"][0]["stage"] == "tooling_molds"
    assert ex["top3_savings_cny"] == 8900.0 + 4800.0
    assert ex["bullets"], "executive summary must have bullets"
    assert any("tooling" in b.lower() for b in ex["bullets"])
    assert any("8,900" in b or "13,700" in b for b in ex["bullets"])

    # gantt capped for readability
    assert len(data["timelines"]["gantt"]) <= 25
    assert isinstance(data["timelines"]["gantt_truncated"], bool)

    assert json.loads(json.dumps(data)) == data  # JSON-safe
