"""Схема данных: zh-заголовки → en-колонки, даты, месяц листа, дедуп-ключ.

Семантика 运费到付: это НЕ отдельная колонка и не сумма — это значение
колонки 报销事项 (позиция «фрахт, оплачиваемый при получении»); сумма
фрахта лежит в 金额. Фиксируем как булев флаг freight_collect:
True iff '到付' входит в item. Варианты 运费寄付/运费到寄付 флагом не
помечаются (это отправленный/смешанный фрахт) — различимо по item.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any, Literal

import pandas as pd

HEADER_MAP = {
    "序号": "seq",
    "日期": "date",
    "款号": "style_no",
    "报销事项": "item",
    "单位": "unit",
    "数量": "qty",
    "单价": "unit_price",
    "金额": "amount",
    "用途": "purpose",
    "供应商": "supplier",
    "备注": "remarks",
    "批次": "batch",
}

# обязательное ядро шапки для авто-детекта строки заголовков
_HEADER_CORE = {"序号", "日期", "金额"}

COLUMNS = [
    "line_id", "month", "date", "date_raw", "style_no", "batch", "item",
    "qty", "unit", "unit_price", "amount", "purpose", "supplier", "remarks",
    "freight_collect", "source_file", "source_sheet", "row_idx",
]

_TEXT_DATE = re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?")
_SHEET_YM = re.compile(r"(20\d{2})\s*[-年]?\s*(\d{1,2})\s*月")
_SHEET_YM_COMPACT = re.compile(r"^(20\d{2})(\d{2})")
_SHEET_M = re.compile(r"^(\d{1,2})月份")


def detect_header_row(rows: list[list[Any]]) -> int | None:
    """Индекс строки шапки: строка, содержащая всё ядро _HEADER_CORE."""
    for i, row in enumerate(rows):
        cells = {str(v).strip() for v in row if v is not None}
        if _HEADER_CORE <= cells:
            return i
    return None


def parse_date(value: Any, datemode: int = 0) -> date | None:
    """Дата из ячейки: Excel-serial (учитывая datemode 1900/1904), datetime, текст."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        from typing import cast

        from xlrd.xldate import xldate_as_datetime

        mode = cast("Literal[0, 1]", 1 if datemode else 0)
        return xldate_as_datetime(float(value), mode).date()
    m = _TEXT_DATE.search(str(value))
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def month_from_sheetname(name: str, year_hint: int | None = None) -> str | None:
    """'2026-05月 ' → '2026-05'; '5月份' + year_hint → '2026-05'; '202501-02' → '2025-01'."""
    name = name.strip()
    m = _SHEET_YM.search(name)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    m = _SHEET_YM_COMPACT.match(name)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = _SHEET_M.match(name)
    if m and year_hint:
        return f"{year_hint}-{int(m.group(1)):02d}"
    return None


def freight_collect(item: Any) -> bool:
    return isinstance(item, str) and "到付" in item


def _is_floatable(value: Any) -> bool:
    if value in (None, ""):
        return False
    if isinstance(value, (int, float)):
        return True
    try:
        float(str(value).replace(",", "").replace("，", "").strip())
    except ValueError:
        return False
    return True


def is_service_row(row: Mapping[str, Any]) -> bool:
    """Служебная строка листа (не данные): итоги/сводки и повторная шапка.

    Признак: в числовой колонке (qty/unit_price/amount) непустое
    НЕчисловое значение — так выглядят 总数：/采购垫付：/月结款汇总：/
    垫付+月结： и повторная шапка (数量/单价/金额). Строки данных под
    повторной шапкой (числа или пусто в числовых) сохраняются.
    """
    return any(
        row.get(f) not in (None, "") and not _is_floatable(row.get(f))
        for f in ("qty", "unit_price", "amount")
    )


# ---------------------------------------------------------------------------
# Дедуп (май: xlsx 5月份 — канон, xls 2026-05月 дозаполняет пропуски)

KEY_FIELDS = ("style_no", "item", "qty", "amount")
DATE_TOLERANCE = timedelta(days=1)


def dedup_key(row: Mapping[str, Any]) -> tuple:
    """Ключ без даты (дата сравнивается с допуском ±1 день в merge_month_dfs)."""
    return tuple(row.get(f) for f in KEY_FIELDS)


def merge_month_dfs(
    xlsx: pd.DataFrame, xls: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Слияние двух месячных таблиц: дубни (ключ + дата ±1d) дропаются,
    недостающие поля канона дозаполняются из xls."""
    out = xlsx.copy()
    dropped = 0
    filled = 0
    used: set = set()
    xls_rows = xls.reset_index(drop=True)
    for _, xr in xls_rows.iterrows():
        xkey = dedup_key({str(k): v for k, v in xr.items()})
        xd = xr.get("date")
        match_i = None
        for i, cr in out.iterrows():
            if i in used:
                continue
            if dedup_key({str(k): v for k, v in cr.items()}) != xkey:
                continue
            cd = cr.get("date")
            if xd is None or pd.isna(xd):
                if cd is None or pd.isna(cd):
                    match_i = i
                    break
                continue
            if cd is None or pd.isna(cd):
                continue
            if abs(pd.Timestamp(cd) - pd.Timestamp(xd)) <= DATE_TOLERANCE:
                match_i = i
                break
        if match_i is not None:
            used.add(match_i)
            dropped += 1
            fill_cols = [c for c in ("date", "style_no", "batch", "item", "qty", "unit",
                                     "unit_price", "amount", "purpose", "supplier", "remarks")
                         if c in out.columns and c in xr.index]
            for col in fill_cols:
                cv = out.at[match_i, col]
                xv = xr.get(col)
                cv_empty = cv is None or (isinstance(cv, float) and pd.isna(cv)) or cv == ""
                xv_empty = xv is None or (isinstance(xv, float) and pd.isna(xv)) or xv == ""
                if cv_empty and not xv_empty:
                    out.at[match_i, col] = xv
                    filled += 1
        else:
            out = pd.concat([out, xr.to_frame().T], ignore_index=True)
    stats = {"duplicates_dropped": dropped, "fields_filled": filled,
             "rows_xlsx": len(xlsx), "rows_xls": len(xls), "rows_merged": len(out)}
    return out.reset_index(drop=True), stats
