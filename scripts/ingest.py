#!/usr/bin/env python3
"""Ingest: xls/xlsx → data/pkl/zh/*.pkl + data/manifest.json.

Оба исходника переносятся из корня проекта в data/raw/ (gitignored),
каждый лист конвертируется в каноническую схему, май дедуплицируется
(xlsx 5月份 — канон, xls 2026-05月 дозаполняет пропуски).

Запуск: python3 scripts/ingest.py            # пути из config/paths.yaml
        python3 scripts/ingest.py --check    # только сверка pkl vs исходники
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from action_figures.excel_io import get_datemode, list_sheets, read_sheet  # noqa: E402
from action_figures.schema import (  # noqa: E402
    COLUMNS,
    HEADER_MAP,
    detect_header_row,
    freight_collect,
    is_service_row,
    merge_month_dfs,
    month_from_sheetname,
    parse_date,
)

ROOT = Path(__file__).resolve().parent.parent
YEAR_RE = re.compile(r"(20\d{2})")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _num(value):
    """Число из ячейки: строка с запятыми/пробелами тоже парсится; иначе NaN."""
    if value is None or value == "":
        return float("nan")
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace(",", "").replace("，", "").strip()
    try:
        return float(s)
    except ValueError:
        return float("nan")


def sheet_to_df(path: Path, sheet: str) -> tuple[pd.DataFrame, dict]:
    """Лист → DataFrame канонической схемы + статистика чтения."""
    rows, engine = read_sheet(path, sheet)
    datemode = get_datemode(path)
    h = detect_header_row(rows)
    if h is None:
        return pd.DataFrame(columns=COLUMNS), {"skipped": "шапка 序号/日期/金额 не найдена", "engine": engine}
    header = [str(v).strip() if v is not None else "" for v in rows[h]]
    col_of = {en: header.index(zh) for zh, en in HEADER_MAP.items() if zh in header}

    def cell(row: list, name: str):
        idx = col_of.get(name)
        return row[idx] if idx is not None and idx < len(row) else None

    records, coerce_errors, service_dropped = [], 0, 0
    for i, row in enumerate(rows[h + 1:], start=h + 2):  # 1-based номер строки листа
        if all(v is None or v == "" for v in row):
            continue
        if is_service_row({f: cell(row, f) for f in ("qty", "unit_price", "amount")}):
            service_dropped += 1  # итоги 总数：/采购垫付：/月结款汇总： и повторные шапки
            continue
        raw_date = cell(row, "date")
        rec = {
            "date": parse_date(raw_date, datemode=datemode),
            "date_raw": "" if raw_date is None else str(raw_date),
            "style_no": cell(row, "style_no"),
            "batch": cell(row, "batch"),
            "item": cell(row, "item"),
            "qty": _num(cell(row, "qty")),
            "unit": cell(row, "unit"),
            "unit_price": _num(cell(row, "unit_price")),
            "amount": _num(cell(row, "amount")),
            "purpose": cell(row, "purpose"),
            "supplier": cell(row, "supplier"),
            "remarks": cell(row, "remarks"),
            "freight_collect": freight_collect(cell(row, "item")),
            "source_file": path.name,
            "source_sheet": sheet,
            "row_idx": i,
        }
        for f in ("qty", "unit_price", "amount"):
            v = cell(row, f)
            if v not in (None, "") and pd.isna(rec[f]):
                coerce_errors += 1
        records.append(rec)
    df = pd.DataFrame(records, columns=[c for c in COLUMNS if c not in ("line_id", "month")])
    df.insert(0, "month", [month_from_sheetname(sheet, year_hint=_year_hint(path))] * len(df))
    df.insert(0, "line_id", [
        hashlib.sha1(f"{path.name}|{sheet}|{r}".encode()).hexdigest()[:16]
        for r in df["row_idx"]
    ])
    return df, {"engine": engine, "coerce_errors": coerce_errors,
                "service_rows_dropped": service_dropped}


def _year_hint(path: Path) -> int | None:
    m = YEAR_RE.search(path.stem)
    return int(m.group(1)) if m else None


def build_sheets_table(raw_dir: Path) -> dict:
    """Прочитать оба сырья: {файл: {лист: (df, meta)}}."""
    table = {}
    for path in sorted(raw_dir.iterdir()):
        if path.suffix.lower() not in (".xls", ".xlsx"):
            continue
        sheets = {}
        for sheet in list_sheets(path):
            df, meta = sheet_to_df(path, sheet)
            if "skipped" not in meta:
                meta["month"] = month_from_sheetname(sheet, year_hint=_year_hint(path))
            sheets[sheet] = (df, meta)
        table[path.name] = sheets
    return table


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="только сверка pkl vs исходники")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
    raw_dir, pkl_dir = Path(cfg["raw_dir"]), Path(cfg["pkl_dir"])
    pkl_dir.mkdir(parents=True, exist_ok=True)
    zh_dir, manifest_path = Path(cfg["zh_pkl_dir"]), Path(cfg["manifest"])

    # 1. перенос сырья в data/raw/
    if not args.check:
        raw_dir.mkdir(parents=True, exist_ok=True)
        for src in cfg["sources"]:
            src_path = Path(src)
            if not src_path.exists():
                print(f"ИСТОЧНИК НЕДОСТУПЕН: {src}", file=sys.stderr)
                return 2
            dest = raw_dir / src_path.name
            if not dest.exists():
                shutil.copy2(src_path, dest)
            print(f"raw: {dest} ({dest.stat().st_size} bytes)")

    table = build_sheets_table(raw_dir)
    if args.check:
        return check(manifest_path, zh_dir, table)

    # 2. pkl по месяцам 2026-01..2026-06 (канон — xlsx)
    zh_dir.mkdir(parents=True, exist_ok=True)
    xlsx_name = next(n for n in table if n.endswith(".xlsx"))
    xls_name = next(n for n in table if n.endswith(".xls"))
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sources": {},
        "dedup_may": None,
        "outputs": {"zh_pkl": {}, "note": "2026-05 — merged (xlsx канон + xls уникальные)"},
    }
    for fname, sheets in table.items():
        manifest["sources"][fname] = {"sha256": sha256_of(raw_dir / fname)}
        for sheet, (df, meta) in sheets.items():
            m = dict(meta)
            m["rows"] = int(len(df))
            m["sum_amount"] = round(float(df["amount"].sum(skipna=True)), 2) if len(df) else 0.0
            if "skipped" not in meta:
                m["skipped"] = None
            manifest["sources"][fname].setdefault("sheets", {})[sheet] = m

    month_dfs: dict[str, pd.DataFrame] = {}
    for _sheet, (df, meta) in table[xlsx_name].items():
        if "skipped" in meta or meta.get("month") is None:
            continue
        month_dfs[meta["month"]] = df

    # 3. дедуп мая: xls 2026-05月 raw-pkl + merge
    may_xls_sheet = next(
        (s for s, (df, m) in table[xls_name].items() if m.get("month") == "2026-05"), None
    )
    if may_xls_sheet and "2026-05" in month_dfs:
        xls_may = table[xls_name][may_xls_sheet][0]
        xls_may.to_pickle(zh_dir / "2026-05_xls_raw.pkl")
        merged, stats = merge_month_dfs(month_dfs["2026-05"], xls_may)
        month_dfs["2026-05"] = merged
        manifest["dedup_may"] = {
            "key": "date±1d + style_no + item + qty + amount",
            "canonical": f"{xlsx_name}::5月份",
            "xls_sheet": may_xls_sheet,
            **stats,
        }

    all_parts = []
    for month in sorted(month_dfs):
        month_dfs[month].to_pickle(zh_dir / f"{month}.pkl")
        manifest["outputs"]["zh_pkl"][f"{month}.pkl"] = {
            "rows": int(len(month_dfs[month])),
            "sum_amount": round(float(month_dfs[month]["amount"].sum(skipna=True)), 2),
        }
        all_parts.append(month_dfs[month])
    # прочие листы xls (2025-*) идут только в all_months
    for _sheet, (df, meta) in table[xls_name].items():
        if "skipped" in meta or meta.get("month") in (None, "2026-05"):
            continue
        all_parts.append(df)
    all_df = pd.concat(all_parts, ignore_index=True) if all_parts else pd.DataFrame(columns=COLUMNS)
    all_df.to_pickle(zh_dir / "all_months.pkl")
    manifest["outputs"]["zh_pkl"]["all_months.pkl"] = {
        "rows": int(len(all_df)),
        "sum_amount": round(float(all_df["amount"].sum(skipna=True)), 2),
    }

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"manifest: {manifest_path}")
    return check(manifest_path, zh_dir, table)


def check(manifest_path: Path, zh_dir: Path, table: dict) -> int:
    """Сверка строк и Σamount каждого pkl против свежепрочитанного исходника."""
    print("\n=== сверка pkl vs исходники ===")
    print(f"{'лист':<28} {'src_rows':>8} {'pkl_rows':>8} {'Δrows':>5} "
          f"{'Σsrc':>12} {'Σpkl':>12} {'ΔΣ':>9}")
    ok = True
    for fname, sheets in table.items():
        for sheet, (df, meta) in sheets.items():
            if "skipped" in meta:
                print(f"{fname}::{sheet:<24} SKIP: {meta['skipped']}")
                continue
            month = meta.get("month")
            if month is None:
                print(f"{fname}::{sheet:<24} SKIP: месяц листа не определён")
                continue
            pkl = None
            if fname.endswith(".xlsx"):
                pkl = _load(zh_dir / f"{month}.pkl")
                pkl = pkl[pkl["source_sheet"] == sheet]
            else:
                raw = _load(zh_dir / "2026-05_xls_raw.pkl")
                if sheet == "2026-05月":
                    pkl = raw
                else:
                    allm = _load(zh_dir / "all_months.pkl")
                    pkl = allm[allm["source_sheet"] == sheet]
            if pkl is None:
                print(f"{fname}::{sheet}: pkl не найден")
                ok = False
                continue
            s_rows, p_rows = len(df), len(pkl)
            s_sum = round(float(df["amount"].sum(skipna=True)), 2)
            p_sum = round(float(pkl["amount"].sum(skipna=True)), 2)
            d_rows, d_sum = p_rows - s_rows, round(p_sum - s_sum, 2)
            mark = "OK" if d_rows == 0 and abs(d_sum) < 0.01 else "!!"
            if mark == "!!":
                ok = False
            print(f"{sheet:<28} {s_rows:>8} {p_rows:>8} {d_rows:>5} "
                  f"{s_sum:>12.2f} {p_sum:>12.2f} {d_sum:>9.2f} {mark}")
    merged = _load(zh_dir / "2026-05.pkl")
    print(f"\n2026-05 после дедупа: rows={len(merged)}, Σamount={merged['amount'].sum(skipna=True):.2f}")
    print("ИТОГ:", "СВЕРКА СХОДИТСЯ" if ok else "ЕСТЬ РАСХОЖДЕНИЯ")
    return 0 if ok else 1


def _load(path: Path) -> pd.DataFrame:
    return pd.read_pickle(path)


if __name__ == "__main__":
    raise SystemExit(main())
