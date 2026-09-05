"""Чтение листов xls/xlsx цепочкой движков calamine → openpyxl → xlrd.

XML-листы исходников раздуты форматированием, поэтому пустые
стилизованные ячейки дропаются сразу: значения читаются как values-only,
полностью пустые строки/колонки отбрасываются.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


class EngineError(RuntimeError):
    """Ни один движок не смог прочитать лист."""


def _clean_rows(rows: list[list[Any]]) -> list[list[Any]]:
    """Дроп пустых (в т.ч. стилизованных) строк и хвостовых пустых колонок."""
    rows = [r for r in rows if any(v is not None and v != "" for v in r)]
    if not rows:
        return []
    width = 0
    for r in rows:
        for i in range(len(r) - 1, width - 1, -1):
            if r[i] is not None and r[i] != "":
                width = i + 1
                break
    return [list(r[:width]) + [None] * (width - len(r)) for r in rows]


def _read_calamine(path: Path, sheet: str) -> list[list[Any]]:
    from python_calamine import CalamineWorkbook

    wb = CalamineWorkbook.from_path(str(path))
    names = wb.sheet_names
    if sheet not in names:
        raise EngineError(f"лист {sheet!r} отсутствует ({names})")
    return wb.get_sheet_by_name(sheet).to_python(skip_empty_area=False)


def _read_openpyxl(path: Path, sheet: str) -> list[list[Any]]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet not in wb.sheetnames:
            raise EngineError(f"лист {sheet!r} отсутствует ({wb.sheetnames})")
        ws = wb[sheet]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def _read_xlrd(path: Path, sheet: str) -> list[list[Any]]:
    import xlrd

    book = xlrd.open_workbook(str(path))
    try:
        sh = book.sheet_by_name(sheet)
    except xlrd.biffh.XLRDError as e:
        raise EngineError(str(e)) from e
    return [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]


_READERS = (_read_calamine, _read_openpyxl, _read_xlrd)


def list_sheets(path: str | Path) -> list[str]:
    """Имена листов в порядке книги (та же цепочка движков)."""
    path = Path(path)
    if path.suffix.lower() == ".xls":
        import xlrd

        return xlrd.open_workbook(str(path)).sheet_names()
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def get_datemode(path: str | Path) -> int:
    """Excel date-система файла: 0 = 1900, 1 = 1904 (важно для xls/xlrd)."""
    path = Path(path)
    if path.suffix.lower() == ".xls":
        import xlrd

        return xlrd.open_workbook(str(path)).datemode
    return 0  # xlsx всегда 1900


def read_sheet(path: str | Path, sheet: str) -> tuple[list[list[Any]], str]:
    """Вернуть (строки_значений, имя_движка). Пустые стилизованные дропнуты."""
    path = Path(path)
    last: Exception | None = None
    for reader in _READERS:
        if reader is _read_openpyxl and path.suffix.lower() == ".xls":
            continue  # openpyxl не читает бинарный xls
        if reader is _read_xlrd and path.suffix.lower() != ".xls":
            continue  # xlrd 2.x читает только xls
        try:
            rows = reader(path, sheet)
        except EngineError:
            raise
        except ImportError:
            continue
        except Exception as e:  # следующий движок
            last = e
            continue
        return _clean_rows(rows), reader.__name__.removeprefix("_read_")
    raise EngineError(f"нет движка для {path}::{sheet}: {last}")
