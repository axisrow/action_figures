"""End-to-end pipeline verification (GH#9).

Runs all cross-checks (pkl vs manifest vs raw, zh/en parity, audit totals,
dashboard payload, git hygiene, qty×unit_price) against the real datasets,
prints a human-readable report, saves it to reports/verification.md and exits
0/1. Reports are gitignored and never committed.

Executive IA route checks (GH#31): every payload route reconciles against
its source CSVs (home stage cards vs stages×stage_summary, supplier pages
vs the supplier CSVs, optimization / benchmark detail pages vs their
reports), the Σ of the Home stage-menu cards equals the grand total, and
the route table is complete — every screen reachable, every link and
breadcrumb/back target resolving, no dead ends.

Usage: python3 scripts/verify.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from action_figures.verify_lib import FAIL, format_report, run_checks  # noqa: E402


def _default_roots() -> tuple[Path, Path]:
    """Data and report roots come from config/paths.yaml (main checkout)."""
    with open(REPO_ROOT / "config" / "paths.yaml", encoding="utf-8") as fh:
        paths = yaml.safe_load(fh)
    return Path(paths["data_root"]), Path(paths["reports_root"])


def main() -> int:
    data_root, reports_root = _default_roots()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=data_root)
    parser.add_argument("--reports-root", type=Path, default=reports_root)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--dist", type=Path, default=REPO_ROOT / "dashboard" / "dist" / "index.html"
    )
    args = parser.parse_args()

    results = run_checks(args.data_root, args.reports_root, args.repo_root, args.dist)
    report = format_report(results)
    print(report)

    out = args.reports_root / "verification.md"
    args.reports_root.mkdir(parents=True, exist_ok=True)
    out.write_text(report + "\n", encoding="utf-8")
    print(f"\nreport saved to {out}")

    return 1 if any(r.status == FAIL for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
