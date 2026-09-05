"""Smoke test: conftest synthetic fixtures work end-to-end (write xlsx, read back)."""

from conftest import ZH_COLUMNS, make_fake_frame


def test_fake_frame_shape_and_columns():
    df = make_fake_frame(n_rows=15, seed=1)
    assert list(df.columns) == ZH_COLUMNS
    assert len(df) == 15


def test_fake_xlsx_roundtrip(fake_xlsx):
    import pandas as pd

    df = pd.read_excel(fake_xlsx)
    assert list(df.columns) == ZH_COLUMNS
    assert 5 <= len(df) <= 20
    # 金额 == 数量 * 单价 for synthetic rows
    assert (df["金额"] == (df["数量"] * df["单价"]).round(2)).all()
