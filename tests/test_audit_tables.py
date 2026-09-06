"""TDD tests for by_supplier_stage aggregation (synthetic data only)."""

import pandas as pd

from action_figures.audit_tables import by_supplier_month, by_supplier_stage, by_supplier_style


def make_staged_frame() -> pd.DataFrame:
    """One supplier × 2 stages × 2 months + a second supplier, synthetic."""
    return pd.DataFrame(
        [
            # supplier A: tooling in Jan and Mar, painting in Mar
            {"line_id": 1, "month": "2026-01", "supplier": "杭州宏达",
             "style_no": "AF-1", "stage": "tooling_molds", "amount": 100.0},
            {"line_id": 2, "month": "2026-03", "supplier": "杭州宏达",
             "style_no": "AF-2", "stage": "tooling_molds", "amount": 50.5},
            {"line_id": 3, "month": "2026-03", "supplier": "杭州宏达",
             "style_no": "AF-1", "stage": "painting_printing", "amount": 25.0},
            # supplier B: one painting line in Feb
            {"line_id": 4, "month": "2026-02", "supplier": "东莞精密",
             "style_no": "AF-2", "stage": "painting_printing", "amount": 10.0},
        ]
    )


def test_by_supplier_stage_rows_and_totals():
    out = by_supplier_stage(make_staged_frame())
    # supplier × stage pairs: A-tooling, A-painting, B-painting
    assert len(out) == 3
    rows = {(r.supplier, r.stage): r for r in out.itertuples(index=False)}
    a_tool = rows[("杭州宏达", "tooling_molds")]
    assert a_tool.amount_cny == 150.5
    assert a_tool.n_lines == 2
    assert a_tool.months_active == "2026-01;2026-03"
    a_paint = rows[("杭州宏达", "painting_printing")]
    assert a_paint.amount_cny == 25.0
    assert a_paint.months_active == "2026-03"
    b_paint = rows[("东莞精密", "painting_printing")]
    assert b_paint.n_lines == 1


def test_by_supplier_stage_columns_and_order():
    out = by_supplier_stage(make_staged_frame())
    assert list(out.columns) == [
        "supplier", "stage", "amount_cny", "n_lines", "months_active",
    ]
    # sorted by amount descending
    amounts = out["amount_cny"].tolist()
    assert amounts == sorted(amounts, reverse=True)


def test_by_supplier_stage_amount_sum_matches_input():
    frame = make_staged_frame()
    out = by_supplier_stage(frame)
    assert abs(out["amount_cny"].sum() - frame["amount"].sum()) < 0.01


# --- EI-3 (GH#28): supplier card inputs — per-month and per-style splits ----


def test_by_supplier_month_rows_and_columns():
    out = by_supplier_month(make_staged_frame())
    assert list(out.columns) == ["supplier", "month", "amount_cny"]
    rows = {(r.supplier, r.month): r.amount_cny
            for r in out.itertuples(index=False)}
    assert rows == {
        ("杭州宏达", "2026-01"): 100.0,
        ("杭州宏达", "2026-03"): 75.5,  # tooling 50.5 + painting 25.0
        ("东莞精密", "2026-02"): 10.0,
    }
    assert abs(out["amount_cny"].sum()
               - make_staged_frame()["amount"].sum()) < 0.01


def test_by_supplier_style_rows_and_columns():
    out = by_supplier_style(make_staged_frame())
    assert list(out.columns) == ["supplier", "style_no", "amount_cny", "n_lines"]
    rows = {(r.supplier, r.style_no): (r.amount_cny, r.n_lines)
            for r in out.itertuples(index=False)}
    assert rows == {
        ("杭州宏达", "AF-1"): (125.0, 2),
        ("杭州宏达", "AF-2"): (50.5, 1),
        ("东莞精密", "AF-2"): (10.0, 1),
    }
    assert abs(out["amount_cny"].sum()
               - make_staged_frame()["amount"].sum()) < 0.01
