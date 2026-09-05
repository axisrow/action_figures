"""Build dict: generate translation chunk CSVs from the staged zh pkls.

Extracts every distinct non-empty text value (item / unit / purpose /
supplier / remarks) from the monthly staged pkls, counts occurrences, and
writes them as data/dict/chunks/chunk_N.csv with an empty `en` column for
manual translation. Re-running overwrites the chunk files, so hand-made
translations must be merged back before regeneration (they live on in
data/dict/translation.csv).

Status semantics (data/dict/translation.csv):
- translated — the zh value has an en translation; audit/dashboard stages
  treat it as "ok" and use the en text.
- gap — no en translation yet; consumers fall back to en = zh ("fallback").

Usage: python3 scripts/build_dict.py [--rows-per-chunk 50]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from action_figures.translate import TEXT_COLUMNS, count_occurrences  # noqa: E402


def _load_paths() -> tuple[Path, Path]:
    """Data and report roots come from config/paths.yaml (main checkout)."""
    with open(REPO_ROOT / "config" / "paths.yaml", encoding="utf-8") as fh:
        paths = yaml.safe_load(fh)
    return Path(paths["data_root"]), Path(paths["reports_root"])


DATA_ROOT, _REPORTS_ROOT = _load_paths()
ZH_DIR = DATA_ROOT / "pkl" / "zh"
CHUNKS_DIR = DATA_ROOT / "dict" / "chunks"

MONTH_PKL = ["2026-01.pkl", "2026-02.pkl", "2026-03.pkl",
             "2026-04.pkl", "2026-05.pkl", "2026-06.pkl"]

# A value seen in several columns is reported once, under the column
# where it occurs most often.
COLUMN_PRIORITY = ("item", "purpose", "supplier", "remarks", "unit")


def build_chunk_rows(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """One row per distinct zh value: zh, column_hint, n_occurrences, en."""
    per_column = {
        column: count_occurrences(frames, columns=[column])
        for column in COLUMN_PRIORITY
        if column in TEXT_COLUMNS
    }
    total = count_occurrences(frames, columns=per_column.keys())
    hints: dict[str, str] = {}
    for column in COLUMN_PRIORITY:
        for zh in per_column.get(column, {}):
            hints.setdefault(zh, column)
    rows = [
        {
            "zh": zh,
            "column_hint": hints.get(zh, ""),
            "n_occurrences": count,
            "en": "",
        }
        for zh, count in sorted(total.items(), key=lambda kv: -kv[1])
    ]
    return pd.DataFrame(rows, columns=["zh", "column_hint", "n_occurrences", "en"])


def write_chunks(rows: pd.DataFrame, chunks_dir: Path, rows_per_chunk: int) -> int:
    """Split rows into chunk_1.csv…chunk_N.csv (fixed lexicographic order)."""
    chunks_dir.mkdir(parents=True, exist_ok=True)
    n_chunks = (len(rows) + rows_per_chunk - 1) // rows_per_chunk
    for idx in range(n_chunks):
        part = rows.iloc[idx * rows_per_chunk:(idx + 1) * rows_per_chunk]
        part.to_csv(chunks_dir / f"chunk_{idx + 1}.csv", index=False)
    # drop stale chunk files from a previous, larger split
    for stale in sorted(chunks_dir.glob("chunk_*.csv")):
        try:
            if int(stale.stem.split("_")[1]) > n_chunks:
                stale.unlink()
        except (IndexError, ValueError):
            continue
    return n_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows-per-chunk", type=int, default=50)
    args = parser.parse_args()

    frames = [pd.read_pickle(ZH_DIR / name) for name in MONTH_PKL]
    rows = build_chunk_rows(frames)
    n_chunks = write_chunks(rows, CHUNKS_DIR, args.rows_per_chunk)
    print(f"{len(rows)} distinct zh values -> {n_chunks} chunks in {CHUNKS_DIR}")


if __name__ == "__main__":
    main()
