"""Тесты дедуп-ключа и слияния майских листов (xlsx — канон, xls дозаполняет)."""
import pandas as pd

from action_figures.schema import dedup_key, merge_month_dfs


def _row(**kw):
    base = dict(date=pd.Timestamp("2026-05-09"), style_no="AF-1003", item="测试材料",
                qty=1, amount=288.0, remarks=None)
    base.update(kw)
    return base


def test_dedup_key_normalizes_fields():
    # ±1d по дате — на merge, не в ключе: проверяется отдельным тестом ниже
    assert dedup_key(_row()) == dedup_key(_row(remarks="дозаполнено"))  # remarks не в ключе
    assert dedup_key(_row()) != dedup_key(_row(amount=289.0))


def test_merge_exact_duplicate_dropped():
    xlsx = pd.DataFrame([_row(source="xlsx")])
    xls = pd.DataFrame([_row(source="xls")])
    merged, stats = merge_month_dfs(xlsx, xls)
    assert len(merged) == 1
    assert stats["duplicates_dropped"] == 1
    assert stats["fields_filled"] == 0


def test_merge_date_tolerance_one_day():
    xlsx = pd.DataFrame([_row(date=pd.Timestamp("2026-05-09"), source="xlsx")])
    xls = pd.DataFrame([_row(date=pd.Timestamp("2026-05-10"), source="xls")])
    merged, stats = merge_month_dfs(xlsx, xls)
    assert len(merged) == 1
    assert stats["duplicates_dropped"] == 1


def test_merge_xls_fills_missing_canonical_fields():
    xlsx = pd.DataFrame([_row(remarks=None, style_no="AF-1003", source="xlsx")])
    xls = pd.DataFrame([_row(remarks="测试配件", source="xls")])
    merged, stats = merge_month_dfs(xlsx, xls)
    assert len(merged) == 1
    assert merged.iloc[0]["remarks"] == "测试配件"
    assert stats["fields_filled"] == 1


def test_merge_keeps_unique_xls_rows():
    xlsx = pd.DataFrame([_row(source="xlsx")])
    xls = pd.DataFrame([_row(item="другое", amount=100.0, source="xls")])
    merged, stats = merge_month_dfs(xlsx, xls)
    assert len(merged) == 2
    assert stats["duplicates_dropped"] == 0
