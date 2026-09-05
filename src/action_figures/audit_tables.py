"""Aggregation tables for the audit report (pure pandas functions).

Input: a staged DataFrame (line_id, month, supplier, stage, amount).
Output: export-ready tables. The input frame is never mutated.
"""

from __future__ import annotations

import pandas as pd


def by_supplier_stage(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate staged lines by supplier × stage.

    Columns: supplier, stage, amount_cny, n_lines, months_active
    (months_active is a sorted `;`-joined list of active months).
    Rows sorted by amount_cny descending. Σ(amount_cny) == Σ(df.amount).
    """
    months = (
        df.groupby(["supplier", "stage", "month"], dropna=False).size()
        .reset_index(level="month")[["month"]]
    )
    months_active = (
        months.groupby(["supplier", "stage"])["month"]
        .apply(lambda s: ";".join(sorted(m for m in s if pd.notna(m))))
        .rename("months_active")
    )
    out = (
        df.groupby(["supplier", "stage"], dropna=False)
        .agg(n_lines=("line_id", "count"), amount_cny=("amount", "sum"))
        .join(months_active)
        .reset_index()
        .sort_values("amount_cny", ascending=False)
    )
    return out[["supplier", "stage", "amount_cny", "n_lines", "months_active"]]
