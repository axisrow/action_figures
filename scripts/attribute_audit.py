"""Forensic attribution audit (GH#10): recover empty-supplier and
unclassified rows from in-data evidence.

Reads all_months_staged.pkl read-only (absolute data root from
config/paths.yaml in the main checkout) and writes review artifacts into
reports/audit/: attribution_proposals.csv + attribution_report.md.
Original pickles are never modified.

Usage: python3 scripts/attribute_audit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from action_figures.attribute_audit import build_proposals, write_reports  # noqa: E402


def _load_paths() -> tuple[Path, Path]:
    """Data and report roots come from config/paths.yaml (main checkout)."""
    with open(REPO_ROOT / "config" / "paths.yaml", encoding="utf-8") as fh:
        paths = yaml.safe_load(fh)
    return Path(paths["data_root"]), Path(paths["reports_root"])


DATA_ROOT, REPORTS_ROOT = _load_paths()
DATA_FILE = DATA_ROOT / "pkl" / "zh" / "all_months_staged.pkl"
REPORTS_DIR = REPORTS_ROOT / "audit"
PROPOSALS_CSV = REPORTS_DIR / "attribution_proposals.csv"


def main() -> None:
    df = pd.read_pickle(DATA_FILE)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)

    # the previous forensic run's proposals — read before the CSV is
    # overwritten, so the report can state each one's application status
    previous = None
    if PROPOSALS_CSV.exists():
        previous = pd.read_csv(PROPOSALS_CSV, keep_default_na=False)

    proposals, stats = build_proposals(df)
    write_reports(proposals, stats, df, REPORTS_DIR, previous=previous)

    total = stats["empty_supplier_amount"]
    print(f"rows: {stats['total_rows']}, empty supplier: "
          f"{stats['empty_supplier_rows']} (¥{total:,.2f}), "
          f"unclassified: {stats['unclassified_rows']}")
    for conf in ("high", "medium", "low"):
        c = stats["supplier_by_confidence"][conf]
        print(f"  {conf:>6}: {c['rows']:3d} lines  ¥{c['amount']:,.2f}")
    share = stats["recovered_medium_plus_share"] * 100
    print(f"medium+ recovery: ¥{stats['recovered_medium_plus_amount']:,.2f} "
          f"({share:.1f}% of empty-supplier amount; goal ≥50%)")
    print(f"stage proposals: {stats['stage_proposals']}")
    print(f"wrote {REPORTS_DIR / 'attribution_proposals.csv'}")
    print(f"wrote {REPORTS_DIR / 'attribution_report.md'}")


if __name__ == "__main__":
    main()
