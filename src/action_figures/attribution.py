"""Attribution application layer (GH#39): fill empty suppliers left by the
ledger using (a) committed generic zh-keyword rules and (b) exact-name
overrides from the gitignored ``data/dict/attribution_overrides.csv``.

The rules mirror the taxonomy style: pure zh process/channel vocabulary,
never counterparty names. Exact supplier names (real counterparties) live
only in the gitignored overrides CSV, loaded at runtime — same pattern as
the translation dictionary (``data/dict/translation.csv``).

Nothing here reclassifies named-supplier rows: a supplier recorded in the
ledger always wins. Applications are provenance-tracked in a
``supplier_source`` column ("ledger" / "keyword" / "override") so downstream
reports can distinguish recorded vs attributed values.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd

# Generic keyword rules: (item keywords, supplier). Applied only to rows
# whose supplier cell is empty. Derived from the GH#10 forensic findings:
# - 搪胶 (rotocast) rows whose ledger never named the shop: the rotocast
#   process word doubles as the recorded counterparty name in this ledger
#   (supplier '搪胶' already exists in attributed rows).
# - 画图 (outsourced design drawing) rows: the 外发 outsourcing channel
#   serves 26/29 of the attributed design-drawing category (90%).
SUPPLIER_KEYWORD_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("搪胶",), "搪胶"),
    (("画图",), "外发"),
)

OVERRIDE_COLUMNS = [
    "line_id", "field", "value", "method", "confidence", "status", "reason",
]

LEDGER = "ledger"
KEYWORD = "keyword"
OVERRIDE = "override"


def load_attribution_overrides(
    path: str | Path,
) -> list[dict[str, str]]:
    """Read data/dict/attribution_overrides.csv -> list of row dicts.

    A missing file is not an error: the pipeline simply runs rule-only.
    Only ``status == "applied"`` rows are actionable; ``skipped`` rows stay
    in the file as the written record of proposals NOT applied (with the
    reason in the ``reason`` column).
    """
    path = Path(path)
    if not path.exists():
        return []
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    return [
        {str(key): str(value) for key, value in row.items()}
        for row in frame.to_dict("records")
    ]


def _empty(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):  # type: ignore[arg-type]
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def apply_attribution(
    df: pd.DataFrame,
    overrides: Sequence[Mapping[str, str]] | None = None,
    rules: tuple[tuple[tuple[str, ...], str], ...] = SUPPLIER_KEYWORD_RULES,
) -> pd.DataFrame:
    """Return a copy of df with empty suppliers filled + supplier_source.

    Priority: a named ledger supplier is never touched (source "ledger");
    then exact line_id overrides ("override"); then generic keyword rules
    ("keyword"). The input frame is not mutated.
    """
    out = df.copy()
    override_map = {
        str(o.get("line_id")): str(o.get("value", "")).strip()
        for o in (overrides or [])
        if o.get("status") == "applied" and o.get("field") == "supplier"
    }
    suppliers: list[object] = []  # unfilled rows keep the raw cell (may be NaN)
    sources: list[str] = []
    for rec in out.to_dict("records"):
        supplier = rec.get("supplier")
        source = LEDGER
        if _empty(supplier):
            suppliers.append(str(supplier))
            sources.append(source)
            continue
        filled = ""
        line_id = str(rec.get("line_id"))
        if line_id in override_map:
            filled, source = override_map[line_id], OVERRIDE
        else:
            item = str(rec.get("item") or "")
            for keywords, name in rules:
                if any(kw in item for kw in keywords):
                    filled, source = name, KEYWORD
                    break
        suppliers.append(filled if filled else supplier)
        sources.append(source)
    out["supplier"] = suppliers
    out["supplier_source"] = sources
    return out


def application_rows(
    previous_proposals: pd.DataFrame,
    staged: pd.DataFrame,
) -> list[dict[str, str]]:
    """Status of every previous proposal against the re-attributed frame.

    Each row: line_id / field / proposed / confidence / status
    ("applied" | "skipped") / mechanism ("rule" | "override" | "") /
    reason. A proposal counts as applied only when the staged row now
    carries exactly the proposed value; anything else is skipped with a
    written reason (GH#39 acceptance: applied or explicitly skipped).
    """
    if not len(previous_proposals):
        return []
    sources = dict(
        zip(staged["line_id"].astype(str),
            staged.get("supplier_source", pd.Series([LEDGER] * len(staged))),
            strict=False,
        )
    )
    current = {
        str(r["line_id"]): r for r in staged.to_dict("records")
    }
    rows: list[dict[str, str]] = []
    for prop in previous_proposals.to_dict("records"):
        line_id = str(prop.get("line_id"))
        field = str(prop.get("field"))
        proposed = str(prop.get("proposed"))
        confidence = str(prop.get("confidence"))
        rec = current.get(line_id)
        if rec is None:
            rows.append({
                "line_id": line_id, "field": field, "proposed": proposed,
                "confidence": confidence, "status": "skipped",
                "mechanism": "", "reason": "line not found in staged data",
            })
            continue
        got = _empty(rec.get(field))
        if got == proposed and got:
            source = str(sources.get(line_id, LEDGER))
            mechanism = (
                "override" if source == OVERRIDE
                else "rule" if source == KEYWORD
                else "taxonomy" if field == "stage"
                else "ledger"
            )
            rows.append({
                "line_id": line_id, "field": field, "proposed": proposed,
                "confidence": confidence, "status": "applied",
                "mechanism": mechanism, "reason": "",
            })
        elif got and got != str(prop.get("current")):
            rows.append({
                "line_id": line_id, "field": field, "proposed": proposed,
                "confidence": confidence, "status": "skipped",
                "mechanism": "",
                "reason": f"applied value differs: staged {field} is {got!r}",
            })
        else:
            rows.append({
                "line_id": line_id, "field": field, "proposed": proposed,
                "confidence": confidence, "status": "skipped",
                "mechanism": "",
                "reason": (
                    "low confidence — below the GH#39 medium+ bar"
                    if confidence == "low"
                    else "not applied via any rule/override"
                ),
            })
    return rows
