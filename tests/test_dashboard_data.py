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
    load_stages_meta,
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
    write(
        d / "audit" / "stages.csv",
        "stage_id,order,label_en,description_en,zh_keys",
        [
            "design_prototyping,1,Design & Prototyping,Artists draw and sculpt every part digitally,画图;打样;3D",
            "tooling_molds,2,Tooling & Molds,Steel or resin molds are made before mass production,开模;模具;模费",
            "painting_printing,5,Painting & Printing,Spray and hand painting plus printing and plating,喷油;上色;丝印",
            "logistics_freight,10,Logistics & Freight,Courier and shipping fees for samples and materials,运费;快递",
            "admin_other,11,Admin & Other,Office overhead not part of physically making the figures,出差;油费",
            "unclassified,12,Unclassified,Lines the taxonomy could not classify,",
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


# --- UX pass 2: Unattributed supplier, gantt empty styles, truncation ----


@pytest.fixture()
def unattr_dir(tmp_path) -> Path:
    """Blank-supplier rows outweigh every named supplier — pinned last anyway."""
    d = tmp_path / "reports"
    write(
        d / "audit" / "stage_summary.csv",
        "stage,n_lines,amount_cny,share_pct",
        ["tooling_molds,3,5000.00,62.5", "painting_printing,3,3000.00,37.5"],
    )
    write(
        d / "audit" / "by_supplier_stage.csv",
        "supplier,stage,month,amount_cny",
        [
            "SupA,tooling_molds,2026-01,1200.00",
            "SupB,painting_printing,2026-01,800.00",
            ",tooling_molds,2026-02,2500.00",
            ",painting_printing,2026-02,1500.00",
        ],
    )
    return d


def test_suppliers_unattributed_renamed_and_pinned_last(unattr_dir):
    suppliers = load_suppliers(unattr_dir / "audit" / "by_supplier_stage.csv")
    assert [s["supplier"] for s in suppliers] == [
        "SupA",
        "SupB",
        "Unattributed",
    ]
    assert suppliers[-1]["amount_cny"] == 4000.0  # biggest total, still last
    assert suppliers[-1]["stage_mix"] == {
        "tooling_molds": 2500.0,
        "painting_printing": 1500.0,
    }


def test_unattributed_stats_in_payload(unattr_dir):
    data = build_dashboard_data(unattr_dir)
    expected = {"n_lines": 2, "amount_cny": 4000.0, "share_pct": 50.0}
    assert data["suppliers"]["unattributed"] == expected
    assert data["overview"]["unattributed"] == expected


def test_unattributed_absent_without_blank_rows(reports_dir):
    data = build_dashboard_data(reports_dir)
    assert data["suppliers"]["unattributed"] is None
    assert data["overview"]["unattributed"] is None


def test_unattributed_share_pct_clamped_to_100(tmp_path):
    """Source-file drift (supplier CSV total > stage_summary total) must not
    render an impossible ">100% of spend" callout (review note on PR 12)."""
    d = tmp_path / "reports"
    write(
        d / "audit" / "stage_summary.csv",
        "stage,n_lines,amount_cny,share_pct",
        ["tooling_molds,2,1000.00,100.0"],
    )
    write(
        d / "audit" / "by_supplier_stage.csv",
        "supplier,stage,month,amount_cny",
        [
            "SupA,tooling_molds,2026-01,600.00",
            ",tooling_molds,2026-02,1300.00",
        ],
    )
    data = build_dashboard_data(d)
    ua = data["overview"]["unattributed"]
    assert ua["amount_cny"] == 1300.0  # honest numerator, clamped percentage
    assert ua["share_pct"] == 100.0


def test_sankey_fallback_share_pct_clamped_to_100(tmp_path):
    """The no-JS Top suppliers table uses the same drifted denominator as the
    callout — its shares must clamp identically or the page contradicts
    itself (review follow-up on PR 12)."""
    d = tmp_path / "reports"
    write(
        d / "audit" / "stage_summary.csv",
        "stage,n_lines,amount_cny,share_pct",
        ["tooling_molds,2,1000.00,100.0"],
    )
    write(
        d / "audit" / "by_supplier_stage.csv",
        "supplier,stage,month,amount_cny",
        [
            "SupA,tooling_molds,2026-01,600.00",
            ",tooling_molds,2026-02,1300.00",
        ],
    )
    rows = build_dashboard_data(d)["overview"]["sankey"]["top_suppliers"]
    assert rows[0]["supplier"] == "SupA"
    assert rows[0]["share_pct"] == 60.0  # honest when below 100
    assert rows[-1]["supplier"] == "Unattributed"
    assert rows[-1]["share_pct"] == 100.0  # raw 130% → clamped


@pytest.fixture()
def unattr_sankey_dir(tmp_path) -> Path:
    """12 named suppliers + a blank-supplier bucket bigger than all of them."""
    d = tmp_path / "reports"
    amounts = [1300 - 100 * (i + 1) for i in range(12)]  # 1200, 1100, …, 100
    rows = [
        f"{zh},tooling_molds,2026-01,{amt:.2f}"
        for zh, amt in zip(SANKEY_SUPPLIERS, amounts, strict=True)
    ]
    rows.append("假供应商甲,painting_printing,2026-02,300.00")
    rows.append(",tooling_molds,2026-01,9999.00")
    write(d / "audit" / "by_supplier_stage.csv",
          "supplier,stage,month,amount_cny", rows)
    write(d / "audit" / "stage_summary.csv",
          "stage,n_lines,amount_cny,share_pct",
          ["tooling_molds,25,17799.00,98.3", "painting_printing,1,300.00,1.7"])
    return d


def test_sankey_unattributed_own_node_pinned_last(unattr_sankey_dir):
    data = build_dashboard_data(unattr_sankey_dir)
    san = data["overview"]["sankey"]
    names = [n["name"] for n in san["nodes"]]
    assert names[-1] == "Unattributed"  # own node, last — never inside Others
    assert names[-2] == "Others (2 suppliers)"
    assert not any(n == "(unknown)" for n in names)
    # bucketing ignores the blank supplier: Others keeps only the named tail
    others = [ln for ln in san["links"] if ln["target"].startswith("Others")]
    assert others == [
        {"source": "tooling_molds", "target": "Others (2 suppliers)", "value": 300.0}
    ]
    # flow conservation with the unattributed node in play
    total = data["overview"]["tiles"]["total_spend_cny"]
    spend = sum(ln["value"] for ln in san["links"] if ln["source"] == "Spend")
    leaf = sum(ln["value"] for ln in san["links"] if ln["source"] != "Spend")
    assert spend == leaf == total
    rows = san["top_suppliers"]
    assert len(rows) == 12  # top-10 + Others + Unattributed
    assert rows[-1]["supplier"] == "Unattributed"
    assert rows[-1]["total_cny"] == 9999.0


@pytest.fixture()
def gantt_dir(tmp_path) -> Path:
    """Real-format timeline: an empty style_no row with the longest span and
    the biggest amount must not become a bar."""
    d = tmp_path / "reports"
    write(
        d / "audit" / "by_style_timeline.csv",
        "style_no,stage,start_date,end_date,n_lines,amount_cny",
        [
            ",tooling_molds,2026-01-01,2026-06-30,3,5000.00",
            "AF-1,tooling_molds,2026-03-01,2026-03-10,2,3000.00",
            "AF-2,assembly_processing,2026-02-01,2026-02-28,1,1200.00",
        ],
    )
    write(
        d / "audit" / "stage_summary.csv",
        "stage,n_lines,amount_cny,share_pct",
        ["tooling_molds,5,8000.00,87.0", "assembly_processing,1,1200.00,13.0"],
    )
    return d


def test_gantt_excludes_empty_style_and_reports_unlinked(gantt_dir):
    data = build_dashboard_data(gantt_dir)
    tl = data["timelines"]
    assert [g["style_no"] for g in tl["gantt"]] == ["AF-1", "AF-2"]  # spend desc
    assert tl["unlinked"] == {"n_lines": 3, "amount_cny": 5000.0}
    assert tl["gantt_total_styles"] == 2
    assert tl["gantt_truncated"] is False
    by_style = {g["style_no"]: g for g in tl["gantt"]}
    assert by_style["AF-1"]["total_days"] == 10  # attributed rows only
    assert by_style["AF-1"]["total_cny"] == 3000.0
    assert by_style["AF-2"]["total_days"] == 28
    assert by_style["AF-2"]["total_cny"] == 1200.0


def test_gantt_legacy_rows_default_lines_and_amount(tmp_path):
    """Legacy 4-column timeline: n_lines/amount_cny default to 1/0.0."""
    path = write(
        tmp_path / "by_style_timeline.csv",
        "style_no,stage,start_date,end_date",
        [
            ",tooling_molds,2026-01-01,2026-02-01",
            "AF-9,painting_printing,2026-01-05,2026-01-09",
        ],
    )
    rows = load_by_style_timeline(path)
    assert rows[0] == {
        "style_no": "",
        "stage": "tooling_molds",
        "start_date": "2026-01-01",
        "end_date": "2026-02-01",
        "duration_days": 32,
        "n_lines": 1,
        "amount_cny": 0.0,
    }


def test_gantt_truncation_reports_total_style_count(tmp_path):
    d = tmp_path / "reports"
    rows = [
        f"AF-{i:03d},tooling_molds,2026-01-01,2026-01-15,1,{30000 - 100 * i:.2f}"
        for i in range(1, 31)
    ]
    write(d / "audit" / "by_style_timeline.csv",
          "style_no,stage,start_date,end_date,n_lines,amount_cny", rows)
    tl = build_dashboard_data(d)["timelines"]
    assert len(tl["gantt"]) == 25
    assert tl["gantt_truncated"] is True
    assert tl["gantt_total_styles"] == 30
    assert tl["gantt"][0]["style_no"] == "AF-001"  # richest style first
    assert tl["unlinked"] == {"n_lines": 0, "amount_cny": 0.0}


# --- PE-2: stages.csv metadata + payload `stages` section (stage menu) ----


def test_load_stages_meta_sorted_by_production_order(reports_dir):
    rows = load_stages_meta(reports_dir / "audit" / "stages.csv")
    assert [r["stage_id"] for r in rows] == [
        "design_prototyping",
        "tooling_molds",
        "painting_printing",
        "logistics_freight",
        "admin_other",
        "unclassified",
    ]
    assert [r["order"] for r in rows] == [1, 2, 5, 10, 11, 12]
    assert rows[0]["label_en"] == "Design & Prototyping"
    assert rows[0]["description_en"].startswith("Artists draw")
    assert rows[0]["zh_keys"] == ["画图", "打样", "3D"]
    assert rows[-1]["zh_keys"] == []  # unclassified has no keywords


def test_load_stages_meta_missing_file(tmp_path):
    assert load_stages_meta(tmp_path / "nope" / "stages.csv") == []


def test_payload_stages_merges_stage_summary_amounts(reports_dir):
    """Menu sums must reconcile with stage_summary; a stage known to
    stages.csv but absent from the summary (qc_testing in the real data)
    sums to zero instead of disappearing."""
    by_id = {s["stage_id"]: s for s in build_dashboard_data(reports_dir)["stages"]}
    assert by_id["tooling_molds"]["amount_cny"] == 10000.0
    assert by_id["tooling_molds"]["share_pct"] == 50.0
    assert by_id["tooling_molds"]["n_lines"] == 4
    assert by_id["logistics_freight"]["amount_cny"] == 4000.0
    assert by_id["design_prototyping"]["amount_cny"] == 0.0
    assert by_id["design_prototyping"]["share_pct"] == 0.0
    assert by_id["design_prototyping"]["n_lines"] == 0


def test_payload_stages_mark_service_buckets(reports_dir):
    stages = build_dashboard_data(reports_dir)["stages"]
    assert [(s["stage_id"], s["service"]) for s in stages] == [
        ("design_prototyping", False),
        ("tooling_molds", False),
        ("painting_printing", False),
        ("logistics_freight", False),
        ("admin_other", True),
        ("unclassified", True),
    ]


def test_payload_stages_absent_without_stages_csv(tmp_path):
    d = tmp_path / "reports"
    write(d / "audit" / "stage_summary.csv",
          "stage,n_lines,amount_cny,share_pct",
          ["tooling_molds,1,100.00,100.0"])
    assert build_dashboard_data(d)["stages"] == []


def test_ideal_timeline_rows_unique_without_stages_csv(tmp_path):
    """No stages.csv → rows fall back to module order and must not duplicate
    a stage listed twice in the module (tooling steel + aluminum)."""
    d = tmp_path / "reports"
    write(d / "audit" / "stage_summary.csv",
          "stage,n_lines,amount_cny,share_pct",
          ["tooling_molds,1,100.00,100.0"])
    it = build_dashboard_data(d)["ideal_timeline"]
    row_ids = [r["stage_id"] for r in it["rows"]]
    assert len(row_ids) == len(set(row_ids)) == 9
    bars = it["bars"]
    assert len({b["row"] for b in bars}) == len(row_ids)


# --- ideal_timeline payload (PE-4: reference Gantt on the Overview) ------


def ideal_bars(reports_dir):
    return build_dashboard_data(reports_dir)["ideal_timeline"]["bars"]


def test_ideal_timeline_payload_shape(reports_dir):
    """Section ideal_timeline: fixed 0-26 week axis, sourced bars, rows."""
    it = build_dashboard_data(reports_dir)["ideal_timeline"]
    assert it["weeks_axis"] == [0, 26]
    assert len(it["total_weeks"]) == 2
    assert 0 < it["total_weeks"][0] <= it["total_weeks"][1] <= 26
    assert "payment dates" in it["disclaimer"]
    assert it["rows"] and [r["row"] for r in it["rows"]] == list(
        range(len(it["rows"]))
    )
    assert it["bars"]
    for b in it["bars"]:
        assert {"stage_id", "label", "variant", "row", "parallel",
                "start_week", "min_end_week", "max_start_week", "end_week",
                "min_weeks", "max_weeks", "source_file",
                "source_url"} <= set(b)
        assert 0 <= b["start_week"] < b["end_week"] <= 26
        assert b["start_week"] <= b["min_end_week"]
        assert b["max_start_week"] <= b["end_week"]
        assert b["source_url"].startswith("https://")
    assert max(b["end_week"] for b in it["bars"]) == it["total_weeks"][1]


def test_ideal_timeline_rows_follow_stages_csv_order(reports_dir):
    """Y rows: stages.csv process order first, module-only stages appended."""
    it = build_dashboard_data(reports_dir)["ideal_timeline"]
    by_id = {r["stage_id"]: r for r in it["rows"]}
    # fixture stages.csv knows design(1)/tooling(2)/painting(5)/logistics(10)
    assert (by_id["design_prototyping"]["row"]
            < by_id["tooling_molds"]["row"]
            < by_id["painting_printing"]["row"]
            < by_id["logistics_freight"]["row"])
    # labels come from stages.csv when the stage is known there
    assert by_id["tooling_molds"]["label"] == "Tooling & Molds"
    # unknown-to-stages.csv stages still get a readable label + a row
    assert by_id["injection_molding"]["label"] == "injection molding"


def test_ideal_timeline_first_bar_starts_at_week_zero(reports_dir):
    bars = ideal_bars(reports_dir)
    assert bars[0]["stage_id"] == "design_prototyping"
    assert bars[0]["start_week"] == 0
    assert not bars[0]["parallel"]


def test_ideal_timeline_tooling_variants_share_row_and_start(reports_dir):
    bars = ideal_bars(reports_dir)
    tooling = [b for b in bars if b["stage_id"] == "tooling_molds"]
    assert {b["variant"] for b in tooling} == {"steel", "aluminum"}
    assert len({(b["row"], b["start_week"]) for b in tooling}) == 1


def test_ideal_timeline_parallel_window_overlaps(reports_dir):
    """injection_molding and textile_accessories start in the same week and
    are flagged parallel; both start after design+tooling could finish."""
    bars = ideal_bars(reports_dir)
    by_id = {}
    for b in bars:
        by_id.setdefault(b["stage_id"], []).append(b)
    inj, tex = by_id["injection_molding"][0], by_id["textile_accessories"][0]
    assert inj["parallel"] and tex["parallel"]
    assert inj["start_week"] == tex["start_week"]
    # the window may open after the FASTEST tooling variant (aluminum)
    fastest_tooling = min(b["min_end_week"] for b in by_id["tooling_molds"])
    assert inj["start_week"] >= fastest_tooling
    # every later main-chain stage starts at/after the window's fastest end
    pack = by_id["packaging"][0]
    assert pack["start_week"] >= inj["min_end_week"]


def test_ideal_timeline_payload_is_json_safe(reports_dir):
    import json

    json.dumps(build_dashboard_data(reports_dir)["ideal_timeline"])
