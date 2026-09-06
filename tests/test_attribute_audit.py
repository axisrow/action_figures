"""Golden cases for the forensic attribution audit (GH#10).

Every frame below is synthetic: invented supplier names, amounts and
stages. No real ledger rows are reproduced here.
"""

import pandas as pd

from action_figures.attribute_audit import (
    build_proposals,
    month_distance,
    normalize_style,
    write_reports,
    zh_bigrams,
)


def _row(line_id, item, supplier="", amount=0.0, stage="raw_materials",
         style_no="", purpose="", remarks="", month="2025-03"):
    return {
        "line_id": line_id,
        "month": month,
        "style_no": style_no,
        "item": item,
        "purpose": purpose,
        "supplier": supplier,
        "remarks": remarks,
        "amount": amount,
        "stage": stage,
    }


def _supplier_proposals(df):
    prop, _ = build_proposals(df)
    return prop[prop["field"] == "supplier"].reset_index(drop=True)


# --- text helpers ---------------------------------------------------------

def test_zh_bigrams_ignores_non_zh_pairs():
    assert zh_bigrams("9062枪护目") == {"枪护", "护目"}
    assert zh_bigrams("木剑护手") == {"木剑", "剑护", "护手"}
    assert zh_bigrams("") == set()


def test_normalize_style_strips_ud_prefix_and_float_tail():
    assert normalize_style("UD9062") == {"9062"}
    assert normalize_style("9066/9068") == {"9066", "9068"}
    assert normalize_style(9062.0) == {"9062"}
    assert normalize_style("") == set()
    assert normalize_style(None) == set()


def test_month_distance_wraps_years():
    assert month_distance("2025-03", "2025-04") == 1
    assert month_distance("2025-12", "2026-01") == 1
    assert month_distance("2025-03", "") is None


# --- supplier recovery: substring ----------------------------------------

def test_substring_recovers_named_supplier():
    df = pd.DataFrame([
        _row("a1", "开模费", supplier="云杉模具", amount=500.0, stage="tooling_molds"),
        _row("a2", "开模费", supplier="云杉模具", amount=300.0, stage="tooling_molds"),
        _row("e1", "云杉模具合金模定金", amount=400.0, stage="tooling_molds"),
    ])
    sup = _supplier_proposals(df)
    assert len(sup) == 1
    row = sup.iloc[0]
    assert row["line_id"] == "e1"
    assert row["proposed"] == "云杉模具"
    assert row["confidence"] == "high"
    assert row["method"] == "substring"


def test_substring_prefers_longest_name():
    df = pd.DataFrame([
        _row("a1", "切割费", supplier="激光", amount=250.0, stage="assembly_processing"),
        _row("a2", "切割费", supplier="激光切割坊", amount=310.0, stage="assembly_processing"),
        _row("e1", "激光切割坊加工费", amount=100.0, stage="assembly_processing"),
    ])
    sup = _supplier_proposals(df)
    assert sup.iloc[0]["proposed"] == "激光切割坊"


# --- supplier recovery: twin (counterpart) row ---------------------------

def test_twin_counterpart_row():
    df = pd.DataFrame([
        _row("a1", "木剑护手", supplier="星工坊", amount=100.0, style_no="0077",
             month="2025-04", stage="design_prototyping"),
        _row("e1", "木剑护手打样", amount=100.0, style_no="UD0077",
             month="2025-03", stage="design_prototyping"),
    ])
    sup = _supplier_proposals(df)
    assert len(sup) == 1
    row = sup.iloc[0]
    assert row["proposed"] == "星工坊"
    assert row["method"] == "twin_row"
    assert row["confidence"] == "high"
    assert "a1" in row["evidence"]


def test_twin_without_exact_amount_stays_medium():
    """A text-only twin may be a sibling line of the same order, not the
    paired payment — high confidence requires the exact amount."""
    df = pd.DataFrame([
        _row("a1", "木剑护手打样", supplier="星工坊", amount=100.0, style_no="0077",
             month="2025-04", purpose="样办", remarks="外协",
             stage="design_prototyping"),
        _row("e1", "木剑护手打样", amount=250.0, style_no="UD0077",
             month="2025-04", purpose="样办", remarks="外协",
             stage="design_prototyping"),
    ])
    sup = _supplier_proposals(df)
    assert len(sup) == 1
    assert sup.iloc[0]["method"] == "twin_row"
    assert sup.iloc[0]["confidence"] == "medium"


def test_twin_ambiguity_is_rejected():
    df = pd.DataFrame([
        _row("a1", "木剑护手", supplier="星工坊", amount=100.0, style_no="0077",
             month="2025-04", stage="design_prototyping"),
        _row("a2", "木剑护手", supplier="月工坊", amount=100.0, style_no="0077",
             month="2025-04", stage="design_prototyping"),
        _row("e1", "木剑护手打样", amount=100.0, style_no="UD0077",
             month="2025-03", stage="design_prototyping"),
    ])
    assert _supplier_proposals(df).empty


def test_twin_ignores_petty_amounts():
    df = pd.DataFrame([
        _row("a1", "运费到付", supplier="雁鸣快递", amount=12.0, style_no="0051",
             month="2025-04"),
        _row("e1", "运费到付", amount=12.0, style_no="UD0051", month="2025-03"),
    ])
    assert _supplier_proposals(df).empty


def test_twin_skips_logistics_rows():
    df = pd.DataFrame([
        _row("a1", "大货配件运输", supplier="雁鸣快递", amount=150.0, style_no="0051",
             month="2025-04"),
        _row("e1", "大货配件运输", amount=150.0, style_no="UD0051", month="2025-03",
             stage="logistics_freight"),
    ])
    assert _supplier_proposals(df).empty


def test_twin_ignores_channel_suppliers():
    """外购/外发 are sourcing channels, not counterparty names — a twin
    match against a channel row must not propose the channel."""
    df = pd.DataFrame([
        _row("a1", "木剑护手", supplier="外购", amount=100.0, style_no="0077",
             month="2025-04", stage="design_prototyping"),
        _row("a2", "木剑护手", supplier="外发", amount=100.0, style_no="0077",
             month="2025-04", stage="design_prototyping"),
        _row("e1", "木剑护手打样", amount=100.0, style_no="UD0077",
             month="2025-03", stage="design_prototyping"),
    ])
    assert _supplier_proposals(df).empty


# --- supplier recovery: category dominance -------------------------------

def _design_pool():
    rows = [
        _row(f"a{i}", "画图费", supplier="外发" if i < 5 else "外购",
             amount=100.0 + i, stage="design_prototyping")
        for i in range(6)
    ]
    rows.append(_row("e1", "头盔画图尾款", amount=200.0, stage="design_prototyping"))
    return pd.DataFrame(rows)


def test_category_dominance_recovers_design_outsource():
    sup = _supplier_proposals(_design_pool())
    assert len(sup) == 1
    row = sup.iloc[0]
    assert row["proposed"] == "外发"
    assert row["method"] == "category_dominance"
    assert row["confidence"] == "medium"


def test_category_dominance_below_threshold_is_rejected():
    rows = [
        _row(f"a{i}", "画图费", supplier="外发" if i < 3 else "外购",
             amount=100.0 + i, stage="design_prototyping")
        for i in range(5)
    ]
    rows.append(_row("e1", "头盔画图尾款", amount=200.0, stage="design_prototyping"))
    assert _supplier_proposals(pd.DataFrame(rows)).empty


# --- resolver ------------------------------------------------------------

def test_substring_beats_lower_confidence_methods():
    rows = [
        _row(f"a{i}", "画图费", supplier="外发" if i < 5 else "外购",
             amount=100.0 + i, stage="design_prototyping")
        for i in range(6)
    ]
    rows.append(_row("a6", "模具费", supplier="云杉模具", amount=999.0,
                     stage="tooling_molds"))
    rows.append(_row("e1", "云杉模具画图费", amount=100.0,
                     stage="design_prototyping"))
    sup = _supplier_proposals(pd.DataFrame(rows))
    assert sup.iloc[0]["method"] == "substring"
    assert sup.iloc[0]["proposed"] == "云杉模具"
    assert sup.iloc[0]["confidence"] == "high"


# --- stage recovery ------------------------------------------------------

def test_stage_from_supplier_statistics():
    rows = [
        _row(f"a{i}", "买线", supplier="缝衣铺", amount=10.0,
             stage="textile_accessories")
        for i in range(4)
    ]
    rows.append(_row("a4", "买纽扣", supplier="缝衣铺", amount=20.0,
                     stage="raw_materials"))
    rows.append(_row("e1", "7号衣车针", supplier="缝衣铺", amount=15.0,
                     stage="unclassified"))
    prop, _ = build_proposals(pd.DataFrame(rows))
    st = prop[prop["field"] == "stage"].reset_index(drop=True)
    assert len(st) == 1
    row = st.iloc[0]
    assert row["line_id"] == "e1"
    assert row["current"] == "unclassified"
    assert row["proposed"] == "textile_accessories"
    assert row["method"] == "supplier_stage"
    assert row["confidence"] == "medium"


def test_stage_low_tier_requires_five_rows():
    """A 2-of-3 stage majority is too thin to propose even at low
    confidence."""
    rows = [
        _row("a1", "买线", supplier="缝衣铺", amount=10.0,
             stage="textile_accessories"),
        _row("a2", "买边布", supplier="缝衣铺", amount=20.0,
             stage="textile_accessories"),
        _row("a3", "买胶水", supplier="缝衣铺", amount=30.0,
             stage="raw_materials"),
        _row("e1", "7号衣车针", supplier="缝衣铺", amount=15.0,
             stage="unclassified"),
    ]
    prop, _ = build_proposals(pd.DataFrame(rows))
    assert prop[prop["field"] == "stage"].empty


def test_stage_hint_for_mold_deposit():
    df = pd.DataFrame([
        _row("a1", "模费", supplier="塑艺坊", amount=700.0, stage="tooling_molds"),
        _row("e1", "合金模定金50%", amount=400.0, stage="raw_materials"),
        _row("e2", "塑胶模订金", amount=280.0, stage="tooling_molds"),
    ])
    prop, _ = build_proposals(df)
    st = prop[prop["field"] == "stage"].reset_index(drop=True)
    assert len(st) == 1
    assert st.iloc[0]["line_id"] == "e1"
    assert st.iloc[0]["proposed"] == "tooling_molds"
    assert st.iloc[0]["confidence"] == "medium"


def test_no_evidence_means_no_proposals():
    df = pd.DataFrame([
        _row("a1", "买螺丝", supplier="甲坊", amount=5.0, stage="raw_materials"),
        _row("e1", "神秘开销", amount=50.0, stage="admin_other"),
    ])
    prop, _ = build_proposals(df)
    assert prop.empty


# --- output contract -----------------------------------------------------

def test_proposal_columns_and_stats():
    df = _design_pool()
    prop, stats = build_proposals(df)
    assert list(prop.columns) == [
        "line_id", "field", "current", "proposed", "confidence", "method", "evidence",
    ]
    assert set(prop["field"]) <= {"supplier", "stage"}
    assert stats["empty_supplier_rows"] == 1
    assert stats["recovered_medium_plus_share"] > 0.0
    # no prepayment lines here -> nothing structurally unattributable
    assert stats["structural_unattributable_amount"] == 0.0
    assert stats["addressable_amount"] == 200.0


def test_write_reports_produces_csv_and_markdown(tmp_path):
    df = _design_pool()
    prop, stats = build_proposals(df)
    write_reports(prop, stats, df, tmp_path)
    csv = pd.read_csv(tmp_path / "attribution_proposals.csv")
    assert "line_id" in csv.columns
    assert "evidence" in csv.columns
    md = (tmp_path / "attribution_report.md").read_text(encoding="utf-8")
    assert "Supplier recovery" in md
    assert "medium" in md
