"""Translate: build the zh→en dictionary, then translate staged pkls to en.

Reads the main checkout (absolute paths in config/paths.yaml) read-only:
chunk CSVs in data/dict/chunks/ and monthly staged pkls in data/pkl/zh/.
Writes data/dict/translation.csv, data/pkl/en/<month>.pkl (same rows,
columns and line_ids as the zh frames) and reports/translation/{gaps,qa}.md.
Original zh pkls are never modified.

Usage: python3 scripts/translate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from action_figures.translate import (  # noqa: E402
    TEXT_COLUMNS,
    apply_dictionary,
    build_translation,
    count_occurrences,
    load_chunks,
)


def _load_paths() -> tuple[Path, Path]:
    """Data and report roots come from config/paths.yaml (main checkout)."""
    with open(REPO_ROOT / "config" / "paths.yaml", encoding="utf-8") as fh:
        paths = yaml.safe_load(fh)
    return Path(paths["data_root"]), Path(paths["reports_root"])


DATA_ROOT, REPORTS_ROOT = _load_paths()
CHUNKS_DIR = DATA_ROOT / "dict" / "chunks"
TRANSLATION_CSV = DATA_ROOT / "dict" / "translation.csv"
ZH_DIR = DATA_ROOT / "pkl" / "zh"
EN_DIR = DATA_ROOT / "pkl" / "en"
REPORTS_DIR = REPORTS_ROOT / "translation"

MONTH_PKL = ["2026-01.pkl", "2026-02.pkl", "2026-03.pkl",
             "2026-04.pkl", "2026-05.pkl", "2026-06.pkl"]

# Only these monthly frames feed the dictionary occurrence counts; every
# other staged frame in zh/ (…_staged, all_months) is translated too, with
# the same dictionary, so en/ stays consistent file-for-file with zh/.
SPOT_CHECK_N = 20


def _load_zh_frames() -> dict[str, pd.DataFrame]:
    frames = {}
    for path in sorted(ZH_DIR.glob("*.pkl")):
        frame = pd.read_pickle(path)
        if "line_id" in frame.columns:  # skip raw pre-staging files
            frames[path.name] = frame
    return frames


def main() -> None:
    chunks = load_chunks(CHUNKS_DIR)
    zh_frames = _load_zh_frames()
    monthly = {name: zh_frames[name] for name in MONTH_PKL if name in zh_frames}
    occurrences = count_occurrences(monthly.values())

    table = build_translation(chunks, occurrences)
    table.to_csv(TRANSLATION_CSV, index=False)
    translated = table[table["status"] == "translated"]
    dictionary = dict(zip(translated["zh"], translated["en"], strict=True))

    EN_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    gaps_all: set[str] = set()
    total_cells = hit_cells = 0
    for name, zh_df in zh_frames.items():
        en_df, gaps = apply_dictionary(zh_df, dictionary)
        en_df.to_pickle(EN_DIR / name)
        gaps_all.update(gaps)

    for zh_df in monthly.values():
        for column in TEXT_COLUMNS:
            if column in zh_df.columns:
                values = zh_df[column].dropna().astype(str).str.strip()
                values = values[values != ""]
                total_cells += len(values)
                hit_cells += sum(v in dictionary for v in values)

    coverage = hit_cells / total_cells if total_cells else 0.0

    # gaps.md — every untranslated zh value with its occurrence count
    gap_rows = table[table["status"] == "gap"].sort_values(
        "n_occurrences", ascending=False
    )
    with open(REPORTS_DIR / "gaps.md", "w", encoding="utf-8") as fh:
        fh.write("# Translation gaps\n\n")
        fh.write(
            f"{len(gap_rows)} distinct zh values are not translated "
            f"(en falls back to zh). Coverage: {coverage:.2%}.\n\n"
        )
        fh.write("| zh | column_hint | n_occurrences |\n|---|---|---|\n")
        for row in gap_rows.itertuples(index=False):
            fh.write(f"| {row.zh} | {row.column_hint} | {row.n_occurrences} |\n")

    # qa.md — 20 random spot-check pairs plus the coverage figure
    sample = translated.sample(min(SPOT_CHECK_N, len(translated)), random_state=4)
    with open(REPORTS_DIR / "qa.md", "w", encoding="utf-8") as fh:
        fh.write("# Translation QA\n\n")
        fh.write(f"Dictionary: {len(table)} entries "
                 f"({len(translated)} translated, {len(gap_rows)} gaps).\n\n")
        fh.write(f"**Coverage: {coverage:.2%}** of text cells "
                 f"({hit_cells}/{total_cells}) translate via the dictionary.\n\n")
        fh.write(f"## Spot check — {len(sample)} random pairs\n\n")
        fh.write("| zh | en | column | n |\n|---|---|---|---|\n")
        for row in sample.itertuples(index=False):
            fh.write(f"| {row.zh} | {row.en} | {row.column_hint} "
                     f"| {row.n_occurrences} |\n")

    print(f"translation.csv: {len(table)} entries "
          f"({len(translated)} translated, {len(gap_rows)} gaps)")
    print(f"en pkls written to {EN_DIR} ({len(zh_frames)} frames)")
    print(f"coverage: {coverage:.2%} ({hit_cells}/{total_cells} cells)")


if __name__ == "__main__":
    main()
