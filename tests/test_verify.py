"""Verify-lib checks: 100% synthetic data (same policy as conftest)."""

from __future__ import annotations

import json

import pandas as pd
from conftest import git, init_repo

from action_figures.verify_lib import (
    check_audit_totals,
    check_dashboard_payload,
    check_git_hygiene,
    check_pkl_vs_manifest,
    check_qty_amount,
    check_zh_en_parity,
    format_report,
    run_checks,
    sheet_anchor_total,
)

ZHEADER = [
    "序号",
    "日期",
    "款号",
    "报销事项",
    "单位",
    "数量",
    "单价",
    "金额",
    "用途",
    "供应商",
    "备注",
]


def make_frame(rows, prefix="syn", month="2026-01"):
    """rows: (qty, unit_price, amount) -> zh frame with stable line_ids."""
    data = []
    for i, (qty, price, amount) in enumerate(rows, start=1):
        data.append(
            {
                "line_id": f"{prefix}-{i:03d}",
                "month": month,
                "qty": qty,
                "unit_price": price,
                "amount": amount,
                "item": f"合成{i}",
            }
        )
    return pd.DataFrame(data)


def write_dataset(tmp_path, months=("2026-01", "2026-02")):
    """Synthetic dataset: manifest + zh/en monthly pkls + all_months, consistent."""
    amounts = {
        "2026-01": [(2, 10.0, 20.0), (3, 5.0, 15.0)],
        "2026-02": [(1, 7.5, 7.5), (4, 2.0, 8.0), (10, 1.0, 10.0)],
    }
    manifest = {"generated_at": "2026-01-01T00:00:00+00:00", "sources": {}, "outputs": {}}
    frames = {}
    for lang in ("zh", "en"):
        (tmp_path / "pkl" / lang).mkdir(parents=True)
    for month in months:
        rows = amounts[month]
        zh = make_frame(rows, prefix=month, month=month)
        en = make_frame(rows, prefix=month, month=month).assign(item="synthetic")
        zh.to_pickle(tmp_path / "pkl" / "zh" / f"{month}.pkl")
        en.to_pickle(tmp_path / "pkl" / "en" / f"{month}.pkl")
        frames[month] = zh
        manifest["outputs"].setdefault("zh_pkl", {})[f"{month}.pkl"] = {
            "rows": len(zh),
            "sum_amount": round(zh["amount"].sum(), 2),
        }
    allm = pd.concat([frames[m] for m in months], ignore_index=True)
    allm.to_pickle(tmp_path / "pkl" / "zh" / "all_months.pkl")
    allm.assign(item="synthetic").to_pickle(tmp_path / "pkl" / "en" / "all_months.pkl")
    manifest["outputs"]["zh_pkl"]["all_months.pkl"] = {
        "rows": len(allm),
        "sum_amount": round(allm["amount"].sum(), 2),
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest, amounts


def write_stage_summary(path, stages, total_extra=0.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "stage": s,
            "n_lines": n,
            "amount_cny": round(a + total_extra / len(stages), 2),
            "share_pct": 10.0,
        }
        for s, n, a in stages
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


# ---------------------------------------------------------------- anchor ----


class TestSheetAnchorTotal:
    def test_plain_sheet_no_label_row(self):
        rows = [
            ZHEADER,
            [1, 46000, "UD1", "事项", "个", 2, 10, 20, "", "", ""],
            [2, 46001, "UD1", "事项", "个", 3, 5, 15, "", "", ""],
        ]
        assert sheet_anchor_total(rows) == 35.0

    def test_totals_label_row_ignored_but_matched(self):
        rows = [
            ZHEADER,
            [1, 46000, "UD1", "事项", "个", 2, 10, 20, "", "", ""],
            ["", "", "", "", "", "", "总数：", 20.0, "", "", ""],
        ]
        assert sheet_anchor_total(rows) == 20.0

    def test_second_block_below_label_counted(self):
        """Rows with numeric 序号 below the totals row join the anchor (deposit block)."""
        rows = [
            ZHEADER,
            [1, 46000, "UD1", "事项", "个", 2, 10, 20, "", "", ""],
            ["", "", "", "", "", "", "总数：", 20.0, "", "", ""],
            [2, 46001, "UD1", "定金", "批", 1, 100, 100, "", "", ""],
        ]
        assert sheet_anchor_total(rows) == 120.0

    def test_two_label_rows_takes_max(self):
        """月结款汇总 + 垫付+月结: the grand-total (max) label wins."""
        rows = [
            ZHEADER,
            [1, 46000, "UD1", "月结", "个", 1, 60, 60, "", "", ""],
            ["", "", "", "", "", "月结款汇总：", "", 60.0, "", "", ""],
            ["", "", "", "", "", "垫付+月结：", "", 200.0, "", "", ""],
        ]
        assert sheet_anchor_total(rows) == 200.0

    def test_empty_amount_counts_zero(self):
        rows = [
            ZHEADER,
            [1, 46000, "UD1", "订金", "", "", 500, "", "", "", ""],
            [2, 46000, "UD1", "事项", "", 1, 5, 5, "", "", ""],
            ["", "", "", "", "", "", "总数：", 5.0, "", "", ""],
        ]
        assert sheet_anchor_total(rows) == 5.0

    def test_no_header_returns_none(self):
        assert sheet_anchor_total([["别的东西"], ["x"]]) is None


# ------------------------------------------------------------ pkl/manifest ---


class TestPklVsManifest:
    def test_consistent_dataset_ok(self, tmp_path):
        write_dataset(tmp_path)
        res = check_pkl_vs_manifest(tmp_path)
        assert res.status == "ok", res.details

    def test_manifest_sum_drift_fails(self, tmp_path):
        write_dataset(tmp_path)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        manifest["outputs"]["zh_pkl"]["2026-01.pkl"]["sum_amount"] = 999.0
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        res = check_pkl_vs_manifest(tmp_path)
        assert res.status == "fail"
        assert any("2026-01" in d for d in res.details)

    def test_row_count_drift_fails(self, tmp_path):
        write_dataset(tmp_path)
        df = pd.read_pickle(tmp_path / "pkl" / "zh" / "2026-02.pkl")
        df.iloc[:1].to_pickle(tmp_path / "pkl" / "zh" / "2026-02.pkl")
        res = check_pkl_vs_manifest(tmp_path)
        assert res.status == "fail"

    def test_all_months_must_equal_sum_of_monthly(self, tmp_path):
        write_dataset(tmp_path)
        df = pd.read_pickle(tmp_path / "pkl" / "zh" / "all_months.pkl")
        df.iloc[:-1].to_pickle(tmp_path / "pkl" / "zh" / "all_months.pkl")
        res = check_pkl_vs_manifest(tmp_path)
        assert res.status == "fail"

    def test_raw_xlsx_anchor_crosscheck(self, tmp_path):
        """manifest sheet sums vs an independent totals-row recomputation from raw."""
        write_dataset(tmp_path)
        raw = tmp_path / "raw"
        raw.mkdir()
        body = [
            [1, 46000, "UD1", "事项", "个", 2, 10, 20, "", "", ""],
            [2, 46001, "UD1", "事项", "个", 3, 5, 15, "", "", ""],
        ]
        frame = pd.DataFrame(body, columns=ZHEADER)
        with pd.ExcelWriter(raw / "syn.xlsx", engine="openpyxl") as xl:
            frame.to_excel(xl, sheet_name="1月份", index=False, startrow=1)
            sheet = xl.book["1月份"]
            sheet["A1"] = "费用报销明细"
            sheet["G6"] = "总数："
            sheet["H6"] = 35.0
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        manifest["sources"]["syn.xlsx"] = {
            "sheets": {
                "1月份": {"month": "2026-01", "rows": 2, "sum_amount": 35.0, "skipped": None},
                # 2026-02 has no raw sheet on disk: only the roll-up uses it
                "2月份": {"month": "2026-02", "rows": 3, "sum_amount": 25.5, "skipped": None},
            }
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        res = check_pkl_vs_manifest(tmp_path)
        assert res.status == "ok", res.details

    def test_raw_anchor_mismatch_fails(self, tmp_path):
        write_dataset(tmp_path)
        raw = tmp_path / "raw"
        raw.mkdir()
        body = [[1, 46000, "UD1", "事项", "个", 2, 10, 20, "", "", ""]]
        frame = pd.DataFrame(body, columns=ZHEADER)
        with pd.ExcelWriter(raw / "syn.xlsx", engine="openpyxl") as xl:
            frame.to_excel(xl, sheet_name="1月份", index=False, header=False, startrow=1)
            sheet = xl.book["1月份"]
            sheet["A1"] = "费用报销明细"
            sheet["G4"] = "总数："
            sheet["H4"] = 777.0
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        manifest["sources"]["syn.xlsx"] = {
            "sheets": {
                "1月份": {"month": "2026-01", "rows": 1, "sum_amount": 20.0, "skipped": None}
            }
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        res = check_pkl_vs_manifest(tmp_path)
        assert res.status == "fail"


# ------------------------------------------------------------------ parity ---


class TestZhEnParity:
    def test_parity_ok(self, tmp_path):
        write_dataset(tmp_path)
        assert check_zh_en_parity(tmp_path).status == "ok"

    def test_amount_drift_fails(self, tmp_path):
        write_dataset(tmp_path)
        df = pd.read_pickle(tmp_path / "pkl" / "en" / "2026-01.pkl")
        df.loc[0, "amount"] = 999.0
        df.to_pickle(tmp_path / "pkl" / "en" / "2026-01.pkl")
        res = check_zh_en_parity(tmp_path)
        assert res.status == "fail"

    def test_missing_line_id_fails(self, tmp_path):
        write_dataset(tmp_path)
        df = pd.read_pickle(tmp_path / "pkl" / "en" / "all_months.pkl")
        df.iloc[1:].to_pickle(tmp_path / "pkl" / "en" / "all_months.pkl")
        res = check_zh_en_parity(tmp_path)
        assert res.status == "fail"

    def test_missing_en_pkl_pending(self, tmp_path):
        write_dataset(tmp_path)
        (tmp_path / "pkl" / "en" / "2026-01.pkl").unlink()
        res = check_zh_en_parity(tmp_path)
        assert res.status == "pending"


# ------------------------------------------------------------ audit totals ---


class TestAuditTotals:
    def test_totals_match_pkl(self, tmp_path):
        write_dataset(tmp_path)
        # 2026-01: 2 lines 35.0; 2026-02: 3 lines 25.5
        write_stage_summary(
            tmp_path / "reports" / "audit" / "stage_summary.csv",
            [("tooling_molds", 3, 30.0), ("packaging", 2, 30.5)],
        )
        pd.DataFrame(
            [
                {"supplier": "甲", "stage": "tooling_molds", "amount_cny": 30.0, "n_lines": 3},
                {"supplier": "乙", "stage": "packaging", "amount_cny": 30.5, "n_lines": 2},
            ]
        ).to_csv(tmp_path / "reports" / "audit" / "by_supplier_stage.csv", index=False)
        res = check_audit_totals(tmp_path / "reports", tmp_path)
        assert res.status == "ok", res.details

    def test_drift_beyond_tolerance_fails(self, tmp_path):
        write_dataset(tmp_path)
        write_stage_summary(
            tmp_path / "reports" / "audit" / "stage_summary.csv", [("tooling_molds", 5, 70.5)]
        )
        res = check_audit_totals(tmp_path / "reports", tmp_path)
        assert res.status == "fail"

    def test_missing_reports_pending(self, tmp_path):
        write_dataset(tmp_path)
        res = check_audit_totals(tmp_path / "reports", tmp_path)
        assert res.status == "pending"


# --------------------------------------------------------------- dashboard ---


class TestDashboardPayload:
    def _reports(self, tmp_path):
        write_stage_summary(
            tmp_path / "reports" / "audit" / "stage_summary.csv",
            [("tooling_molds", 3, 30.0), ("packaging", 2, 5.5)],
        )

    def test_missing_dist_pending(self, tmp_path):
        self._reports(tmp_path)
        res = check_dashboard_payload(tmp_path / "dist" / "index.html", tmp_path / "reports")
        assert res.status == "pending"

    def test_payload_matching_csv_ok(self, tmp_path):
        self._reports(tmp_path)
        payload = {
            "cost_structure": {
                "stages": [
                    {"stage": "tooling_molds", "n_lines": 3, "amount_cny": 30.0},
                    {"stage": "packaging", "n_lines": 2, "amount_cny": 5.5},
                ]
            }
        }
        dist = tmp_path / "dist"
        dist.mkdir()
        html = (
            '<html><script id="dash-data" type="application/json">'
            + json.dumps(payload)
            + "</script></html>"
        )
        (dist / "index.html").write_text(html, encoding="utf-8")
        res = check_dashboard_payload(dist / "index.html", tmp_path / "reports")
        assert res.status == "ok", res.details

    def test_stale_payload_fails(self, tmp_path):
        self._reports(tmp_path)
        payload = {
            "cost_structure": {
                "stages": [
                    {"stage": "tooling_molds", "n_lines": 3, "amount_cny": 999.0},
                ]
            }
        }
        dist = tmp_path / "dist"
        dist.mkdir()
        html = (
            '<html><script id="dash-data" type="application/json">'
            + json.dumps(payload)
            + "</script></html>"
        )
        (dist / "index.html").write_text(html, encoding="utf-8")
        res = check_dashboard_payload(dist / "index.html", tmp_path / "reports")
        assert res.status == "fail"


# --------------------------------------------------------------------- git ---


class TestGitHygiene:
    def test_clean_repo_ok(self, tmp_path):
        repo = init_repo(tmp_path)
        res = check_git_hygiene(repo)
        assert res.status == "ok", res.details

    def test_untracked_data_file_fails(self, tmp_path):
        """A data file visible in status (broken .gitignore) must fail the check."""
        repo = init_repo(tmp_path)
        (repo / ".gitignore").write_text("")  # simulate a broken ignore setup
        (repo / "data").mkdir()
        (repo / "data" / "2026-01.pkl").write_bytes(b"x")
        res = check_git_hygiene(repo)
        assert res.status == "fail"

    def test_untracked_report_fails(self, tmp_path):
        repo = init_repo(tmp_path)
        (repo / ".gitignore").write_text("")
        (repo / "reports").mkdir()
        (repo / "reports" / "stage_summary.csv").write_text("stage,amount\n")
        res = check_git_hygiene(repo)
        assert res.status == "fail"

    def test_financial_file_in_history_fails(self, tmp_path):
        repo = init_repo(tmp_path)
        (repo / "leak.pkl").write_bytes(b"x")
        git(repo, "add", "-f", "leak.pkl")
        git(repo, "commit", "-q", "-m", "leak")
        git(repo, "rm", "-q", "--cached", "leak.pkl")
        git(repo, "commit", "-q", "-m", "unleak")
        res = check_git_hygiene(repo)
        assert res.status == "fail"
        assert any("leak.pkl" in d for d in res.details)

    def test_data_path_in_history_fails(self, tmp_path):
        repo = init_repo(tmp_path)
        (repo / "data").mkdir()
        (repo / "data" / "notes.txt").write_text("x")
        git(repo, "add", "-f", "data/notes.txt")
        git(repo, "commit", "-q", "-m", "data leak")
        res = check_git_hygiene(repo)
        assert res.status == "fail"

    def test_not_a_repo_pending(self, tmp_path):
        res = check_git_hygiene(tmp_path)
        assert res.status == "pending"


# --------------------------------------------------------------- qty×price ---


class TestQtyAmount:
    def test_consistent_ok(self, tmp_path):
        write_dataset(tmp_path)
        assert check_qty_amount(tmp_path).status == "ok"

    def test_small_minority_reported_not_fatal(self, tmp_path):
        write_dataset(tmp_path)
        df = pd.read_pickle(tmp_path / "pkl" / "zh" / "all_months.pkl")
        df.loc[0, "amount"] = 12345.0  # 1 of 5 rows off
        df.to_pickle(tmp_path / "pkl" / "zh" / "all_months.pkl")
        res = check_qty_amount(tmp_path, max_mismatch_frac=0.5)
        assert res.status == "ok"
        assert res.details

    def test_widespread_mismatch_fails(self, tmp_path):
        write_dataset(tmp_path)
        df = pd.read_pickle(tmp_path / "pkl" / "zh" / "all_months.pkl")
        df["amount"] = 999.0
        df.to_pickle(tmp_path / "pkl" / "zh" / "all_months.pkl")
        res = check_qty_amount(tmp_path)
        assert res.status == "fail"

    def test_missing_dataset_pending(self, tmp_path):
        assert check_qty_amount(tmp_path).status == "pending"


# ------------------------------------------------------------------ runner ---


class TestRunChecksAndReport:
    def test_exit_code_zero_when_ok_or_pending(self, tmp_path):
        write_dataset(tmp_path)
        repo = init_repo(tmp_path)
        results = run_checks(tmp_path, tmp_path / "reports", repo, tmp_path / "dist" / "index.html")
        statuses = {r.status for r in results}
        assert statuses <= {"ok", "pending"}
        report = format_report(results)
        assert "PASS" in report and "PENDING" in report

    def test_exit_reported_on_failure(self, tmp_path):
        write_dataset(tmp_path)
        df = pd.read_pickle(tmp_path / "pkl" / "zh" / "2026-01.pkl")
        df.loc[0, "amount"] = 1.0
        df.to_pickle(tmp_path / "pkl" / "zh" / "2026-01.pkl")
        repo = init_repo(tmp_path)
        results = run_checks(tmp_path, tmp_path / "reports", repo, tmp_path / "dist" / "index.html")
        assert any(r.status == "fail" for r in results)
        assert "FAIL" in format_report(results)
