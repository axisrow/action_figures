"""End-to-end verification checks for the action_figures pipeline.

Each check reads only from disk (datasets, reports, git repo) and returns a
CheckResult — no check mutates anything. Pure helpers (sheet_anchor_total)
are kept side-effect free so they can be unit-tested on synthetic rows.

The independent raw recomputation deliberately does NOT reuse the ETL code:
for every raw sheet it rebuilds the sheet total from the sheet's own
totals/summary rows (总数 / 合计 / 月结 / 垫付 labels) plus any deposit-block
rows with a numeric 序号 below the last summary row, and compares that anchor
against data/manifest.json.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from action_figures.dashboard_data import NOT_BOOKED_STAGES

OK = "ok"
FAIL = "fail"
PENDING = "pending"

TOL = 0.01
# Rows where qty × unit_price deviates from amount by more than QTY_TOL are
# reported; the check fails only when they exceed this share of checked rows
# (real data has a small share of hand-entered inconsistencies).
MAX_MISMATCH_FRAC = 0.05

LABEL_KEYS = ("总数", "合计", "月结", "垫付")
FINANCIAL_EXTS = (".xls", ".xlsx", ".pkl")
DIRTY_PREFIXES = ("data/", "reports/", "issues/")


@dataclass
class CheckResult:
    name: str
    status: str
    summary: str = ""
    details: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# independent raw recomputation
# --------------------------------------------------------------------------


def _cell_float(value: object) -> float | None:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f


def sheet_anchor_total(rows: list) -> float | None:
    """Independent sheet total from row values (xlrd or openpyxl shapes).

    Rule (derived from the accounting layout, not from the ETL code):
    - locate the header row containing 序号 and 金额 (first 10 rows); None otherwise
    - rows whose cells contain a totals label (总数/合计/月结/垫付) carry a
      printed total; the grand total is the largest of them
    - rows with a numeric 序号 *below* the last totals row (deposit blocks
      added after the sheet was summed) are added on top
    - if a sheet has no totals row at all, the anchor is the sum of the 金额
      column over rows with a numeric 序号 (blank 金额 counts as 0)
    """
    header_idx = sn_col = amt_col = None
    for i, row in enumerate(rows[:10]):
        cells = [str(c).strip() if c is not None else "" for c in row]
        if "序号" in cells and "金额" in cells:
            header_idx = i
            sn_col = cells.index("序号")
            amt_col = cells.index("金额")
            break
    if header_idx is None or sn_col is None or amt_col is None:
        return None

    label_totals: list[float] = []
    last_label_idx = -1
    plain_total = 0.0
    for i, row in enumerate(rows[header_idx + 1 :], start=header_idx + 1):
        texts = [str(c).strip() for c in row if c is not None and str(c).strip()]
        # A totals row carries a label AND a blank 序号 (data rows always have
        # a numeric 序号 — even when their text mentions 月结/垫付).
        if _cell_float(row[sn_col]) is None and any(key in "".join(texts) for key in LABEL_KEYS):
            numerics = [f for c in row if (f := _cell_float(c)) is not None]
            if numerics:
                label_totals.append(max(numerics))
                last_label_idx = i
            continue
        if _cell_float(row[sn_col]) is not None:
            amt = _cell_float(row[amt_col]) if amt_col < len(row) else None
            plain_total += amt or 0.0

    if label_totals:
        tail = 0.0
        for row in rows[last_label_idx + 1 :]:
            if _cell_float(row[sn_col]) is not None:
                amt = _cell_float(row[amt_col]) if amt_col < len(row) else None
                tail += amt or 0.0
        return round(max(label_totals) + tail, 2)
    return round(plain_total, 2)


def read_raw_sheets(raw_dir: Path) -> list[tuple[str, str, list]]:
    """(filename, sheet_name, rows) for every xls/xlsx sheet in raw_dir."""
    import xlrd
    from openpyxl import load_workbook

    sheets: list[tuple[str, str, list]] = []
    for path in sorted(raw_dir.iterdir()):
        if path.suffix == ".xls":
            book = xlrd.open_workbook(str(path))
            for sheet in book.sheets():
                rows = [sheet.row_values(r) for r in range(sheet.nrows)]
                sheets.append((path.name, sheet.name, rows))
        elif path.suffix == ".xlsx":
            wb = load_workbook(path, read_only=True, data_only=True)
            for ws in wb.worksheets:
                sheets.append(
                    (path.name, ws.title, [list(r) for r in ws.iter_rows(values_only=True)])
                )
    return sheets


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------


def check_pkl_vs_manifest(data_root: Path) -> CheckResult:
    """(1) rows/Σamount: pkl == manifest == independent raw recomputation."""
    data_root = Path(data_root)
    manifest_path = data_root / "manifest.json"
    if not manifest_path.exists():
        return CheckResult("pkl_vs_manifest", PENDING, "data/manifest.json not found")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    outputs = manifest.get("outputs", {}).get("zh_pkl", {})
    if not outputs:
        return CheckResult("pkl_vs_manifest", FAIL, "manifest has no outputs.zh_pkl")

    details: list[str] = []
    ok = True
    for name, expected in sorted(outputs.items()):
        path = data_root / "pkl" / "zh" / name
        if not path.exists():
            ok = False
            details.append(f"{name}: pkl file missing")
            continue
        df = pd.read_pickle(path)
        got = (len(df), round(float(df["amount"].sum()), 2))
        exp = (int(expected["rows"]), round(float(expected["sum_amount"]), 2))
        if got != exp:
            ok = False
            details.append(f"{name}: pkl rows/sum {got} != manifest {exp}")

    # month roll-up: Σamount of every month in the all_months pkl == Σ of raw
    # sheets tagged with that month in the manifest (2026 months legitimately
    # merge two sources; row counts may shrink via dedup — sums must not).
    sources = manifest.get("sources", {})
    sheet_month_totals: dict[str, float] = {}
    _sheet_rows: dict[str, int] = {}
    for _src, info in sources.items():
        for meta in info.get("sheets", {}).values():
            if meta.get("skipped") or not meta.get("month"):
                continue
            month = meta["month"]
            sheet_month_totals[month] = sheet_month_totals.get(month, 0.0) + float(
                meta["sum_amount"]
            )
            _sheet_rows[month] = _sheet_rows.get(month, 0) + int(meta.get("rows", 0))
    allm_path = data_root / "pkl" / "zh" / "all_months.pkl"
    if sources and allm_path.exists():
        allm_df = pd.read_pickle(allm_path)
        pkl_months = allm_df.groupby("month")["amount"].agg(["count", "sum"])
        for month in sorted(set(pkl_months.index) | set(sheet_month_totals)):
            raw_total = round(sheet_month_totals.get(month, 0.0), 2)
            pkl_total = (
                round(float(pkl_months.loc[month, "sum"]), 2) if month in pkl_months.index else 0.0
            )
            if month not in pkl_months.index or month not in sheet_month_totals:
                ok = False
                details.append(
                    f"{month}: present only on one side (pkl {pkl_total} / raw {raw_total})"
                )
                continue
            if abs(pkl_total - raw_total) > TOL:
                ok = False
                details.append(
                    f"{month}: all_months Σamount {pkl_total} != Σ raw sheets {raw_total}"
                )
            pkl_rows = int(pkl_months.loc[month, "count"])
            if pkl_rows != _sheet_rows.get(month):
                details.append(
                    f"{month}: row count pkl {pkl_rows} vs raw sheets {_sheet_rows.get(month)} "
                    "(dedup/merge note)"
                )

    # independent anchor: raw sheet totals vs manifest sheet sums
    raw_dir = data_root / "raw"
    if raw_dir.exists():
        manifest_sheets: dict[tuple[str, str], float] = {}
        for src, info in manifest.get("sources", {}).items():
            for sheet, meta in info.get("sheets", {}).items():
                if not meta.get("skipped"):
                    manifest_sheets[(src, sheet.strip())] = round(float(meta["sum_amount"]), 2)
        for fname, sheet, rows in read_raw_sheets(raw_dir):
            key = (fname, sheet.strip())
            if key not in manifest_sheets:
                continue
            anchor = sheet_anchor_total(rows)
            if anchor is None:
                details.append(f"{fname}:{sheet}: no header — anchor crosscheck skipped")
            elif abs(anchor - manifest_sheets[key]) > TOL:
                ok = False
                details.append(
                    f"{fname}:{sheet}: raw anchor {anchor} != manifest {manifest_sheets[key]}"
                )

    allm_meta = outputs.get("all_months.pkl", {})
    return CheckResult(
        "pkl_vs_manifest",
        OK if ok else FAIL,
        f"{len(outputs)} pkl files vs manifest: "
        f"all_months = {int(allm_meta.get('rows', 0))} rows / "
        f"{float(allm_meta.get('sum_amount', 0.0)):.2f} CNY; "
        "every raw sheet total independently re-anchored",
        details,
    )


def check_zh_en_parity(data_root: Path) -> CheckResult:
    """(2) zh/en: same line_id sets and Σamount per month and overall."""
    data_root = Path(data_root)
    details: list[str] = []
    ok = True
    missing_twins = 0
    seen_any = False
    zh_dir = data_root / "pkl" / "zh"
    if not zh_dir.exists():
        return CheckResult("zh_en_parity", PENDING, "no data/pkl/zh directory")
    for zh_path in sorted(zh_dir.glob("*.pkl")):
        en_path = data_root / "pkl" / "en" / zh_path.name
        if not en_path.exists():
            missing_twins += 1
            details.append(f"{zh_path.name}: no en twin")
            continue
        seen_any = True
        zh = pd.read_pickle(zh_path)
        en = pd.read_pickle(en_path)
        zh_ids, en_ids = sorted(zh["line_id"]), sorted(en["line_id"])
        if zh_ids != en_ids:
            ok = False
            missing = set(zh_ids) - set(en_ids)
            extra = set(en_ids) - set(zh_ids)
            details.append(
                f"{zh_path.name}: line_id sets differ (zh-only {len(missing)}, en-only {len(extra)})"
            )
        zh_sum = round(float(zh["amount"].sum()), 2)
        en_sum = round(float(en["amount"].sum()), 2)
        if abs(zh_sum - en_sum) > TOL:
            ok = False
            details.append(f"{zh_path.name}: Σamount zh {zh_sum} != en {en_sum}")
    if not seen_any:
        return CheckResult("zh_en_parity", PENDING, "no en pkl files found", details)
    if ok and missing_twins:
        return CheckResult(
            "zh_en_parity",
            PENDING,
            f"{missing_twins} of {missing_twins + seen_any} files lack an en twin",
            details,
        )
    return CheckResult(
        "zh_en_parity", OK if ok else FAIL, "zh/en line_id sets and Σamount match", details
    )


def _pkl_total(data_root: Path) -> tuple[int, float] | None:
    path = Path(data_root) / "pkl" / "zh" / "all_months.pkl"
    if not path.exists():
        return None
    df = pd.read_pickle(path)
    return len(df), round(float(df["amount"].sum()), 2)


def check_audit_totals(reports_root: Path, data_root: Path, tol: float = TOL) -> CheckResult:
    """(3) Σ stage_summary, by_supplier_stage and by_day_stage == pkl Σamount (± tol)."""
    reports_root = Path(reports_root)
    details: list[str] = []
    ok = True
    pkl = _pkl_total(data_root)
    if pkl is None:
        return CheckResult("audit_totals", PENDING, "no zh all_months.pkl")
    n_lines, total = pkl
    checked_any = False
    for csv_name, _cols in (
        ("stage_summary.csv", ("amount_cny", "n_lines")),
        ("by_supplier_stage.csv", ("amount_cny", "n_lines")),
        ("by_day_stage.csv", ("amount_cny", "n_lines")),
    ):
        path = reports_root / "audit" / csv_name
        if not path.exists():
            details.append(f"{csv_name}: missing — skipped")
            continue
        checked_any = True
        df = pd.read_csv(path)
        csv_total = round(float(df["amount_cny"].sum()), 2)
        csv_lines = int(df["n_lines"].sum())
        if abs(csv_total - total) > tol:
            ok = False
            details.append(f"{csv_name}: Σamount {csv_total} != pkl {total} (±{tol})")
        if csv_lines != n_lines:
            ok = False
            details.append(f"{csv_name}: Σn_lines {csv_lines} != pkl rows {n_lines}")
    if not checked_any:
        return CheckResult("audit_totals", PENDING, "no audit CSVs found", details)
    return CheckResult(
        "audit_totals",
        OK if ok else FAIL,
        f"Σ(stage_summary) == Σ(by_supplier_stage) == Σ(by_day_stage) == "
        f"Σ(amount) == {total:.2f} CNY / {n_lines} rows",
        details,
    )


def check_stage_totals(reports_root: Path, tol: float = TOL) -> CheckResult:
    """(3b) per-stage Σ(by_day_stage) == stage_summary (amounts ± tol, n_lines)."""
    reports_root = Path(reports_root)
    day_path = reports_root / "audit" / "by_day_stage.csv"
    sum_path = reports_root / "audit" / "stage_summary.csv"
    if not day_path.exists() or not sum_path.exists():
        return CheckResult(
            "stage_totals", PENDING, "by_day_stage.csv / stage_summary.csv missing"
        )
    by_day = pd.read_csv(day_path)
    summary = pd.read_csv(sum_path)
    per_stage = by_day.groupby("stage").agg(
        n_lines=("n_lines", "sum"), amount_cny=("amount_cny", "sum")
    ).to_dict("index")
    details: list[str] = []
    ok = True
    for r in summary.itertuples():
        if r.stage not in per_stage:
            ok = False
            details.append(f"{r.stage}: missing from by_day_stage.csv")
            continue
        got_amount = round(float(per_stage[r.stage]["amount_cny"]), 2)
        got_lines = int(per_stage[r.stage]["n_lines"])
        if abs(got_amount - float(r.amount_cny)) > tol:
            ok = False
            details.append(f"{r.stage}: Σ by_day {got_amount} != stage_summary {float(r.amount_cny)}")
        if got_lines != int(r.n_lines):
            ok = False
            details.append(f"{r.stage}: n_lines {got_lines} != stage_summary {int(r.n_lines)}")
    extra = sorted(set(per_stage) - set(summary["stage"]))
    if extra:
        ok = False
        details.append(f"stages missing from stage_summary: {', '.join(extra)}")
    return CheckResult(
        "stage_totals",
        OK if ok else FAIL,
        f"per-stage Σ(by_day_stage) == stage_summary ({len(summary)} stages, ±{tol})",
        details,
    )


DASH_JSON_RE = re.compile(
    r'<script id="dash-data" type="application/json">(.*?)</script>', re.DOTALL
)


def check_dashboard_payload(dist_html: Path, reports_root: Path, tol: float = TOL) -> CheckResult:
    """(4) JSON embedded in dist/index.html == reports CSVs (post-regeneration)."""
    dist_html = Path(dist_html)
    summary_path = Path(reports_root) / "audit" / "stage_summary.csv"
    payload, error = _load_dash_payload(dist_html)
    if payload is None:
        status = PENDING if not dist_html.exists() else FAIL
        return CheckResult("dashboard_payload", status, error)
    if not summary_path.exists():
        return CheckResult("dashboard_payload", PENDING, "no reports/audit/stage_summary.csv")
    csv_rows = pd.read_csv(summary_path)
    csv_map = {
        r["stage"]: (int(r["n_lines"]), round(float(r["amount_cny"]), 2))
        for _, r in csv_rows.iterrows()
    }
    payload_map = {
        r["stage"]: (int(r["n_lines"]), round(float(r["amount_cny"]), 2))
        for r in payload.get("cost_structure", {}).get("stages", [])
    }
    details: list[str] = []
    ok = True
    for stage in sorted(set(csv_map) | set(payload_map)):
        if csv_map.get(stage) != payload_map.get(stage):
            ok = False
            details.append(f"{stage}: dist {payload_map.get(stage)} != csv {csv_map.get(stage)}")
    return CheckResult(
        "dashboard_payload",
        OK if ok else FAIL,
        f"embedded cost_structure == stage_summary.csv ({len(csv_map)} stages)",
        details,
    )


def _load_dash_payload(dist_html: Path) -> tuple[dict | None, str]:
    """Embedded dash-data JSON from dist/index.html -> (payload, error)."""
    dist_html = Path(dist_html)
    if not dist_html.exists():
        return None, f"{dist_html} not built yet — regenerate dist and re-run verify"
    match = DASH_JSON_RE.search(dist_html.read_text(encoding="utf-8"))
    if not match:
        return None, "dash-data script tag not found in dist/index.html"
    return json.loads(match.group(1).replace("\\u003c", "<")), ""


def _norm_style(value: object) -> str:
    """'9052.0' -> '9052' (float-string style numbers from the audit)."""
    s = ("" if value is None else str(value)).strip().strip('"')
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


STAGE_PAGE_TOP_N = 10
UNATTRIBUTED_LABEL = "Unattributed"


def _series_matches(got: list, expected: list, tol: float) -> bool:
    """Same (key, amount) pairs in the same order, amounts within tol —
    every per-stage series (months/days/styles/suppliers) uses the same
    tolerance, so a 1-cent float artifact fails nowhere or everywhere."""
    return len(got) == len(expected) and all(
        g[0] == e[0] and abs(g[1] - e[1]) <= tol
        for g, e in zip(got, expected, strict=True)
    )


def check_stage_pages(dist_html: Path, reports_root: Path, tol: float = TOL) -> CheckResult:
    """(4b) payload.stage_pages == CSV filters (by_month/by_day/style/supplier).

    For every stage of the payload's stage menu the embedded page must carry
    exactly the CSV-derived series: monthly/daily spend (non-zero rows,
    sorted), top-10 styles, top-10 suppliers (+ blank-supplier bucket as
    Unattributed, pinned last), and stats (total/share/n_lines) matching
    stage_summary. Also: Σ page totals == the stage_summary grand total, and
    the not_booked plate flag matches the GH#16 forensic verdict stages.
    """
    payload, error = _load_dash_payload(dist_html)
    if payload is None:
        return CheckResult("stage_pages", PENDING, error)
    reports_root = Path(reports_root)
    csv_names = (
        "stage_summary.csv",
        "by_month_stage.csv",
        "by_day_stage.csv",
        "by_style_stage.csv",
        "by_supplier_stage.csv",
    )
    missing = [n for n in csv_names if not (reports_root / "audit" / n).exists()]
    if missing:
        return CheckResult(
            "stage_pages", PENDING, f"missing CSVs: {', '.join(missing)}"
        )
    summary_path = reports_root / "audit" / "stage_summary.csv"
    summary = pd.read_csv(summary_path)
    by_month = pd.read_csv(reports_root / "audit" / "by_month_stage.csv")
    # keep_default_na=False: a blank date stays '' so the drop below is an
    # explicit guard, not an implicit groupby NaN-drop — mirrors the builder's
    # own blank-date filter (dashboard_data.build_stage_pages)
    by_day = pd.read_csv(reports_root / "audit" / "by_day_stage.csv", keep_default_na=False)
    by_style = pd.read_csv(reports_root / "audit" / "by_style_stage.csv")
    by_supplier = pd.read_csv(
        reports_root / "audit" / "by_supplier_stage.csv", keep_default_na=False
    )

    menu = payload.get("stages") or []
    pages = payload.get("stage_pages")
    if pages is None:
        return CheckResult("stage_pages", FAIL, "payload has no stage_pages section")
    summary_map = {
        r["stage"]: (int(r["n_lines"]), float(r["amount_cny"]), float(r["share_pct"]))
        for _, r in summary.iterrows()
    }

    details: list[str] = []
    ok = True
    for meta in menu:
        sid = meta["stage_id"]
        page = pages.get(sid)
        if page is None:
            ok = False
            details.append(f"{sid}: missing from payload.stage_pages")
            continue

        expected_months = list(
            by_month[(by_month["stage"] == sid) & (by_month["amount_cny"] != 0)]
            .groupby("month")["amount_cny"].sum().round(2).items()
        )
        got_months = [(m["month"], round(float(m["amount_cny"]), 2))
                      for m in page.get("months") or []]
        if not _series_matches(got_months, expected_months, tol):
            ok = False
            details.append(f"{sid}: months != by_month_stage.csv filter")

        day_rows = by_day[(by_day["stage"] == sid) & (by_day["amount_cny"] != 0)]
        day_rows = day_rows[day_rows["date"].astype(str).str.strip() != ""]
        expected_days = list(day_rows.groupby("date")["amount_cny"].sum().round(2).items())
        got_days = [(d["date"], round(float(d["amount_cny"]), 2))
                    for d in page.get("days") or []]
        if not _series_matches(got_days, expected_days, tol):
            ok = False
            details.append(f"{sid}: days != by_day_stage.csv filter")

        style_rows = by_style[(by_style["stage"] == sid) & (by_style["amount_cny"] != 0)]
        style_rows = style_rows[style_rows["style_no"].astype(str).str.strip() != ""]
        style_agg = {
            _norm_style(s): round(float(a), 2)
            for s, a in style_rows.groupby("style_no")["amount_cny"].sum().items()
        }
        expected_styles = sorted(style_agg.items(), key=lambda t: (-t[1], t[0]))[:STAGE_PAGE_TOP_N]
        got_styles = sorted(
            ((r["style_no"], round(float(r["amount_cny"]), 2))
             for r in page.get("top_styles") or []),
            key=lambda t: (-t[1], t[0]),
        )
        if not _series_matches(got_styles, expected_styles, tol):
            ok = False
            details.append(f"{sid}: top_styles != by_style_stage.csv filter")

        stage_suppliers = by_supplier[by_supplier["stage"] == sid]
        named = sorted(
            (
                (str(r["supplier"]).strip(), round(float(r["amount_cny"]), 2))
                for _, r in stage_suppliers.iterrows()
                if str(r["supplier"]).strip()
            ),
            key=lambda t: (-t[1], t[0]),
        )
        unattr = [
            round(float(a), 2)
            for s, a in stage_suppliers.groupby("supplier")["amount_cny"].sum().items()
            if not str(s).strip()
        ]
        expected_amounts = [a for _n, a in named[:STAGE_PAGE_TOP_N]] + unattr
        got_suppliers = page.get("top_suppliers") or []
        got_amounts = [round(float(r["amount_cny"]), 2) for r in got_suppliers]
        supplier_ok = len(got_amounts) == len(expected_amounts) and all(
            abs(g - e) <= tol
            for g, e in zip(got_amounts, expected_amounts, strict=True)
        )
        # labels: named rows keep the raw zh name inside 'EN (zh)'; the blank
        # bucket is exactly 'Unattributed' and must sit last
        if supplier_ok and named:
            top_names = [n for n, _a in named[:STAGE_PAGE_TOP_N]]
            for row, name in zip(got_suppliers, top_names, strict=False):
                if name not in row["supplier"]:
                    supplier_ok = False
                    details.append(
                        f"{sid}: top_suppliers label {row['supplier']!r} lost the "
                        f"raw supplier name {name!r}"
                    )
        if supplier_ok and unattr:
            if not got_suppliers or got_suppliers[-1]["supplier"] != UNATTRIBUTED_LABEL:
                supplier_ok = False
                details.append(f"{sid}: Unattributed bucket not pinned last")
        if not supplier_ok:
            ok = False
            details.append(f"{sid}: top_suppliers != by_supplier_stage.csv filter")

        n_lines, amount, share = summary_map.get(sid, (0, 0.0, 0.0))
        stats = page.get("stats") or {}
        stats_ok = (
            abs(float(stats.get("total_cny", -1)) - amount) <= tol
            and abs(float(stats.get("share_pct", -1)) - share) <= 0.05
            and int(stats.get("n_lines", -1)) == n_lines
        )
        if not stats_ok:
            ok = False
            details.append(f"{sid}: stats != stage_summary.csv row")

        if bool(page.get("not_booked")) != (sid in NOT_BOOKED_STAGES):
            ok = False
            details.append(f"{sid}: not_booked flag != forensic verdict")

    grand_total = round(float(summary["amount_cny"].sum()), 2)
    pages_total = round(
        sum(float((pages.get(m["stage_id"]) or {}).get("stats", {}).get("total_cny", 0.0))
            for m in menu),
        2,
    )
    if abs(pages_total - grand_total) > tol:
        ok = False
        details.append(
            f"Σ stage_pages totals {pages_total} != grand total {grand_total}"
        )

    extra = sorted(set(pages) - {m["stage_id"] for m in menu})
    if extra:
        ok = False
        details.append(f"stage_pages has stages outside the menu: {', '.join(extra)}")

    return CheckResult(
        "stage_pages",
        OK if ok else FAIL,
        f"stage_pages == CSV filters for {len(menu)} stages "
        f"(months/days/styles/suppliers/stats); Σ pages == grand total {grand_total:.2f}",
        details,
    )


def check_ideal_timeline(dist_html: Path) -> CheckResult:
    """(4c) payload.ideal_timeline: bars exist, every source url/file non-empty."""
    payload, error = _load_dash_payload(dist_html)
    if payload is None:
        return CheckResult("ideal_timeline", PENDING, error)
    it = payload.get("ideal_timeline")
    if not it or not it.get("bars"):
        return CheckResult("ideal_timeline", FAIL, "payload has no ideal_timeline bars")
    details: list[str] = []
    ok = True
    for b in it["bars"]:
        label = b.get("label", "?")
        if not str(b.get("source_url", "")).startswith("http"):
            ok = False
            details.append(f"{label}: source_url missing/not http")
        if not str(b.get("source_file", "")).strip():
            ok = False
            details.append(f"{label}: source_file empty")
    return CheckResult(
        "ideal_timeline",
        OK if ok else FAIL,
        f"ideal_timeline: {len(it['bars'])} bars, all sources non-empty",
        details,
    )


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, text=True)


def _is_financial_path(path: str) -> bool:
    # tests/fixtures/*.xls(x) are committed on purpose: SYNTHETIC data only
    if path.startswith("tests/fixtures/"):
        return False
    return path.endswith(FINANCIAL_EXTS) or path.startswith(DIRTY_PREFIXES)


def check_git_hygiene(repo_root: Path) -> CheckResult:
    """(5) status clean of data/reports/issues; check-ignore; clean history."""
    repo_root = Path(repo_root)
    if _git(repo_root, "rev-parse", "--git-dir").returncode != 0:
        return CheckResult("git_hygiene", PENDING, f"{repo_root} is not a git repository")

    details: list[str] = []
    ok = True

    status = _git(repo_root, "status", "--porcelain").stdout
    dirty = [
        line[3:].split(" -> ")[-1]
        for line in status.splitlines()
        if _is_financial_path(line[3:].split(" -> ")[-1])
    ]
    if dirty:
        ok = False
        details.append(f"git status not clean: {', '.join(sorted(dirty))}")

    probe_paths = [
        "data/pkl/zh/all_months.pkl",
        "data/manifest.json",
        "data/raw/synthetic.xlsx",
        "reports/audit/stage_summary.csv",
        "reports/verification.md",
        "issues/000-epic.md",
    ]
    not_ignored = [
        p for p in probe_paths if _git(repo_root, "check-ignore", "-q", p).returncode != 0
    ]
    if not_ignored:
        ok = False
        details.append(f"git check-ignore misses: {', '.join(not_ignored)}")

    history = _git(repo_root, "log", "--all", "--name-only", "--pretty=format:")
    leaked = sorted(
        {
            line.strip()
            for line in history.stdout.splitlines()
            if line.strip() and _is_financial_path(line.strip())
        }
    )
    if leaked:
        ok = False
        details.append(f"financial/data paths in git history: {', '.join(leaked[:20])}")

    return CheckResult(
        "git_hygiene",
        OK if ok else FAIL,
        "status clean of data/reports/issues; ignores verified; history free of "
        "xls/xlsx/pkl/data paths",
        details,
    )


def check_qty_amount(
    data_root: Path, tol: float = 0.01, max_mismatch_frac: float = MAX_MISMATCH_FRAC
) -> CheckResult:
    """(6) qty × unit_price ≈ amount (± tol), with a mismatch report."""
    pkl = Path(data_root) / "pkl" / "zh" / "all_months.pkl"
    if not pkl.exists():
        return CheckResult("qty_amount", PENDING, "no zh all_months.pkl")
    df = pd.read_pickle(pkl)
    usable = df.dropna(subset=["qty", "unit_price", "amount"])
    usable = usable[(usable["qty"] != 0) & (usable["unit_price"] != 0) & (usable["amount"] != 0)]
    skipped = len(df) - len(usable)
    if usable.empty:
        return CheckResult("qty_amount", PENDING, "no rows with qty/unit_price/amount")
    calc = usable["qty"] * usable["unit_price"]
    dev = (calc - usable["amount"]).abs() / usable["amount"].abs()
    bad = usable[dev > tol]
    frac = len(bad) / len(usable)
    details = [
        f"{r.line_id}: qty={r.qty:g} × unit_price={r.unit_price:g} != amount={r.amount:g} "
        f"(dev {dev.loc[r.Index]:.1%})"
        for r in bad.head(10).itertuples()
    ]
    if len(bad) > 10:
        details.append(f"... and {len(bad) - 10} more")
    if skipped:
        details.append(f"{skipped} rows skipped (missing/zero qty, unit_price or amount)")
    status = OK if frac <= max_mismatch_frac else FAIL
    return CheckResult(
        "qty_amount",
        status,
        f"{len(bad)}/{len(usable)} rows deviate > {tol:.0%} (threshold {max_mismatch_frac:.0%})",
        details,
    )


# --------------------------------------------------------------------------
# runner / report
# --------------------------------------------------------------------------


def run_checks(
    data_root: Path, reports_root: Path, repo_root: Path, dist_html: Path
) -> list[CheckResult]:
    return [
        check_pkl_vs_manifest(data_root),
        check_zh_en_parity(data_root),
        check_audit_totals(reports_root, data_root),
        check_stage_totals(reports_root),
        check_dashboard_payload(dist_html, reports_root),
        check_stage_pages(dist_html, reports_root),
        check_ideal_timeline(dist_html),
        check_git_hygiene(repo_root),
        check_qty_amount(data_root),
    ]


STATUS_MARK = {OK: "PASS", FAIL: "FAIL", PENDING: "PENDING"}


def format_report(results: list[CheckResult]) -> str:
    lines = ["# Pipeline verification report", ""]
    for res in results:
        lines.append(f"## [{STATUS_MARK.get(res.status, res.status.upper())}] {res.name}")
        lines.append("")
        lines.append(res.summary or "-")
        if res.details:
            lines.append("")
            lines.extend(f"- {d}" for d in res.details)
        lines.append("")
    failed = sum(r.status == FAIL for r in results)
    verdict = "FAILED" if failed else "PASSED (pending checks excluded)"
    lines.append(f"**Overall: {verdict}** — {failed} failing of {len(results)} checks")
    return "\n".join(lines)
