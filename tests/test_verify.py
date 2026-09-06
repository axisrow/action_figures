"""Verify-lib checks: 100% synthetic data (same policy as conftest)."""

from __future__ import annotations

import json
from urllib.parse import quote

import pandas as pd
from conftest import git, init_repo

from action_figures.dashboard_data import (
    IA_TABS,
    build_benchmark_pages,
    load_benchmarks_md,
    load_optimizations_md,
)
from action_figures.verify_lib import (
    check_audit_totals,
    check_benchmark_pages,
    check_dashboard_payload,
    check_git_hygiene,
    check_home_reconciles,
    check_ideal_timeline,
    check_optimization_pages,
    check_pkl_vs_manifest,
    check_qty_amount,
    check_routes_complete,
    check_stage_pages,
    check_supplier_pages,
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


# ------------------------------------------------------- stage pages (PE-5) ---


def write_stage_page_reports(tmp_path):
    """Synthetic reports + matching payload for the two-stage Process Explorer.

    Stages: design_prototyping (regular) and packaging (GH#16 not-booked
    plate). All numbers invented; share_pct follows round(amount/total,1).
    """
    audit = tmp_path / "reports" / "audit"
    audit.mkdir(parents=True)
    pd.DataFrame(
        [
            {"stage": "design_prototyping", "n_lines": 2, "amount_cny": 30.0,
             "share_pct": 60.0},
            {"stage": "packaging", "n_lines": 2, "amount_cny": 20.0,
             "share_pct": 40.0},
        ]
    ).to_csv(audit / "stage_summary.csv", index=False)
    pd.DataFrame(
        [
            {"month": "2026-01", "stage": "design_prototyping", "n_lines": 1,
             "amount_cny": 20.0},
            {"month": "2026-02", "stage": "design_prototyping", "n_lines": 1,
             "amount_cny": 10.0},
            {"month": "2026-01", "stage": "packaging", "n_lines": 2,
             "amount_cny": 20.0},
        ]
    ).to_csv(audit / "by_month_stage.csv", index=False)
    pd.DataFrame(
        [
            {"date": "2026-01-05", "stage": "design_prototyping",
             "amount_cny": 12.0, "n_lines": 1},
            {"date": "2026-01-20", "stage": "design_prototyping",
             "amount_cny": 8.0, "n_lines": 1},
            {"date": "2026-02-01", "stage": "packaging", "amount_cny": 20.0,
             "n_lines": 2},
        ]
    ).to_csv(audit / "by_day_stage.csv", index=False)
    pd.DataFrame(
        [
            {"style_no": "AF-1", "stage": "design_prototyping", "n_lines": 1,
             "amount_cny": 18.0},
            {"style_no": "AF-2", "stage": "design_prototyping", "n_lines": 1,
             "amount_cny": 12.0},
            {"style_no": "AF-1", "stage": "packaging", "n_lines": 2,
             "amount_cny": 20.0},
        ]
    ).to_csv(audit / "by_style_stage.csv", index=False)
    # real aggregated format; blank supplier = Unattributed
    pd.DataFrame(
        [
            {"supplier": "杭州宏达", "stage": "design_prototyping",
             "amount_cny": 20.0, "n_lines": 1, "months_active": "2026-01"},
            {"supplier": "东莞精密", "stage": "design_prototyping",
             "amount_cny": 10.0, "n_lines": 1, "months_active": "2026-02"},
            {"supplier": "", "stage": "packaging", "amount_cny": 20.0,
             "n_lines": 2, "months_active": "2026-01"},
        ]
    ).to_csv(audit / "by_supplier_stage.csv", index=False)
    pd.DataFrame(
        [
            {"supplier": "杭州宏达", "month": "2026-01", "amount_cny": 20.0},
            # duplicate (supplier, month) rows exist in the real export:
            # the builder sums them, the check must mirror that
            {"supplier": "杭州宏达", "month": "2026-01", "amount_cny": 5.0},
            {"supplier": "东莞精密", "month": "2026-02", "amount_cny": 10.0},
            {"supplier": "", "month": "2026-01", "amount_cny": 20.0},
        ]
    ).to_csv(audit / "by_supplier_month.csv", index=False)
    pd.DataFrame(
        [
            {"supplier": "杭州宏达", "style_no": "AF-1", "amount_cny": 18.0,
             "n_lines": 1},
            {"supplier": "东莞精密", "style_no": "AF-2", "amount_cny": 12.0,
             "n_lines": 1},
            {"supplier": "", "style_no": "AF-1", "amount_cny": 20.0,
             "n_lines": 2},
        ]
    ).to_csv(audit / "by_supplier_style.csv", index=False)
    pd.DataFrame(
        [
            {"stage_id": "design_prototyping", "order": 1, "label_en": "Design",
             "description_en": "d", "zh_keys": "设计"},
            {"stage_id": "packaging", "order": 8, "label_en": "Packaging",
             "description_en": "p", "zh_keys": "包装"},
        ]
    ).to_csv(audit / "stages.csv", index=False)
    return stage_pages_payload()


def stage_pages_payload():
    return {
        "stages": [
            {"stage_id": "design_prototyping", "order": 1, "label_en": "Design",
             "description_en": "d", "zh_keys": ["设计"], "service": False,
             "amount_cny": 30.0, "share_pct": 60.0, "n_lines": 2},
            {"stage_id": "packaging", "order": 8, "label_en": "Packaging",
             "description_en": "p", "zh_keys": ["包装"], "service": False,
             "amount_cny": 20.0, "share_pct": 40.0, "n_lines": 2},
        ],
        "stage_pages": {
            "design_prototyping": {
                "not_booked": False,
                "months": [{"month": "2026-01", "amount_cny": 20.0},
                           {"month": "2026-02", "amount_cny": 10.0}],
                "days": [{"date": "2026-01-05", "amount_cny": 12.0},
                         {"date": "2026-01-20", "amount_cny": 8.0}],
                "top_suppliers": [
                    {"supplier": "Hangzhou Hongda (杭州宏达)", "amount_cny": 20.0,
                     "share_pct": 66.7},
                    {"supplier": "东莞精密", "amount_cny": 10.0,
                     "share_pct": 33.3},
                ],
                "top_styles": [
                    {"style_no": "AF-1", "amount_cny": 18.0, "share_pct": 60.0},
                    {"style_no": "AF-2", "amount_cny": 12.0, "share_pct": 40.0},
                ],
                "stats": {"total_cny": 30.0, "share_pct": 60.0, "n_lines": 2,
                          "avg_line_cny": 15.0},
            },
            "packaging": {
                "not_booked": True,
                "months": [{"month": "2026-01", "amount_cny": 20.0}],
                "days": [{"date": "2026-02-01", "amount_cny": 20.0}],
                "top_suppliers": [
                    {"supplier": "Unattributed", "amount_cny": 20.0,
                     "share_pct": 100.0},
                ],
                "top_styles": [
                    {"style_no": "AF-1", "amount_cny": 20.0, "share_pct": 100.0},
                ],
                "stats": {"total_cny": 20.0, "share_pct": 40.0, "n_lines": 2,
                          "avg_line_cny": 10.0},
            },
        },
        "ideal_timeline": {
            "weeks_axis": [0, 26],
            "total_weeks": [4, 8],
            "disclaimer": "synthetic",
            "rows": [{"row": 0, "stage_id": "design_prototyping",
                      "label": "Design"}],
            "bars": [
                {"stage_id": "design_prototyping", "label": "Design",
                 "variant": "", "row": 0, "parallel": False, "start_week": 0,
                 "min_end_week": 4, "max_start_week": 0, "end_week": 8,
                 "min_weeks": 4, "max_weeks": 8,
                 "source_file": "design_bench.md",
                 "source_url": "https://example.com/design"},
            ],
        },
    }


def write_dist(tmp_path, payload):
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text(
        '<html><script id="dash-data" type="application/json">'
        + json.dumps(payload) + "</script></html>",
        encoding="utf-8",
    )
    return dist / "index.html"


class TestStagePages:
    def test_matching_payload_ok(self, tmp_path):
        write_stage_page_reports(tmp_path)
        dist = write_dist(tmp_path, stage_pages_payload())
        res = check_stage_pages(dist, tmp_path / "reports")
        assert res.status == "ok", res.details

    def test_missing_dist_pending(self, tmp_path):
        write_stage_page_reports(tmp_path)
        res = check_stage_pages(tmp_path / "dist" / "index.html", tmp_path / "reports")
        assert res.status == "pending"

    def test_missing_reports_pending(self, tmp_path):
        payload = stage_pages_payload()
        dist = write_dist(tmp_path, payload)
        res = check_stage_pages(dist, tmp_path / "reports")
        assert res.status == "pending"

    def test_no_stage_pages_section_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = stage_pages_payload()
        del payload["stage_pages"]
        res = check_stage_pages(write_dist(tmp_path, payload), tmp_path / "reports")
        assert res.status == "fail"

    def test_month_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = stage_pages_payload()
        payload["stage_pages"]["design_prototyping"]["months"][0]["amount_cny"] = 99.0
        res = check_stage_pages(write_dist(tmp_path, payload), tmp_path / "reports")
        assert res.status == "fail"
        assert any("months" in d for d in res.details)

    def test_day_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = stage_pages_payload()
        payload["stage_pages"]["packaging"]["days"] = []
        res = check_stage_pages(write_dist(tmp_path, payload), tmp_path / "reports")
        assert res.status == "fail"
        assert any("days" in d for d in res.details)

    def test_supplier_amount_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = stage_pages_payload()
        payload["stage_pages"]["design_prototyping"]["top_suppliers"][0]["amount_cny"] = 5.0
        res = check_stage_pages(write_dist(tmp_path, payload), tmp_path / "reports")
        assert res.status == "fail"
        assert any("top_suppliers" in d for d in res.details)

    def test_style_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = stage_pages_payload()
        payload["stage_pages"]["design_prototyping"]["top_styles"] = []
        res = check_stage_pages(write_dist(tmp_path, payload), tmp_path / "reports")
        assert res.status == "fail"
        assert any("top_styles" in d for d in res.details)

    def test_grand_total_mismatch_fails(self, tmp_path):
        """Σ page totals must equal the stage_summary grand total."""
        write_stage_page_reports(tmp_path)
        payload = stage_pages_payload()
        payload["stage_pages"]["packaging"]["stats"]["total_cny"] = 25.0
        res = check_stage_pages(write_dist(tmp_path, payload), tmp_path / "reports")
        assert res.status == "fail"
        assert any("grand total" in d for d in res.details)

    def test_stats_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = stage_pages_payload()
        payload["stage_pages"]["design_prototyping"]["stats"]["n_lines"] = 7
        res = check_stage_pages(write_dist(tmp_path, payload), tmp_path / "reports")
        assert res.status == "fail"
        assert any("stats" in d for d in res.details)

    def test_not_booked_flag_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = stage_pages_payload()
        payload["stage_pages"]["packaging"]["not_booked"] = False
        res = check_stage_pages(write_dist(tmp_path, payload), tmp_path / "reports")
        assert res.status == "fail"
        assert any("not_booked" in d for d in res.details)

    def test_unattributed_label_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = stage_pages_payload()
        payload["stage_pages"]["packaging"]["top_suppliers"][0]["supplier"] = "甲乙"
        res = check_stage_pages(write_dist(tmp_path, payload), tmp_path / "reports")
        assert res.status == "fail"
        assert any("top_suppliers" in d for d in res.details)


class TestIdealTimeline:
    def test_sources_present_ok(self, tmp_path):
        payload = stage_pages_payload()
        res = check_ideal_timeline(write_dist(tmp_path, payload))
        assert res.status == "ok", res.details

    def test_missing_dist_pending(self, tmp_path):
        assert check_ideal_timeline(tmp_path / "dist" / "index.html").status == "pending"

    def test_no_section_fails(self, tmp_path):
        payload = stage_pages_payload()
        del payload["ideal_timeline"]
        res = check_ideal_timeline(write_dist(tmp_path, payload))
        assert res.status == "fail"

    def test_empty_source_url_fails(self, tmp_path):
        payload = stage_pages_payload()
        payload["ideal_timeline"]["bars"][0]["source_url"] = ""
        res = check_ideal_timeline(write_dist(tmp_path, payload))
        assert res.status == "fail"

    def test_non_http_source_url_fails(self, tmp_path):
        payload = stage_pages_payload()
        payload["ideal_timeline"]["bars"][0]["source_url"] = "example.com/design"
        res = check_ideal_timeline(write_dist(tmp_path, payload))
        assert res.status == "fail"

    def test_empty_source_file_fails(self, tmp_path):
        payload = stage_pages_payload()
        payload["ideal_timeline"]["bars"][0]["source_file"] = ""
        res = check_ideal_timeline(write_dist(tmp_path, payload))
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


# ------------------------------------------------- executive IA (GH#31) -----


def write_optimization_md(tmp_path):
    """Synthetic optimization.md: ranked table + rec sections + stage shares."""
    opt_dir = tmp_path / "reports" / "optimization"
    opt_dir.mkdir(parents=True)
    (opt_dir / "optimization.md").write_text(
        "# Optimization recommendations\n"
        "\n"
        "| # | Recommendation | Saving | Prob | Score | Time | Effort |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 1 | Consolidate tooling orders | 12,000 | 60.0% | 7.2"
        " | 2 weeks | medium |\n"
        "| 2 | Merge freight runs | 8,000 | 50.0% | 4.0 | 1 week | low |\n"
        "\n"
        "### 1) Consolidate tooling orders\n"
        "**What to do:** batch the orders.\n"
        "**Savings math:** 3 molds -> 1.\n"
        "\n"
        "### 2) Merge freight runs\n"
        "**What to do:** share trucks.\n"
        "\n"
        "## Stage shares vs market\n"
        "\n"
        "| Stage | Our share | H1-2026 | Market reference |\n"
        "|---|---|---|---|\n"
        "| design_prototyping | 60.0% | 30,000 | typically 50-60% of spend |\n",
        encoding="utf-8",
    )


def write_benchmark_mds(tmp_path):
    """Synthetic benchmarks/<stage>.md pair (the real per-stage md format)."""
    bdir = tmp_path / "reports" / "benchmarks"
    bdir.mkdir(parents=True)
    (bdir / "tooling_molds.md").write_text(
        "# Benchmark: Tooling & Molds (injection tooling)\n"
        "\n"
        "Tooling is the largest one-off investment.\n"
        "\n"
        "## Typical ranges\n"
        "\n"
        "- Steel mold **1,000-5,000** per cavity, acc. 2026-08-01\n"
        "\n"
        "Sources:\n"
        "\n"
        "1. https://example.com/tooling — Tooling price survey, acc. 2026-08-01\n",
        encoding="utf-8",
    )
    (bdir / "design_prototyping.md").write_text(
        "# Benchmark: Design & Prototyping\n"
        "\n"
        "Design is paid per model.\n"
        "\n"
        "## Typical ranges\n"
        "\n"
        "- Concept art **50-200** per part, acc. 2026-08-02\n",
        encoding="utf-8",
    )


def exec_payload(tmp_path):
    """Full executive-IA payload consistent with write_stage_page_reports.

    home / ia / supplier_pages / optimization_pages / benchmark_pages are
    built from the same synthetic reports the stage-pages fixtures use.
    """
    write_optimization_md(tmp_path)
    write_benchmark_mds(tmp_path)
    payload = stage_pages_payload()
    menu = payload["stages"]
    payload["home"] = {
        "lead": "synthetic lead",
        "stage_cards": menu,
        "deepdive_links": [
            {"id": t, "label": t.title(), "href": f"#/tab/{t}"} for t in IA_TABS
        ],
    }
    payload["ia"] = {
        "default_hash": "#/home",
        "redirects": {"#/overview": "#/home"},
        "routes": [
            {"hash": "#/home", "screen": "home", "title": "Home",
             "crumbs": ["Home"]},
        ]
        + [
            {"hash": f"#/tab/{t}", "screen": t, "title": t.title(),
             "crumbs": ["Home", t.title()]}
            for t in IA_TABS
        ],
        "stage_crumbs": ["Home", "Process"],
    }
    payload["supplier_pages"] = {
        "杭州宏达": {
            "label": "Hangzhou Hongda (杭州宏达)", "is_unattributed": False,
            "forensics": "",
            "stats": {"total_cny": 20.0, "share_pct": 40.0,
                      "months_active": 1, "n_lines": 1},
            "stage_mix": [{"stage": "design_prototyping", "amount_cny": 20.0}],
            "months": [{"month": "2026-01", "amount_cny": 25.0}],
            "top_styles": [{"style_no": "AF-1", "amount_cny": 18.0,
                            "n_lines": 1}],
        },
        "东莞精密": {
            "label": "东莞精密", "is_unattributed": False, "forensics": "",
            "stats": {"total_cny": 10.0, "share_pct": 20.0,
                      "months_active": 1, "n_lines": 1},
            "stage_mix": [{"stage": "design_prototyping", "amount_cny": 10.0}],
            "months": [{"month": "2026-02", "amount_cny": 10.0}],
            "top_styles": [{"style_no": "AF-2", "amount_cny": 12.0,
                            "n_lines": 1}],
        },
        "Unattributed": {
            "label": "Unattributed", "is_unattributed": True,
            "forensics": "synthetic explainer",
            "stats": {"total_cny": 20.0, "share_pct": 40.0,
                      "months_active": 1, "n_lines": 2},
            "stage_mix": [{"stage": "packaging", "amount_cny": 20.0}],
            "months": [{"month": "2026-01", "amount_cny": 20.0}],
            "top_styles": [{"style_no": "AF-1", "amount_cny": 20.0,
                            "n_lines": 2}],
        },
    }
    opt = load_optimizations_md(tmp_path / "reports" / "optimization" / "optimization.md")
    payload["optimizations"] = opt
    payload["optimization_pages"] = {c["id"]: c for c in opt["cards"]}
    bench = load_benchmarks_md(tmp_path / "reports" / "benchmarks")
    payload["benchmarks"] = {"rows": [], "stages": bench}
    payload["benchmark_pages"] = build_benchmark_pages(
        bench, opt["market_comparison"]
    )
    return payload


def exec_html(payload):
    """Mini dist/index.html: nav + menus + catalogs + back links + payload."""
    tabs = "".join(f'<a href="#/tab/{t}">{t}</a>' for t in IA_TABS)
    stages = "".join(
        f'<li><a href="#/stage/{s["stage_id"]}">{s["label_en"]}</a></li>'
        for s in payload["stages"]
    )
    suppliers = "".join(
        f'<li><a href="#/supplier/{quote(n)}">{n}</a></li>'
        for n in payload["supplier_pages"]
    )
    opts = "".join(
        f'<li><a href="#/optimization/{i}">#{i}</a></li>'
        for i in payload["optimization_pages"]
    )
    bench = "".join(
        f'<li><a href="#/bench/{s}">{s}</a></li>'
        for s in payload["benchmark_pages"]
    )
    return (
        "<html><head><title>synthetic</title></head><body>"
        f'<a id="back-link" href="#/home">Back</a>'
        f"<nav>{tabs}</nav>"
        f'<ul id="stage-menu">{stages}</ul>'
        f"<ul>{suppliers}</ul>"
        f"<ul>{opts}</ul>"
        f"<ul>{bench}</ul>"
        '<p><a class="back" href="#/home">back</a></p>'
        '<p><a class="back" href="#/tab/suppliers">back</a></p>'
        '<p><a class="back" href="#/tab/optimizations">back</a></p>'
        '<p><a class="back" href="#/tab/benchmarks">back</a></p>'
        '<script id="dash-data" type="application/json">'
        f"{json.dumps(payload)}</script>"
        "</body></html>"
    )


def write_exec_dist(tmp_path, payload, html=None):
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text(html or exec_html(payload), encoding="utf-8")
    return dist / "index.html"


class TestHomeReconciles:
    def test_matching_payload_ok(self, tmp_path):
        write_stage_page_reports(tmp_path)
        dist = write_exec_dist(tmp_path, exec_payload(tmp_path))
        res = check_home_reconciles(dist, tmp_path / "reports")
        assert res.status == "ok", res.details

    def test_missing_dist_pending(self, tmp_path):
        write_stage_page_reports(tmp_path)
        res = check_home_reconciles(
            tmp_path / "dist" / "index.html", tmp_path / "reports"
        )
        assert res.status == "pending"

    def test_missing_summary_pending(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        (tmp_path / "reports" / "audit" / "stage_summary.csv").unlink()
        res = check_home_reconciles(write_exec_dist(tmp_path, payload),
                                    tmp_path / "reports")
        assert res.status == "pending"

    def test_card_amount_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["home"]["stage_cards"][0]["amount_cny"] = 99.0
        res = check_home_reconciles(write_exec_dist(tmp_path, payload),
                                    tmp_path / "reports")
        assert res.status == "fail"
        assert any("design_prototyping" in d for d in res.details)

    def test_card_sum_ne_grand_total_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["home"]["stage_cards"] = payload["home"]["stage_cards"][:1]
        res = check_home_reconciles(write_exec_dist(tmp_path, payload),
                                    tmp_path / "reports")
        assert res.status == "fail"
        assert any("grand total" in d for d in res.details)

    def test_menu_order_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["home"]["stage_cards"] = list(
            reversed(payload["home"]["stage_cards"])
        )
        res = check_home_reconciles(write_exec_dist(tmp_path, payload),
                                    tmp_path / "reports")
        assert res.status == "fail"
        assert any("order" in d for d in res.details)

    def test_share_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["home"]["stage_cards"][1]["share_pct"] = 99.0
        res = check_home_reconciles(write_exec_dist(tmp_path, payload),
                                    tmp_path / "reports")
        assert res.status == "fail"
        assert any("share_pct" in d for d in res.details)

    def test_no_home_section_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        del payload["home"]
        res = check_home_reconciles(write_exec_dist(tmp_path, payload),
                                    tmp_path / "reports")
        assert res.status == "fail"


class TestSupplierPagesCheck:
    def test_matching_payload_ok(self, tmp_path):
        write_stage_page_reports(tmp_path)
        dist = write_exec_dist(tmp_path, exec_payload(tmp_path))
        res = check_supplier_pages(dist, tmp_path / "reports")
        assert res.status == "ok", res.details

    def test_missing_dist_pending(self, tmp_path):
        write_stage_page_reports(tmp_path)
        res = check_supplier_pages(
            tmp_path / "dist" / "index.html", tmp_path / "reports"
        )
        assert res.status == "pending"

    def test_missing_stage_csv_pending(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        (tmp_path / "reports" / "audit" / "by_supplier_stage.csv").unlink()
        res = check_supplier_pages(write_exec_dist(tmp_path, payload),
                                   tmp_path / "reports")
        assert res.status == "pending"

    def test_legacy_stage_csv_without_month_file_ok(self, tmp_path):
        """Legacy per-month by_supplier_stage.csv without by_supplier_month.csv:
        months derive from the catalog rows (the builder's fallback) and
        n_lines counts rows, mirroring load_suppliers."""
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        audit = tmp_path / "reports" / "audit"
        pd.DataFrame(
            [
                {"supplier": "杭州宏达", "stage": "design_prototyping",
                 "month": "2026-01", "amount_cny": 20.0},
                {"supplier": "东莞精密", "stage": "design_prototyping",
                 "month": "2026-02", "amount_cny": 10.0},
                {"supplier": "", "stage": "packaging", "month": "2026-01",
                 "amount_cny": 20.0},
            ]
        ).to_csv(audit / "by_supplier_stage.csv", index=False)
        (audit / "by_supplier_month.csv").unlink()
        payload["supplier_pages"]["杭州宏达"]["months"] = [
            {"month": "2026-01", "amount_cny": 20.0}
        ]
        payload["supplier_pages"]["Unattributed"]["stats"]["n_lines"] = 1
        res = check_supplier_pages(write_exec_dist(tmp_path, payload),
                                   tmp_path / "reports")
        assert res.status == "ok", res.details

    def test_aggregated_layout_without_month_file_ok(self, tmp_path):
        """Aggregated catalog + no by_supplier_month.csv: the builder renders
        no monthly series at all, the check must expect empty months."""
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        (tmp_path / "reports" / "audit" / "by_supplier_month.csv").unlink()
        for page in payload["supplier_pages"].values():
            page["months"] = []
        res = check_supplier_pages(write_exec_dist(tmp_path, payload),
                                   tmp_path / "reports")
        assert res.status == "ok", res.details

    def test_missing_style_file_ok_with_empty_styles(self, tmp_path):
        """No by_supplier_style.csv: the builder renders no styles, the
        check must expect empty top_styles instead of going pending."""
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        (tmp_path / "reports" / "audit" / "by_supplier_style.csv").unlink()
        for page in payload["supplier_pages"].values():
            page["top_styles"] = []
        res = check_supplier_pages(write_exec_dist(tmp_path, payload),
                                   tmp_path / "reports")
        assert res.status == "ok", res.details

    def test_total_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["supplier_pages"]["杭州宏达"]["stats"]["total_cny"] = 21.0
        res = check_supplier_pages(write_exec_dist(tmp_path, payload),
                                   tmp_path / "reports")
        assert res.status == "fail"
        assert any("杭州宏达" in d for d in res.details)

    def test_month_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["supplier_pages"]["东莞精密"]["months"] = []
        res = check_supplier_pages(write_exec_dist(tmp_path, payload),
                                   tmp_path / "reports")
        assert res.status == "fail"
        assert any("months" in d for d in res.details)

    def test_style_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["supplier_pages"]["杭州宏达"]["top_styles"] = []
        res = check_supplier_pages(write_exec_dist(tmp_path, payload),
                                   tmp_path / "reports")
        assert res.status == "fail"
        assert any("top_styles" in d for d in res.details)

    def test_stage_mix_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["supplier_pages"]["Unattributed"]["stage_mix"] = [
            {"stage": "design_prototyping", "amount_cny": 20.0}
        ]
        res = check_supplier_pages(write_exec_dist(tmp_path, payload),
                                   tmp_path / "reports")
        assert res.status == "fail"
        assert any("stage_mix" in d for d in res.details)

    def test_missing_page_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        del payload["supplier_pages"]["东莞精密"]
        res = check_supplier_pages(write_exec_dist(tmp_path, payload),
                                   tmp_path / "reports")
        assert res.status == "fail"

    def test_extra_page_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["supplier_pages"]["Ghost Vendor"] = dict(
            payload["supplier_pages"]["东莞精密"]
        )
        res = check_supplier_pages(write_exec_dist(tmp_path, payload),
                                   tmp_path / "reports")
        assert res.status == "fail"
        assert any("Ghost Vendor" in d for d in res.details)

    def test_n_lines_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["supplier_pages"]["Unattributed"]["stats"]["n_lines"] = 5
        res = check_supplier_pages(write_exec_dist(tmp_path, payload),
                                   tmp_path / "reports")
        assert res.status == "fail"


class TestOptimizationPagesCheck:
    def test_md_source_ok(self, tmp_path):
        write_stage_page_reports(tmp_path)
        dist = write_exec_dist(tmp_path, exec_payload(tmp_path))
        res = check_optimization_pages(dist, tmp_path / "reports")
        assert res.status == "ok", res.details

    def test_csv_source_ok(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        cards = payload["optimizations"]["cards"]
        pd.DataFrame(
            [
                {"id": c["id"], "title": c["title"],
                 "stage": "design_prototyping",
                 "baseline_cny": 0.0, "saving_cny": c["saving_cny"],
                 "proof": "synthetic"}
                for c in cards
            ]
        ).to_csv(tmp_path / "reports" / "optimization" / "optimizations.csv",
                 index=False)
        res = check_optimization_pages(write_exec_dist(tmp_path, payload),
                                       tmp_path / "reports")
        assert res.status == "ok", res.details

    def test_missing_dist_pending(self, tmp_path):
        write_stage_page_reports(tmp_path)
        res = check_optimization_pages(
            tmp_path / "dist" / "index.html", tmp_path / "reports"
        )
        assert res.status == "pending"

    def test_missing_source_pending(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        (tmp_path / "reports" / "optimization" / "optimization.md").unlink()
        res = check_optimization_pages(write_exec_dist(tmp_path, payload),
                                       tmp_path / "reports")
        assert res.status == "pending"

    def test_missing_page_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        del payload["optimization_pages"]["2"]
        res = check_optimization_pages(write_exec_dist(tmp_path, payload),
                                       tmp_path / "reports")
        assert res.status == "fail"

    def test_saving_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["optimization_pages"]["1"]["saving_cny"] = 999.0
        res = check_optimization_pages(write_exec_dist(tmp_path, payload),
                                       tmp_path / "reports")
        assert res.status == "fail"
        assert any("saving" in d for d in res.details)

    def test_title_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["optimization_pages"]["2"]["title"] = "Renamed"
        res = check_optimization_pages(write_exec_dist(tmp_path, payload),
                                       tmp_path / "reports")
        assert res.status == "fail"
        assert any("title" in d for d in res.details)

    def test_stale_md_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        md = tmp_path / "reports" / "optimization" / "optimization.md"
        md.write_text(md.read_text(encoding="utf-8").replace("12,000", "13,500"),
                      encoding="utf-8")
        res = check_optimization_pages(write_exec_dist(tmp_path, payload),
                                       tmp_path / "reports")
        assert res.status == "fail"


class TestBenchmarkPagesCheck:
    def test_md_source_ok(self, tmp_path):
        write_stage_page_reports(tmp_path)
        dist = write_exec_dist(tmp_path, exec_payload(tmp_path))
        res = check_benchmark_pages(dist, tmp_path / "reports")
        assert res.status == "ok", res.details

    def test_missing_dist_pending(self, tmp_path):
        write_stage_page_reports(tmp_path)
        res = check_benchmark_pages(
            tmp_path / "dist" / "index.html", tmp_path / "reports"
        )
        assert res.status == "pending"

    def test_missing_source_pending(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        for md in (tmp_path / "reports" / "benchmarks").glob("*.md"):
            md.unlink()
        res = check_benchmark_pages(write_exec_dist(tmp_path, payload),
                                    tmp_path / "reports")
        assert res.status == "pending"

    def test_missing_page_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        del payload["benchmark_pages"]["design_prototyping"]
        res = check_benchmark_pages(write_exec_dist(tmp_path, payload),
                                    tmp_path / "reports")
        assert res.status == "fail"

    def test_our_join_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["benchmark_pages"]["design_prototyping"]["our"][
            "h1_2026_cny"
        ] = 999.0
        res = check_benchmark_pages(write_exec_dist(tmp_path, payload),
                                    tmp_path / "reports")
        assert res.status == "fail"
        assert any("our" in d for d in res.details)

    def test_our_must_be_null_when_not_in_comparison(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["benchmark_pages"]["tooling_molds"]["our"] = {
            "share_pct": 10.0, "h1_2026_cny": 5.0, "market_ref": "x"
        }
        res = check_benchmark_pages(write_exec_dist(tmp_path, payload),
                                    tmp_path / "reports")
        assert res.status == "fail"

    def test_highlights_drift_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["benchmark_pages"]["tooling_molds"]["highlights"] = []
        res = check_benchmark_pages(write_exec_dist(tmp_path, payload),
                                    tmp_path / "reports")
        assert res.status == "fail"
        assert any("highlights" in d for d in res.details)


class TestRoutesComplete:
    def test_routes_ok(self, tmp_path):
        write_stage_page_reports(tmp_path)
        dist = write_exec_dist(tmp_path, exec_payload(tmp_path))
        res = check_routes_complete(dist)
        assert res.status == "ok", res.details

    def test_missing_dist_pending(self, tmp_path):
        res = check_routes_complete(tmp_path / "dist" / "index.html")
        assert res.status == "pending"

    def test_no_ia_section_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        del payload["ia"]
        res = check_routes_complete(write_exec_dist(tmp_path, payload))
        assert res.status == "fail"

    def test_bad_default_hash_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["ia"]["default_hash"] = "#/nowhere"
        res = check_routes_complete(write_exec_dist(tmp_path, payload))
        assert res.status == "fail"
        assert any("default_hash" in d for d in res.details)

    def test_redirect_to_unknown_hash_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["ia"]["redirects"] = {"#/overview": "#/ghost"}
        res = check_routes_complete(write_exec_dist(tmp_path, payload))
        assert res.status == "fail"
        assert any("redirect" in d for d in res.details)

    def test_duplicate_route_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["ia"]["routes"].append(dict(payload["ia"]["routes"][1]))
        res = check_routes_complete(write_exec_dist(tmp_path, payload))
        assert res.status == "fail"

    def test_missing_tab_route_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["ia"]["routes"] = [
            r for r in payload["ia"]["routes"] if r["hash"] != "#/tab/glossary"
        ]
        res = check_routes_complete(write_exec_dist(tmp_path, payload))
        assert res.status == "fail"
        assert any("glossary" in d for d in res.details)

    def test_route_without_crumbs_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["ia"]["routes"][1]["crumbs"] = []
        res = check_routes_complete(write_exec_dist(tmp_path, payload))
        assert res.status == "fail"
        assert any("crumbs" in d for d in res.details)

    def test_dead_link_in_html_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        html = exec_html(payload).replace(
            "</body>", '<a href="#/stage/ghost_stage">dead</a></body>'
        )
        res = check_routes_complete(write_exec_dist(tmp_path, payload, html))
        assert res.status == "fail"
        assert any("ghost_stage" in d for d in res.details)

    def test_unreachable_supplier_page_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        name = quote("东莞精密")
        html = exec_html(payload).replace(
            f'<li><a href="#/supplier/{name}">东莞精密</a></li>', ""
        )
        assert f"#/supplier/{name}" not in html  # link really gone
        res = check_routes_complete(write_exec_dist(tmp_path, payload, html))
        assert res.status == "fail"
        assert any("东莞精密" in d for d in res.details)

    def test_deepdive_link_to_unknown_tab_fails(self, tmp_path):
        write_stage_page_reports(tmp_path)
        payload = exec_payload(tmp_path)
        payload["home"]["deepdive_links"].append(
            {"id": "ghost", "label": "Ghost", "href": "#/tab/ghost"}
        )
        res = check_routes_complete(write_exec_dist(tmp_path, payload))
        assert res.status == "fail"
        assert any("ghost" in d for d in res.details)


class TestExecutiveRunChecks:
    def test_run_checks_includes_new_checks(self, tmp_path):
        write_stage_page_reports(tmp_path)
        dist = write_exec_dist(tmp_path, exec_payload(tmp_path))
        results = {r.name: r for r in run_checks(
            tmp_path, tmp_path / "reports", tmp_path, dist
        )}
        for name in ("home_reconciles", "supplier_pages", "optimization_pages",
                     "benchmark_pages", "routes_complete"):
            assert name in results, name
        report = format_report(list(results.values()))
        assert "routes_complete" in report
