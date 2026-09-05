"""Classify reimbursement line items into production stages.

Pure functions: a pandas DataFrame plus a taxonomy mapping go in,
stage / stage_confidence columns come out. The input frame is never mutated.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_CONFIG_TAXONOMY = REPO_ROOT / "config" / "taxonomy.yaml"

# Field priority: a hit in the item text is strongest, then purpose,
# then supplier / remarks.
FIELDS_WITH_CONFIDENCE = (
    (("item",), 1.0),
    (("purpose",), 0.8),
    (("supplier", "remarks"), 0.6),
)

UNCLASSIFIED = "unclassified"


def load_taxonomy(path: str | Path = REPO_CONFIG_TAXONOMY) -> dict[str, list[str]]:
    """Load config/taxonomy.yaml as an ordered {stage: [zh keywords]} mapping."""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    stages = data["stages"]
    if not isinstance(stages, Mapping) or not stages:
        raise ValueError(f"taxonomy {path} has no stages")
    return dict(stages)


def _as_text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value)


def _first_stage_hit(text: str, taxonomy: Mapping[str, Sequence[str]]) -> str | None:
    for stage, keywords in taxonomy.items():
        for keyword in keywords:
            if keyword and keyword in text:
                return stage
    return None


def classify_text(
    item: object,
    purpose: object,
    supplier: object,
    remarks: object,
    taxonomy: Mapping[str, Sequence[str]],
) -> tuple[str, float]:
    """Classify one line by searching item/purpose/supplier/remarks.

    Stage priority: taxonomy order (top → down). Field priority: item
    (confidence 1.0) > purpose (0.8) > supplier/remarks (0.6).
    Returns ("unclassified", 0.0) when nothing matches.
    """
    fields = {
        "item": _as_text(item),
        "purpose": _as_text(purpose),
        "supplier": _as_text(supplier),
        "remarks": _as_text(remarks),
    }
    for names, confidence in FIELDS_WITH_CONFIDENCE:
        for name in names:
            stage = _first_stage_hit(fields[name], taxonomy)
            if stage is not None:
                return stage, confidence
    return UNCLASSIFIED, 0.0


def classify_df(
    df: pd.DataFrame,
    taxonomy: Mapping[str, Sequence[str]] | None = None,
) -> pd.DataFrame:
    """Return a copy of df with added stage / stage_confidence columns."""
    if taxonomy is None:
        taxonomy = load_taxonomy()
    out = df.copy()
    pairs = [
        classify_text(row.get("item"), row.get("purpose"), row.get("supplier"),
                      row.get("remarks"), taxonomy)
        for row in out.to_dict("records")
    ]
    out["stage"] = [stage for stage, _ in pairs]
    out["stage_confidence"] = [confidence for _, confidence in pairs]
    return out
