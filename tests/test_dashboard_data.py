"""TDD tests for dashboard_data (synthetic mini CSVs, same schema as reports/)."""

import json
from pathlib import Path

import pytest

from action_figures.dashboard_data import (
    build_dashboard_data,
    load_benchmarks,
    load_by_month_stage,
    load_by_style_stage,
    load_by_style_timeline,
    load_glossary,
    load_optimizations,
    load_stage_summary,
    load_suppliers,
)


def write(path: Path, header: str, rows: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([header] + rows) + "\n", encoding="utf-8")
    return path


@pytest.fixture()
def reports_dir(tmp_path) -> Path:
    d = tmp_path / "reports"
    write(
        d / "audit" / "stage_summary.csv",
        "stage,n_lines,amount_cny,share_pct",
        [
            "tooling_molds,4,10000.00,50.0",
            "painting_printing,3,6000.00,30.0",
            "logistics_freight,3,4000.00,20.0",
        ],
    )
    write(
        d / "audit" / "by_month_stage.csv",
        "month,stage,amount_cny",
        [
            "2026-01,tooling_molds,6000.00",
            "2026-02,tooling_molds,4000.00",
            "2026-01,painting_printing,6000.00",
            "2026-02,logistics_freight,4000.00",
        ],
    )
    write(
        d / "audit" / "by_style_stage.csv",
        "style_no,stage,amount_cny",
        [
            "AF-1,tooling_molds,10000.00",
            "AF-1,painting_printing,6000.00",
            "AF-2,logistics_freight,4000.00",
        ],
    )
    write(
        d / "audit" / "by_style_timeline.csv",
        "style_no,stage,start_date,end_date",
        [
            "AF-1,tooling_molds,2026-01-05,2026-02-20",
            "AF-1,painting_printing,2026-02-21,2026-03-10",
            "AF-2,logistics_freight,2026-01-10,2026-01-25",
        ],
    )
    write(
        d / "audit" / "by_supplier_stage.csv",
        "supplier,stage,month,amount_cny",
        [
            "SupA,tooling_molds,2026-01,6000.00",
            "SupA,tooling_molds,2026-02,4000.00",
            "SupB,painting_printing,2026-01,6000.00",
            "SupC,logistics_freight,2026-02,4000.00",
        ],
    )
    write(
        d / "benchmarks" / "benchmarks.csv",
        "stage,metric,our_value,market_low,market_high,unit,source_title,source_url,accessed_on",
        [
            "tooling_molds,mold_cost,10000,5000,20000,CNY-benchmark,toyyie,https://example.com/t,2026-09-01",
            "painting_printing,share_of_price,30,60,70,pct,newmiho,https://example.com/p,2026-09-02",
        ],
    )
    write(
        d / "optimization" / "optimizations.csv",
        "id,title,stage,baseline_cny,saving_cny,proof",
        [
            "1,Rapid tooling,tooling_molds,10000,3000,https://example.com/proof1",
            "2,Spray masks,painting_printing,6000,2000,https://example.com/proof2",
        ],
    )
    write(
        d / "translation" / "glossary.csv",
        "zh,en,explanation",
        [
            "开模,Tooling / mold making,Metal mold creation for plastic parts",
            "喷油,Spray painting,Painting parts with spray guns",
        ],
    )
    return d


# --- individual loaders -------------------------------------------------


def test_stage_summary_sorted_desc(reports_dir):
    rows = load_stage_summary(reports_dir / "audit" / "stage_summary.csv")
    assert [r["stage"] for r in rows] == [
        "tooling_molds",
        "painting_printing",
        "logistics_freight",
    ]
    assert rows[0]["amount_cny"] == 10000.0
    assert rows[0]["share_pct"] == 50.0


def test_by_month_stage_matrix(reports_dir):
    rows = load_by_month_stage(reports_dir / "audit" / "by_month_stage.csv")
    cell = {(r["month"], r["stage"]): r["amount_cny"] for r in rows}
    assert cell[("2026-01", "tooling_molds")] == 6000.0
    assert cell[("2026-02", "logistics_freight")] == 4000.0


def test_by_style_stage(reports_dir):
    rows = load_by_style_stage(reports_dir / "audit" / "by_style_stage.csv")
    assert len(rows) == 3
    assert rows[0]["style_no"] == "AF-1"


def test_timeline_duration_days(reports_dir):
    rows = load_by_style_timeline(reports_dir / "audit" / "by_style_timeline.csv")
    by_key = {(r["style_no"], r["stage"]): r for r in rows}
    r = by_key[("AF-1", "tooling_molds")]
    assert r["start_date"] == "2026-01-05"
    assert r["duration_days"] == 47  # inclusive


def test_suppliers_aggregate_stage_mix_and_months(reports_dir):
    suppliers = load_suppliers(reports_dir / "audit" / "by_supplier_stage.csv")
    assert suppliers[0]["supplier"] == "SupA"  # highest total first
    assert suppliers[0]["amount_cny"] == 10000.0
    assert suppliers[0]["stage_mix"] == {"tooling_molds": 10000.0}
    assert suppliers[0]["months"] == ["2026-01", "2026-02"]
    mix = {s["supplier"]: s["stage_mix"] for s in suppliers}
    assert mix["SupB"] == {"painting_printing": 6000.0}


def test_suppliers_without_month_column(tmp_path):
    """Real by_supplier_stage.csv has no `month` column; months_active is a
    ";"-joined list of YYYY-MM months (PR 19 export format)."""
    path = write(
        tmp_path / "by_supplier_stage.csv",
        "supplier,stage,amount_cny,n_lines,months_active",
        [
            "SupA,tooling_molds,6000.00,4,2026-01;2026-02",
            "SupB,painting_printing,3000.00,3,2026-01",
        ],
    )
    suppliers = load_suppliers(path)
    assert suppliers[0]["supplier"] == "SupA"
    assert suppliers[0]["amount_cny"] == 6000.0
    assert suppliers[0]["months"] == ["2026-01", "2026-02"]


def test_benchmarks_keep_source_links(reports_dir):
    rows = load_benchmarks(reports_dir / "benchmarks" / "benchmarks.csv")
    assert rows[0]["source_url"] == "https://example.com/t"
    assert rows[0]["our_value"] == 10000.0
    assert rows[0]["market_high"] == 20000.0


def test_optimizations_sorted_by_saving(reports_dir):
    rows = load_optimizations(reports_dir / "optimization" / "optimizations.csv")
    assert [r["id"] for r in rows] == ["1", "2"]
    assert rows[0]["saving_cny"] == 3000.0


def test_glossary(reports_dir):
    rows = load_glossary(reports_dir / "translation" / "glossary.csv")
    assert rows[0]["zh"] == "开模"
    assert rows[0]["en"] == "Tooling / mold making"


# --- aggregate builder --------------------------------------------------


def test_build_dashboard_data_tiles_and_sankey(reports_dir):
    data = build_dashboard_data(reports_dir)
    tiles = data["overview"]["tiles"]
    assert tiles["total_spend_cny"] == 20000.0
    assert tiles["total_lines"] == 10  # sum of stage_summary lines
    assert tiles["num_styles"] == 2
    assert tiles["top_stage"] == "tooling_molds"

    nodes = [n["name"] for n in data["overview"]["sankey"]["nodes"]]
    links = data["overview"]["sankey"]["links"]
    assert "Spend" in nodes and "tooling_molds" in nodes and "SupA" in nodes
    spend_links = [ln for ln in links if ln["source"] == "Spend"]
    assert sum(ln["value"] for ln in spend_links) == 20000.0
    assert {"source": "tooling_molds", "target": "SupA", "value": 10000.0} in links


def test_build_dashboard_data_heatmap_and_gantt(reports_dir):
    data = build_dashboard_data(reports_dir)
    hm = data["cost_structure"]["heatmap"]
    assert hm["months"] == ["2026-01", "2026-02"]
    assert ("2026-01", "tooling_molds") in {(c[0], c[1]) for c in hm["cells"]}

    gantt = data["timelines"]["gantt"]
    assert gantt[0]["style_no"] == "AF-1"  # longest total duration first
    stages = {g["style_no"]: {s["stage"]: s for s in g["stages"]} for g in gantt}
    assert stages["AF-1"]["tooling_molds"]["duration_days"] == 47


def test_build_dashboard_data_top_suppliers_and_sections(reports_dir):
    data = build_dashboard_data(reports_dir)
    top = data["suppliers"]["top"]
    assert top[0]["supplier"] == "SupA"
    assert len(data["benchmarks"]["rows"]) == 2
    assert len(data["optimizations"]["cards"]) == 2
    assert len(data["glossary"]["rows"]) == 2


def test_build_dashboard_data_json_roundtrip(reports_dir):
    data = build_dashboard_data(reports_dir)
    assert json.loads(json.dumps(data)) == data  # plain JSON-safe types only
