"""Tests for dictionary building and zh→en frame translation.

All fixtures are synthetic: fake zh values that mirror the real chunk layout
(zh, column_hint, n_occurrences, en) and fake staged rows.
"""

from pathlib import Path

import pandas as pd
import pytest

from action_figures.translate import (
    TEXT_COLUMNS,
    apply_dictionary,
    build_translation,
    count_occurrences,
    load_chunks,
)


@pytest.fixture()
def chunks_dir(tmp_path: Path) -> Path:
    """Two synthetic chunk files with the real chunk CSV layout."""
    d = tmp_path / "chunks"
    d.mkdir()
    pd.DataFrame(
        {
            "zh": ["个", "开模费"],
            "column_hint": ["unit", "item"],
            "n_occurrences": [0, 0],
            "en": ["pc", "mold fee"],
        }
    ).to_csv(d / "chunk_1.csv", index=False)
    pd.DataFrame(
        {
            "zh": ["星辰快运", "未知词"],
            "column_hint": ["supplier", "item"],
            "n_occurrences": [0, 0],
            "en": ["Xingchen Express", ""],
        }
    ).to_csv(d / "chunk_2.csv", index=False)
    return d


@pytest.fixture()
def staged() -> pd.DataFrame:
    """A miniature staged frame: same column contract as data/pkl/zh."""
    return pd.DataFrame(
        {
            "line_id": ["aaa", "bbb", "ccc"],
            "item": ["开模费", "开模费", "未知词"],
            "unit": ["个", "个", "个"],
            "supplier": ["星辰快运", "别的", "星辰快运"],
            "qty": [1.0, 2.0, 3.0],
            "amount": [10.0, 20.0, 30.0],
        }
    )


def test_load_chunks_concatenates_in_order(chunks_dir: Path):
    chunks = load_chunks(chunks_dir)
    assert list(chunks["zh"]) == ["个", "开模费", "星辰快运", "未知词"]
    assert list(chunks["column_hint"]) == ["unit", "item", "supplier", "item"]


def test_count_occurrences_over_text_columns(staged: pd.DataFrame):
    counts = count_occurrences([staged])
    # only TEXT_COLUMNS are counted; qty / amount / line_id never are
    assert counts == {"开模费": 2, "个": 3, "星辰快运": 2, "别的": 1, "未知词": 1}
    assert "aaa" not in counts


def test_build_translation_marks_translated_and_gap(chunks_dir: Path, staged: pd.DataFrame):
    chunks = load_chunks(chunks_dir)
    counts = count_occurrences([staged])
    table = build_translation(chunks, counts)
    assert list(table.columns) == ["zh", "en", "column_hint", "n_occurrences", "status"]
    by_zh = table.set_index("zh")
    assert by_zh.loc["个", "n_occurrences"] == 3
    assert by_zh.loc["开模费", "n_occurrences"] == 2
    # translated rows get status translated, the empty-en row becomes a gap
    assert by_zh.loc["个", "status"] == "translated"
    assert by_zh.loc["未知词", "status"] == "gap"
    # unknown-to-chunks zh values from the frames are appended as gaps
    assert by_zh.loc["别的", "status"] == "gap"
    assert by_zh.loc["别的", "en"] == ""


def test_apply_dictionary_keeps_shape_and_line_ids(staged: pd.DataFrame):
    dictionary = {"开模费": "mold fee", "个": "pc", "星辰快运": "Xingchen Express"}
    en_df, gaps = apply_dictionary(staged, dictionary)
    # parity: same rows, same columns, same line_id order
    assert en_df.shape == staged.shape
    assert list(en_df.columns) == list(staged.columns)
    assert list(en_df["line_id"]) == list(staged["line_id"])
    # numeric columns untouched
    assert en_df["qty"].tolist() == staged["qty"].tolist()
    assert en_df["amount"].tolist() == staged["amount"].tolist()
    # text columns translated, missing values fall back to zh
    assert en_df["item"].tolist() == ["mold fee", "mold fee", "未知词"]
    assert en_df["unit"].tolist() == ["pc", "pc", "pc"]
    assert en_df["supplier"].tolist() == ["Xingchen Express", "别的", "Xingchen Express"]
    assert sorted(gaps) == ["别的", "未知词"]


def test_apply_dictionary_on_empty_text_is_fallback():
    frame = pd.DataFrame({"line_id": ["x"], "item": [None], "unit": [""]})
    en_df, gaps = apply_dictionary(frame, {})
    assert en_df["item"].isna().all()
    assert en_df["unit"].tolist() == [""]
    assert gaps == []


def test_text_columns_exist_in_real_staged_pkls():
    """Contract guard: every TEXT_COLUMNS member is a real staged column."""
    staged_cols = {
        "line_id", "month", "date", "date_raw", "style_no", "batch", "item",
        "qty", "unit", "unit_price", "amount", "purpose", "supplier",
        "remarks", "freight_collect", "source_file", "source_sheet", "row_idx",
    }
    assert set(TEXT_COLUMNS) <= staged_cols
