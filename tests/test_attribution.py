"""Attribution application layer (GH#39): generic keyword supplier rules +
exact-name overrides loaded from a gitignored data/dict CSV.

Every frame and name below is synthetic: invented line ids, suppliers
(e.g. 'Star Tooling Co.') and amounts. No real ledger rows are reproduced.
"""

import pandas as pd

from action_figures.attribution import (
    application_rows,
    apply_attribution,
    load_attribution_overrides,
)


def _row(line_id="L1", item="杂费", supplier="", amount=10.0,
         stage="raw_materials"):
    return {
        "line_id": line_id,
        "item": item,
        "supplier": supplier,
        "amount": amount,
        "stage": stage,
    }


OVERRIDES_CSV = (
    "line_id,field,value,method,confidence,status,reason\n"
    "T1,supplier,Star Tooling Co.,twin_row,medium,applied,\n"
    "T2,supplier,Acme Molds,twin_row,high,applied,\n"
    "T3,supplier,Ghost Ltd,substring,low,skipped,low confidence - below the GH#39 medium+ bar\n"
)


# --- overrides loader ------------------------------------------------------

def test_load_overrides_missing_file_returns_empty(tmp_path):
    assert load_attribution_overrides(tmp_path / "nope.csv") == []


def test_load_overrides_separates_applied_from_skipped(tmp_path):
    path = tmp_path / "attribution_overrides.csv"
    path.write_text(OVERRIDES_CSV, encoding="utf-8")
    overrides = load_attribution_overrides(path)
    applied = [o for o in overrides if o["status"] == "applied"]
    assert [o["line_id"] for o in applied] == ["T1", "T2"]
    assert applied[0]["field"] == "supplier"
    assert applied[0]["value"] == "Star Tooling Co."


# --- generic keyword rules --------------------------------------------------

def test_rotocast_keyword_fills_empty_supplier():
    df = pd.DataFrame([_row(item="头仔搪胶模费", stage="tooling_molds")])
    out = apply_attribution(df)
    assert out.loc[0, "supplier"] == "搪胶"
    assert out.loc[0, "supplier_source"] == "keyword"


def test_design_drawing_keyword_fills_empty_supplier():
    df = pd.DataFrame([_row(item="外发头雕画图尾款",
                            stage="design_prototyping")])
    out = apply_attribution(df)
    assert out.loc[0, "supplier"] == "外发"
    assert out.loc[0, "supplier_source"] == "keyword"


def test_keyword_rules_never_overwrite_a_named_supplier():
    df = pd.DataFrame([_row(item="头仔搪胶模费", supplier="Star Tooling Co.")])
    out = apply_attribution(df)
    assert out.loc[0, "supplier"] == "Star Tooling Co."
    assert out.loc[0, "supplier_source"] == "ledger"


def test_ledger_rows_get_ledger_source():
    df = pd.DataFrame([_row(item="杂费", supplier="Star Tooling Co.")])
    out = apply_attribution(df)
    assert list(out["supplier_source"]) == ["ledger"]


def test_no_match_leaves_supplier_empty():
    df = pd.DataFrame([_row(item="杂费")])
    out = apply_attribution(df)
    assert out.loc[0, "supplier"] == ""
    assert out.loc[0, "supplier_source"] == "ledger"


# --- exact-name overrides ---------------------------------------------------

def test_override_applies_by_line_id_only_when_supplier_empty(tmp_path):
    path = tmp_path / "attribution_overrides.csv"
    path.write_text(OVERRIDES_CSV, encoding="utf-8")
    df = pd.DataFrame([
        _row(line_id="T1", item="弹簧"),
        _row(line_id="T2", item="模芯做模", supplier="Star Tooling Co."),
        _row(line_id="T9", item="弹簧"),
    ])
    out = apply_attribution(df, load_attribution_overrides(path))
    assert out.loc[0, "supplier"] == "Star Tooling Co."
    assert out.loc[0, "supplier_source"] == "override"
    # a named ledger supplier is stronger than an override
    assert out.loc[1, "supplier"] == "Star Tooling Co."
    assert out.loc[1, "supplier_source"] == "ledger"
    # unknown line_id untouched
    assert out.loc[2, "supplier"] == ""


def test_skipped_override_rows_are_not_applied(tmp_path):
    path = tmp_path / "attribution_overrides.csv"
    path.write_text(OVERRIDES_CSV, encoding="utf-8")
    df = pd.DataFrame([_row(line_id="T3", item="杂费")])
    out = apply_attribution(df, load_attribution_overrides(path))
    assert out.loc[0, "supplier"] == ""


def test_input_frame_not_mutated():
    df = pd.DataFrame([_row(item="头仔搪胶模费")])
    apply_attribution(df)
    assert df.loc[0, "supplier"] == ""
    assert "supplier_source" not in df.columns


# --- application status of a previous proposals list ------------------------

def _proposals():
    return pd.DataFrame(
        [
            {
                "line_id": "P1", "field": "supplier", "current": "",
                "proposed": "Star Tooling Co.", "confidence": "medium",
                "method": "twin_row",
                "evidence": "twin line X: same amount 10.00",
            },
            {
                "line_id": "P2", "field": "stage", "current": "unclassified",
                "proposed": "design_prototyping", "confidence": "low",
                "method": "supplier_stage",
                "evidence": "supplier '外发': 33/42 rows are design_prototyping",
            },
        ]
    )


def test_application_rows_report_applied_and_skipped():
    staged = pd.DataFrame(
        [
            _row(line_id="P1", item="弹簧", supplier="Star Tooling Co.",
                 stage="raw_materials"),
            _row(line_id="P2", item="外发画图", supplier="外发",
                 stage="unclassified"),
        ]
    )
    staged["supplier_source"] = ["override", "ledger"]
    rows = application_rows(_proposals(), staged)
    by_id = {r["line_id"]: r for r in rows}
    assert by_id["P1"]["status"] == "applied"
    assert by_id["P1"]["mechanism"] == "override"
    assert by_id["P2"]["status"] == "skipped"
    assert "low confidence" in by_id["P2"]["reason"]


def test_application_rows_detects_rule_applied_stage_proposal():
    staged = pd.DataFrame(
        [_row(line_id="P2", item="外发画图", supplier="外发",
              stage="design_prototyping")]
    )
    staged["supplier_source"] = ["keyword"]
    rows = application_rows(_proposals(), staged)
    by_id = {r["line_id"]: r for r in rows}
    assert by_id["P2"]["status"] == "applied"
    assert by_id["P2"]["mechanism"] == "rule"


def test_application_rows_marks_partially_applied_as_skipped():
    # a proposal whose value was NOT the one applied is not silently counted
    staged = pd.DataFrame(
        [_row(line_id="P1", item="弹簧", supplier="Other Ltd.")]
    )
    staged["supplier_source"] = ["override"]
    rows = application_rows(_proposals(), staged)
    by_id = {r["line_id"]: r for r in rows}
    assert by_id["P1"]["status"] == "skipped"
    assert "applied value differs" in by_id["P1"]["reason"]


def test_application_rows_empty_previous():
    staged = pd.DataFrame([_row()])
    staged["supplier_source"] = ["ledger"]
    assert application_rows(pd.DataFrame(), staged) == []


def test_application_md_section_summarizes_and_lists_every_proposal():
    from action_figures.attribute_audit import _application_md

    staged = pd.DataFrame(
        [
            _row(line_id="P1", item="弹簧", supplier="Star Tooling Co.",
                 stage="raw_materials"),
            _row(line_id="P2", item="外发画图", supplier="外发",
                 stage="unclassified"),
        ]
    )
    staged["supplier_source"] = ["override", "ledger"]
    md = _application_md(_proposals(), staged)
    assert "applied **1**" in md
    assert "skipped **0**" in md  # P2 is low confidence: listed, not counted
    assert "| P1 | supplier | Star Tooling Co. | medium | applied | override |" in md
    assert "low confidence" in md
    # every previous proposal is listed, applied or not
    assert md.count("\n| P") == 2


def test_application_md_empty_previous_is_empty():
    from action_figures.attribute_audit import _application_md

    staged = pd.DataFrame([_row()])
    staged["supplier_source"] = ["ledger"]
    assert _application_md(pd.DataFrame(), staged) == ""
