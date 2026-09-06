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
    load_supplier_translations,
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


# Fake zh supplier names for the sankey Top-N tests — 12 distinct, synthetic.
SANKEY_SUPPLIERS = [
    "假供应商甲", "假供应商乙", "假供应商丙", "假供应商丁",
    "假供应商戊", "假供应商己", "假供应商庚", "假供应商辛",
    "假供应商壬", "假供应商癸", "假供应商子", "假供应商丑",
]


@pytest.fixture()
def sankey_dir(tmp_path) -> Path:
    """12 suppliers with descending amounts: top-10 individual + tail of 2.

    Totals: tooling_molds 7800 + painting_printing 300 = grand total 8100;
    top-10 sum 7500, Others tail 300 (200 + 100).
    """
    d = tmp_path / "reports"
    amounts = [1300 - 100 * (i + 1) for i in range(12)]  # 1200, 1100, …, 100
    rows = [
        f"{zh},tooling_molds,2026-01,{amt:.2f}"
        for zh, amt in zip(SANKEY_SUPPLIERS, amounts, strict=True)
    ]
    rows.append("假供应商甲,painting_printing,2026-02,300.00")
    write(d / "audit" / "by_supplier_stage.csv",
          "supplier,stage,month,amount_cny", rows)
    write(d / "audit" / "stage_summary.csv",
          "stage,n_lines,amount_cny,share_pct",
          ["tooling_molds,24,7800.00,96.3", "painting_printing,1,300.00,3.7"])
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


def test_load_supplier_translations_filters_supplier_hint(tmp_path):
    path = write(
        tmp_path / "translation.csv",
        "zh,en,column_hint,n_occurrences,status",
        [
            "假供应商甲,Fake Supplier A,supplier,2,translated",
            "假动词,Fake Verb,item,9,translated",
            "假供应商乙,,supplier,3,untranslated",
        ],
    )
    assert load_supplier_translations(path) == {"假供应商甲": "Fake Supplier A"}


def test_load_supplier_translations_missing_file(tmp_path):
    assert load_supplier_translations(tmp_path / "nope" / "translation.csv") == {}


# --- aggregate builder --------------------------------------------------


def test_build_dashboard_data_tiles(reports_dir):
    data = build_dashboard_data(reports_dir)
    tiles = data["overview"]["tiles"]
    assert tiles["total_spend_cny"] == 20000.0
    assert tiles["total_lines"] == 10  # sum of stage_summary lines
    assert tiles["num_styles"] == 2
    assert tiles["top_stage"] == "tooling_molds"


# --- sankey: Top-N + Others, EN labels, flow invariant -------------------


def test_sankey_all_suppliers_individual_below_top_n(reports_dir):
    data = build_dashboard_data(reports_dir)
    names = [n["name"] for n in data["overview"]["sankey"]["nodes"]]
    assert names == [
        "Spend",
        "tooling_molds",
        "painting_printing",
        "logistics_freight",
        "SupA",
        "SupB",
        "SupC",
    ]
    assert not any(n.startswith("Others") for n in names)
    links = data["overview"]["sankey"]["links"]
    assert {"source": "tooling_molds", "target": "SupA", "value": 10000.0} in links
    assert sum(ln["value"] for ln in links if ln["source"] == "Spend") == 20000.0


def test_sankey_top10_individual_and_others_node(sankey_dir):
    data = build_dashboard_data(sankey_dir)
    names = [n["name"] for n in data["overview"]["sankey"]["nodes"]]
    assert names == (
        ["Spend", "tooling_molds", "painting_printing"]
        + SANKEY_SUPPLIERS[:10]
        + ["Others (2 suppliers)"]
    )


def test_sankey_others_bucket_aggregates_tail_links(sankey_dir):
    links = build_dashboard_data(sankey_dir)["overview"]["sankey"]["links"]
    others = [ln for ln in links if ln["target"].startswith("Others")]
    assert others == [
        {"source": "tooling_molds", "target": "Others (2 suppliers)", "value": 300.0}
    ]
    # one aggregated link per stage only — the two tail suppliers are gone
    assert len([ln for ln in links if ln["target"] in SANKEY_SUPPLIERS[10:]]) == 0
    values = [ln["value"] for ln in links]
    assert values == sorted(values, reverse=True)  # sorted by value, desc


def test_sankey_flow_conservation(sankey_dir, reports_dir):
    """Σ sankey links == grand total on both layers (spend→stage, stage→supplier)."""
    for data in (build_dashboard_data(sankey_dir), build_dashboard_data(reports_dir)):
        links = data["overview"]["sankey"]["links"]
        spend_links = sum(ln["value"] for ln in links if ln["source"] == "Spend")
        leaf_links = sum(ln["value"] for ln in links if ln["source"] != "Spend")
        total = data["overview"]["tiles"]["total_spend_cny"]
        assert spend_links == total
        assert leaf_links == total


def test_sankey_english_labels_with_zh_original(sankey_dir, tmp_path):
    dict_path = write(
        tmp_path / "translation.csv",
        "zh,en,column_hint,n_occurrences,status",
        [
            "假供应商甲,Fake Supplier A,supplier,2,translated",
            "假供应商乙,Fake Supplier B,item,1,translated",  # non-supplier hint: ignored
        ],
    )
    data = build_dashboard_data(sankey_dir, supplier_translations_path=dict_path)
    names = [n["name"] for n in data["overview"]["sankey"]["nodes"]]
    assert "Fake Supplier A (假供应商甲)" in names  # EN + zh original
    assert "假供应商丙" in names  # untranslated supplier keeps raw zh
    assert not any("Fake Supplier B" in n for n in names)  # item-hint rows never map
    links = data["overview"]["sankey"]["links"]
    assert {
        "source": "tooling_molds",
        "target": "Fake Supplier A (假供应商甲)",
        "value": 1200.0,
    } in links
    # without a dictionary every supplier keeps its raw zh name
    plain = build_dashboard_data(sankey_dir)["overview"]["sankey"]["nodes"]
    assert "假供应商甲" in [n["name"] for n in plain]
    # fallback table rows use the same EN + zh composite label
    sup_rows = data["overview"]["sankey"]["top_suppliers"]
    assert sup_rows[0]["supplier"] == "Fake Supplier A (假供应商甲)"


def test_sankey_top_suppliers_fallback_rows(sankey_dir):
    rows = build_dashboard_data(sankey_dir)["overview"]["sankey"]["top_suppliers"]
    assert len(rows) == 11  # top-10 + Others
    assert rows[0]["supplier"] == "假供应商甲"
    assert rows[0]["stages"] == ["tooling_molds", "painting_printing"]
    assert rows[0]["total_cny"] == 1500.0
    assert rows[0]["share_pct"] == 18.5
    others = rows[-1]
    assert others["supplier"] == "Others (2 suppliers)"
    assert others["stages"] == ["tooling_molds"]
    assert others["total_cny"] == 300.0
    assert others["share_pct"] == 3.7
    assert sum(r["total_cny"] for r in rows) == 8100.0  # nothing lost in bucketing


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
