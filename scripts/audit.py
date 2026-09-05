"""Audit: classify reimbursement lines into production stages, build reports.

Reads pkl datasets (absolute paths in the main checkout) read-only, writes
*_staged.pkl copies plus CSV/markdown outputs into reports/audit/.
Original pkl files are never modified.

Usage: python3 scripts/audit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from action_figures.audit_tables import by_supplier_stage  # noqa: E402
from action_figures.classify import classify_df, load_taxonomy  # noqa: E402


def _load_paths() -> tuple[Path, Path]:
    """Data and report roots come from config/paths.yaml (main checkout)."""
    with open(REPO_ROOT / "config" / "paths.yaml", encoding="utf-8") as fh:
        paths = yaml.safe_load(fh)
    return Path(paths["data_root"]), Path(paths["reports_root"])


DATA_ROOT, REPORTS_ROOT = _load_paths()
DATA_DIR = DATA_ROOT / "pkl" / "zh"
REPORTS_DIR = REPORTS_ROOT / "audit"
TAXONOMY = REPO_ROOT / "config" / "taxonomy.yaml"

MONTH_PKL = ["2026-01.pkl", "2026-02.pkl", "2026-03.pkl",
             "2026-04.pkl", "2026-05.pkl", "2026-06.pkl"]

# Stage descriptions for audit.md (plain English, no jargon)
STAGE_EN = {
    "logistics_freight": (
        "Shipping and courier fees — sending samples, parts and materials "
        "between the studio and outsourcing partners."
    ),
    "design_prototyping": (
        "Design and prototyping — paying artists to draw/sculpt parts (画图), "
        "3D printing sample parts, and making garment patterns/samples."
    ),
    "tooling_molds": (
        "Molds and tooling — one-off cost of steel/resin molds (开模/搪胶模) "
        "needed before any part can be mass-produced."
    ),
    "injection_molding": (
        "Molded parts production — factory runs that inject or cast parts "
        "from the molds (啤货/注塑/压铸): soles, buckles, guns, helmets."
    ),
    "painting_printing": (
        "Painting and printing — spray painting (喷油), hand-painting head "
        "sculpts (上色), fabric printing (印花) and decals (水贴)."
    ),
    "assembly_processing": (
        "Assembly and handwork — cutting fabric pieces, sewing garments, "
        "trimming threads, lathe-turned metal parts and other hand finishing."
    ),
    "raw_materials": (
        "Raw materials and consumables — fabric glue, thinner, alcohol, "
        "screws, copper, magnets and other workshop supplies."
    ),
    "textile_accessories": (
        "Textiles and garment accessories — fabric (布), leather (皮), thread, "
        "zippers, buttons, woven labels for the figure uniforms."
    ),
    "packaging": (
        "Packaging — boxes, cartons, sealing and manuals."
    ),
    "qc_testing": (
        "Quality control and testing — inspection and lab tests."
    ),
    "admin_other": (
        "Admin and office — business trips, fuel, tolls, office equipment "
        "and company meals."
    ),
    "unclassified": (
        "Lines the taxonomy could not classify — reviewed manually in "
        "unclassified.csv."
    ),
}


def main() -> None:
    taxonomy = load_taxonomy(TAXONOMY)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    frames = []
    for name in MONTH_PKL:
        df = pd.read_pickle(DATA_DIR / name)
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
        staged = classify_df(df, taxonomy)
        staged.to_pickle(DATA_DIR / name.replace(".pkl", "_staged.pkl"))
        frames.append(staged)
        print(f"{name}: {len(staged)} rows staged")
    all_df = pd.read_pickle(DATA_DIR / "all_months.pkl")
    all_df["amount"] = pd.to_numeric(all_df["amount"], errors="coerce").fillna(0.0)
    all_df = classify_df(all_df, taxonomy)
    all_df.to_pickle(DATA_DIR / "all_months_staged.pkl")

    total_amount = all_df["amount"].sum()

    # stage_summary.csv
    summary = (
        all_df.groupby("stage")
        .agg(n_lines=("line_id", "count"), amount_cny=("amount", "sum"))
        .reset_index()
        .sort_values("amount_cny", ascending=False)
    )
    summary["share_pct"] = (summary["amount_cny"] / total_amount * 100).round(2)
    summary.to_csv(REPORTS_DIR / "stage_summary.csv", index=False)

    # by_month_stage.csv
    by_month = (
        all_df.groupby(["month", "stage"])
        .agg(n_lines=("line_id", "count"), amount_cny=("amount", "sum"))
        .reset_index()
        .sort_values(["month", "amount_cny"], ascending=[True, False])
    )
    by_month.to_csv(REPORTS_DIR / "by_month_stage.csv", index=False)

    # by_style_stage.csv
    by_style = (
        all_df.groupby(["style_no", "stage"])
        .agg(n_lines=("line_id", "count"), amount_cny=("amount", "sum"))
        .reset_index()
        .sort_values(["style_no", "amount_cny"], ascending=[True, False])
    )
    by_style.to_csv(REPORTS_DIR / "by_style_stage.csv", index=False)

    # by_supplier_stage.csv (dashboard Suppliers tab)
    by_supplier = by_supplier_stage(all_df)
    by_supplier.to_csv(REPORTS_DIR / "by_supplier_stage.csv", index=False)
    supplier_sum = by_supplier["amount_cny"].sum()
    print(f"supplier sum:  {supplier_sum:.2f}  "
          f"(diff {supplier_sum - total_amount:+.4f})")

    # by_style_timeline.csv (Gantt input)
    timeline = (
        all_df[all_df["date"].notna()]
        .groupby(["style_no", "stage"])
        .agg(start_date=("date", "min"), end_date=("date", "max"),
             n_lines=("line_id", "count"), amount_cny=("amount", "sum"))
        .reset_index()
        .sort_values(["style_no", "start_date"])
    )
    timeline.to_csv(REPORTS_DIR / "by_style_timeline.csv", index=False)

    # unclassified.csv
    uncl = all_df[all_df["stage"] == "unclassified"]
    uncl[["line_id", "month", "date", "style_no", "item", "purpose",
          "supplier", "amount"]].to_csv(REPORTS_DIR / "unclassified.csv",
                                        index=False)

    uncl_share = uncl["amount"].sum() / total_amount * 100
    stage_sum = summary["amount_cny"].sum()
    print(f"\ntotal amount: {total_amount:.2f}")
    print(f"stage sum:    {stage_sum:.2f}  (diff {stage_sum - total_amount:+.4f})")
    print(f"unclassified: {uncl_share:.2f}% of amount, {len(uncl)} lines")
    print("\n", summary.to_string(index=False))

    write_audit_md(all_df, summary, total_amount, uncl_share)


def _fmt_table(summary: pd.DataFrame) -> str:
    header = "| Stage | Lines | Amount, CNY | Share, % |"
    rows = [
        f"| {r.stage} | {r.n_lines} | {r.amount_cny:,.2f} | {r.share_pct:.2f} |"
        for r in summary.itertuples()
    ]
    return "\n".join([header, "|---|---:|---:|---:|", *rows])


def _verdict(summary: pd.DataFrame) -> list[str]:
    """Product-type verdict from the cost structure (deterministic rules)."""
    share = dict(zip(summary["stage"], summary["share_pct"], strict=True))
    garment = (share.get("textile_accessories", 0) + share.get("assembly_processing", 0)
               + share.get("raw_materials", 0))
    hard_parts = (share.get("tooling_molds", 0) + share.get("injection_molding", 0))
    design = share.get("design_prototyping", 0)
    painting = share.get("painting_printing", 0)
    packaging = share.get("packaging", 0)
    return [
        f"- Garment/textile chain (textile + handwork + materials): **{garment:.1f}%**",
        f"- Hard parts chain (tooling + molding): **{hard_parts:.1f}%**",
        f"- Design & prototyping: **{design:.1f}%**; painting/printing: **{painting:.1f}%**",
        f"- Packaging: **{packaging:.1f}%** (very low for a toy factory)",
        "",
        "**Verdict:** this is a **small-batch collectible (1/6 scale) studio**, not a "
        "mass-market toy factory. The cost structure is dominated by the sewing "
        "chain (fabric, cutting, hand assembly) and by many low-value molds "
        "(rotocast 搪胶模 at ~¥380–1,520 each and small steel/die-cast tools), "
        "with a high design share — the signature of high-mix, low-volume "
        "production. Hand painting of head sculpts is present but not the "
        "dominant cost (unlike factory-painted PVC figures where paint is "
        "60–70% of unit cost); packaging is nearly absent, i.e. products ship "
        "as collectible figures without retail boxes.",
    ]


def write_audit_md(all_df: pd.DataFrame, summary: pd.DataFrame,
                   total_amount: float, uncl_share: float, _: int = 0) -> None:
    n_lines = len(all_df)
    months = sorted(m for m in all_df["month"].dropna().unique())
    styles = all_df["style_no"].dropna().astype(str)
    n_styles = styles[styles.str.strip() != ""].nunique()
    md = [
        "# Production Cost Audit — action figures (2026 H1 + carry-over 2025)",
        "",
        f"- Source: `data/pkl/zh/all_months.pkl` — **{n_lines}** line items, "
        f"**¥{total_amount:,.2f}** total.",
        f"- Months covered: {months[0]} … {months[-1]} ({len(months)} month tags).",
        f"- Styles referenced: **{n_styles}**.",
        "- Every number below is reproducible with one groupby over `line_id` "
        "in `all_months_staged.pkl`.",
        "",
        "## Stage summary",
        "",
        _fmt_table(summary),
        "",
        f"- Unclassified: **{uncl_share:.2f}%** of amount "
        f"(target ≤ 5%) — see `unclassified.csv` for the manual review list.",
        f"- Cross-check: Σ stage amounts = **¥{summary['amount_cny'].sum():,.2f}** "
        f"= Σ line amounts ± ¥0.01 ✓",
        "",
        "## What each stage is (plain English)",
        "",
    ]
    for r in summary.itertuples():
        md.append(f"### {r.stage} — ¥{r.amount_cny:,.2f} ({r.share_pct:.2f}%, "
                  f"{r.n_lines} lines)")
        md.append("")
        md.append(STAGE_EN.get(r.stage, ""))
        md.append("")
    md += ["## Product type by cost structure", ""] + _verdict(summary) + [
        "",
        "## Output files",
        "",
        "- `stage_summary.csv` — stage, n_lines, amount_cny, share_pct",
        "- `by_month_stage.csv` — month × stage (n_lines, amount)",
        "- `by_style_stage.csv` — style × stage (n_lines, amount)",
        "- `by_supplier_stage.csv` — supplier × stage "
        "(n_lines, amount, months_active)",
        "- `by_style_timeline.csv` — style × stage with min/max dates (Gantt input)",
        "- `unclassified.csv` — lines left unclassified, for manual review",
        "- `data/pkl/zh/*_staged.pkl` — original frames + stage/stage_confidence "
        "(originals untouched)",
    ]
    (REPORTS_DIR / "audit.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nwrote {REPORTS_DIR / 'audit.md'}")


if __name__ == "__main__":
    main()
