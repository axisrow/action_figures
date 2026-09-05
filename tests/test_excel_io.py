from conftest import _fake_rows

from action_figures.excel_io import EngineError, get_datemode, list_sheets, read_sheet

XLS_FIXTURE = "tests/fixtures/tiny_fake.xls"


def test_read_xlsx_drops_empty_styled(ingest_xlsx):
    rows, engine = read_sheet(ingest_xlsx, "5月份")
    assert engine in ("calamine", "openpyxl")
    # титул и шапка на месте, стилизованные пустые строки/колонки дропнуты
    assert len(rows) == 5  # титул + шапка + 3 данных
    assert rows[1][:11] == _fake_rows()[1]
    assert all(len(r) == 11 for r in rows)  # хвостовая пустая колонка отрезана


def test_read_xlsx_empty_sheet(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Sheet2"
    p = tmp_path / "empty.xlsx"
    wb.save(p)
    rows, _engine = read_sheet(p, "Sheet2")
    assert rows == []


def test_read_xls_binary_fixture():
    rows, engine = read_sheet(XLS_FIXTURE, "2026-05月")
    assert engine in ("calamine", "xlrd")
    assert rows[0][0] == "费用报销明细"  # титул
    assert rows[1][:4] == ["序号", "日期", "款号", "报销事项"]
    assert len(rows) == 5  # титул + шапка + 3 данных; пустые стилизованные дропнуты


def test_read_missing_sheet_raises(ingest_xlsx):
    try:
        read_sheet(ingest_xlsx, "нет такого")
    except EngineError:
        return
    raise AssertionError("ожидался EngineError для отсутствующего листа")


def test_list_sheets_and_datemode(ingest_xlsx):
    assert "5月份" in list_sheets(ingest_xlsx)
    assert get_datemode(ingest_xlsx) == 0  # openpyxl/calamine — система 1900
    assert "2026-05月" in list_sheets(XLS_FIXTURE)
    assert get_datemode(XLS_FIXTURE) == 0
