"""Dictionary-based zh→en translation of staged expense rows.

Pure functions: chunk CSVs and staged pandas frames go in, a translation
table and translated frames come out. Input frames are never mutated.
Rows whose zh value is missing from the dictionary fall back to en = zh
and are reported back as gaps.

Status semantics in data/dict/translation.csv (issue #4 terms in parens):
- translated ("ok") — the zh value has an en translation; consumers use en.
- gap ("fallback") — no en translation; consumers fall back to en = zh.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

import pandas as pd

# Staged columns whose values are natural-language zh text and get translated.
# Codes (line_id, style_no, batch), dates, numbers and provenance columns
# (source_file, source_sheet) are left as-is.
TEXT_COLUMNS = ("item", "unit", "purpose", "supplier", "remarks")

TRANSLATION_COLUMNS = ["zh", "en", "column_hint", "n_occurrences", "status"]


def load_chunks(chunks_dir: str | Path) -> pd.DataFrame:
    """Concatenate chunk_*.csv files (zh, column_hint, n_occurrences, en)."""
    paths = sorted(Path(chunks_dir).glob("chunk_*.csv"))
    if not paths:
        raise FileNotFoundError(f"no chunk_*.csv files in {chunks_dir}")
    frames = [
        pd.read_csv(path, dtype=str).fillna("") for path in paths
    ]
    chunks = pd.concat(frames, ignore_index=True)
    for column in ("zh", "en", "column_hint"):
        if column not in chunks.columns:
            raise ValueError(f"chunk files miss the {column!r} column")
    return chunks


def count_occurrences(
    frames: Iterable[pd.DataFrame],
    columns: Sequence[str] = TEXT_COLUMNS,
) -> dict[str, int]:
    """Count non-empty text-cell values across staged frames."""
    counter: Counter[str] = Counter()
    for frame in frames:
        for column in columns:
            if column not in frame.columns:
                continue
            values = frame[column].dropna().astype(str).str.strip()
            counter.update(v for v in values if v)
    return dict(counter)


def build_translation(
    chunks: pd.DataFrame,
    occurrences: Mapping[str, int],
) -> pd.DataFrame:
    """Merge chunk translations with real occurrence counts.

    Chunk rows keep their order; zh values seen in the frames but absent
    from the chunks are appended as gap rows (empty en).
    """
    rows = []
    seen: set[str] = set()
    for chunk in chunks.itertuples(index=False):
        zh = str(chunk.zh)
        en = str(chunk.en).strip()
        seen.add(zh)
        rows.append(
            {
                "zh": zh,
                "en": en,
                "column_hint": str(chunk.column_hint),
                "n_occurrences": int(occurrences.get(zh, 0)),
                "status": "translated" if en else "gap",
            }
        )
    for zh, count in sorted(occurrences.items(), key=lambda kv: -kv[1]):
        if zh not in seen:
            rows.append(
                {
                    "zh": zh,
                    "en": "",
                    "column_hint": "",
                    "n_occurrences": int(count),
                    "status": "gap",
                }
            )
    return pd.DataFrame(rows, columns=TRANSLATION_COLUMNS)


def apply_dictionary(
    frame: pd.DataFrame,
    dictionary: Mapping[str, str],
    columns: Sequence[str] = TEXT_COLUMNS,
) -> tuple[pd.DataFrame, list[str]]:
    """Return a translated copy of frame plus the list of untranslated zh values.

    Every output column/row/line_id matches the input; text cells missing
    from the dictionary fall back to the original zh value.
    """
    en_frame = frame.copy()
    gaps: set[str] = set()
    for column in columns:
        if column not in en_frame.columns:
            continue
        translated = []
        for value in en_frame[column]:
            if pd.isna(value):
                translated.append(value)
                continue
            text = str(value)
            translated.append(dictionary.get(text, text))
            if text and text not in dictionary:
                gaps.add(text)
        en_frame[column] = translated
    return en_frame, sorted(gaps)
