"""Tests for scripts/build_dict.py chunk generation (synthetic frames only)."""

import importlib.util
import sys
from pathlib import Path

import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
_spec = importlib.util.spec_from_file_location(
    "build_dict", SCRIPTS_DIR / "build_dict.py"
)
build_dict = importlib.util.module_from_spec(_spec)
sys.modules["build_dict"] = build_dict
_spec.loader.exec_module(build_dict)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "line_id": ["a", "b", "c"],
            "item": ["开模费", "开模费", "其他"],
            "unit": ["个", "个", "个"],
            "supplier": ["星辰快运", "星辰快运", "别家"],
        }
    )


def test_build_chunk_rows_counts_and_hints():
    rows = build_dict.build_chunk_rows([_frame()])
    assert list(rows.columns) == ["zh", "column_hint", "n_occurrences", "en"]
    by_zh = rows.set_index("zh")
    # sorted by occurrences, ties keep deterministic order
    assert by_zh.loc["个", "n_occurrences"] == 3
    assert by_zh.loc["个", "column_hint"] == "unit"
    assert by_zh.loc["开模费", "n_occurrences"] == 2
    assert by_zh.loc["开模费", "column_hint"] == "item"
    assert (rows["en"] == "").all()
    # a value seen in several text columns appears once, hint = first hit
    assert "line_id" not in by_zh.index


def test_write_chunks_splits_and_cleans_stale(tmp_path: Path):
    rows = build_dict.build_chunk_rows([_frame()])
    n = build_dict.write_chunks(rows, tmp_path, rows_per_chunk=2)
    assert n == 3  # 5 distinct values / 2 per chunk
    names = sorted(p.name for p in tmp_path.glob("chunk_*.csv"))
    assert names == ["chunk_1.csv", "chunk_2.csv", "chunk_3.csv"]
    # a smaller re-split removes stale higher-numbered chunks
    n2 = build_dict.write_chunks(rows, tmp_path, rows_per_chunk=10)
    assert n2 == 1
    assert [p.name for p in tmp_path.glob("chunk_*.csv")] == ["chunk_1.csv"]
    assert len(pd.read_csv(tmp_path / "chunk_1.csv")) == len(rows)
