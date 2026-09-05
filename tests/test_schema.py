from datetime import date

from conftest import ZH_HEADER, _fake_rows

from action_figures.schema import (
    HEADER_MAP,
    detect_header_row,
    freight_collect,
    is_service_row,
    month_from_sheetname,
    parse_date,
)


def test_detect_header_row_finds_zh_header_anywhere():
    rows = _fake_rows()
    assert detect_header_row(rows) == 1
    # шапка на первой строке
    assert detect_header_row([ZH_HEADER[:]]) == 0
    # две строки-титула сверху
    assert detect_header_row([["x"], ["y"], ZH_HEADER[:]]) == 2


def test_detect_header_row_returns_none_without_header():
    assert detect_header_row([["费用报销明细"], ["мусор"]]) is None


def test_header_map_covers_core_columns():
    for zh in ["序号", "日期", "款号", "报销事项", "单位", "数量", "单价", "金额", "用途", "供应商", "备注"]:
        assert zh in HEADER_MAP


def test_parse_date_excel_serial_1900():
    assert parse_date(46024, datemode=0) == date(2026, 1, 2)


def test_parse_date_excel_serial_1904():
    assert parse_date(46024, datemode=1) == date(2030, 1, 3)


def test_parse_date_text_forms():
    assert parse_date("2026-05-09", datemode=0) == date(2026, 5, 9)
    assert parse_date("2026/5/9", datemode=0) == date(2026, 5, 9)
    assert parse_date("2026年5月9日", datemode=0) == date(2026, 5, 9)


def test_parse_date_passthrough_and_none():
    assert parse_date(date(2026, 5, 9), datemode=0) == date(2026, 5, 9)
    assert parse_date(None, datemode=0) is None
    assert parse_date("не дата", datemode=0) is None


def test_month_from_sheetname():
    assert month_from_sheetname("2026-05月 ") == "2026-05"
    assert month_from_sheetname("2025-12月") == "2025-12"
    assert month_from_sheetname("1月份", year_hint=2026) == "2026-01"
    assert month_from_sheetname("202501-02") == "2025-01"


def test_freight_collect_flag():
    # 运费到付 — это позиция (item) в 报销事项, сумма лежит в 金额:
    # фиксируем семантику как флаг «фрахт, оплачиваемый при получении»
    assert freight_collect("运费到付") is True
    assert freight_collect("5月寄件费用") is False
    assert freight_collect("运费寄付") is False
    assert freight_collect("") is False


def test_is_service_row_drops_totals_and_second_header():
    # итог листа: текст в числовой колонке + число в 金额
    assert is_service_row({"item": None, "unit_price": "总数：", "amount": 8631.87}) is True
    assert is_service_row({"item": None, "unit_price": "采购垫付：", "amount": 17715.8}) is True
    assert is_service_row({"item": None, "qty": "月结款汇总：", "amount": 9560.2}) is True
    # повторная шапка внутри листа
    assert is_service_row({"item": "报销事项", "qty": "数量", "unit_price": "单价", "amount": "金额"}) is True


def test_is_service_row_keeps_data_rows():
    assert is_service_row({"item": "5，6月寄件费用", "qty": 12, "unit_price": None, "amount": 165}) is False
    assert is_service_row({"item": "切割费", "qty": 1, "unit_price": 3620, "amount": 3620}) is False
    # строка-продолжение без item, но с корректными числами — тоже данные
    assert is_service_row({"item": None, "qty": 6000, "unit_price": 900, "amount": None}) is False
    # числа-строки и с запятыми парсятся — не служебные
    assert is_service_row({"qty": "10000", "unit_price": "0.076", "amount": "1,234.5"}) is False
