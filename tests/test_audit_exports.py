"""GH#5 data-layer exports: by_day_stage.csv and stages.csv.

100% synthetic data (same policy as conftest): invented dates, stages and
amounts — no real suppliers, style numbers, transaction dates or totals.
"""

from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from action_figures.audit_tables import by_day_stage
from action_figures.classify import load_taxonomy
from action_figures.stages_meta import STAGE_ORDER, stages_metadata
from action_figures.verify_lib import (
    TOL,
    check_audit_totals,
    check_stage_totals,
    run_checks,
)

TAX = load_taxonomy()

CJK_RE = re.compile(r"[一-鿿]")
SENTENCE_SPLIT_RE = re.compile(r"(?<=\.)\s+")


def staged_frame(rows) -> pd.DataFrame:
    """rows: (line_id, date, stage, amount) -> minimal staged frame."""
    return pd.DataFrame(rows, columns=["line_id", "date", "stage", "amount"])


# ------------------------------------------------------------- by_day_stage ---


class TestByDayStage:
    def test_groups_by_date_and_stage(self):
        df = staged_frame(
            [
                ("L1", date(2026, 3, 1), "tooling_molds", 100.0),
                ("L2", date(2026, 3, 1), "tooling_molds", 50.0),
                ("L3", date(2026, 3, 1), "packaging", 10.0),
                ("L4", date(2026, 3, 2), "tooling_molds", 5.0),
            ]
        )
        out = by_day_stage(df)
        assert list(out.columns) == ["date", "stage", "amount_cny", "n_lines"]
        assert len(out) == 3
        row = out[(out["date"] == "2026-03-01") & (out["stage"] == "tooling_molds")].iloc[0]
        assert row["amount_cny"] == pytest.approx(150.0)
        assert row["n_lines"] == 2

    def test_totals_preserved(self):
        df = staged_frame(
            [
                ("L1", date(2026, 1, 5), "tooling_molds", 0.01),
                ("L2", date(2026, 1, 5), "packaging", 99.99),
                ("L3", date(2026, 2, 1), "tooling_molds", 1234.56),
                ("L4", None, "raw_materials", 7.0),
            ]
        )
        out = by_day_stage(df)
        assert out["amount_cny"].sum() == pytest.approx(df["amount"].sum())
        assert out["n_lines"].sum() == len(df)

    def test_lines_without_date_form_last_group_with_empty_date(self):
        df = staged_frame(
            [
                ("L1", date(2026, 3, 2), "packaging", 1.0),
                ("L2", None, "packaging", 2.0),
                ("L3", None, "packaging", 4.0),
                ("L4", date(2026, 3, 1), "packaging", 8.0),
            ]
        )
        out = by_day_stage(df)
        assert out["date"].tolist() == ["2026-03-01", "2026-03-02", ""]
        assert out.iloc[-1]["n_lines"] == 2
        assert out.iloc[-1]["amount_cny"] == pytest.approx(6.0)

    def test_dates_are_iso_strings_sorted_ascending(self):
        df = staged_frame(
            [
                ("L1", date(2026, 3, 2), "packaging", 1.0),
                ("L2", date(2026, 1, 15), "packaging", 2.0),
                ("L3", date(2026, 3, 1), "packaging", 4.0),
            ]
        )
        out = by_day_stage(df)
        assert out["date"].tolist() == ["2026-01-15", "2026-03-01", "2026-03-02"]

    def test_amount_descending_within_a_day(self):
        df = staged_frame(
            [
                ("L1", date(2026, 3, 1), "packaging", 1.0),
                ("L2", date(2026, 3, 1), "tooling_molds", 500.0),
                ("L3", date(2026, 3, 1), "raw_materials", 50.0),
            ]
        )
        out = by_day_stage(df)
        assert out["stage"].tolist() == ["tooling_molds", "raw_materials", "packaging"]

    def test_input_frame_not_mutated(self):
        df = staged_frame([("L1", date(2026, 3, 1), "packaging", 1.0)])
        by_day_stage(df)
        assert list(df.columns) == ["line_id", "date", "stage", "amount"]
        assert df.loc[0, "date"] == date(2026, 3, 1)


# ----------------------------------------------------- stages.csv metadata ---


class TestStagesMetadata:
    def test_schema_columns(self):
        meta = stages_metadata(TAX)
        assert list(meta.columns) == [
            "stage_id",
            "order",
            "label_en",
            "description_en",
            "zh_keys",
        ]

    def test_production_order_then_service_buckets(self):
        meta = stages_metadata(TAX)
        assert meta["stage_id"].tolist() == [
            "design_prototyping",
            "tooling_molds",
            "raw_materials",
            "injection_molding",
            "painting_printing",
            "textile_accessories",
            "assembly_processing",
            "packaging",
            "qc_testing",
            "logistics_freight",
            "admin_other",
            "unclassified",
        ]
        assert meta["order"].tolist() == list(range(1, 13))

    def test_stage_order_covers_taxonomy(self):
        assert set(TAX) | {"unclassified"} == set(STAGE_ORDER)

    def test_labels_and_descriptions_are_plain_english(self):
        meta = stages_metadata(TAX)
        for r in meta.itertuples():
            assert r.label_en and not CJK_RE.search(r.label_en), r.stage_id
            assert r.description_en and not CJK_RE.search(r.description_en), r.stage_id
            sentences = [s for s in SENTENCE_SPLIT_RE.split(r.description_en.strip()) if s]
            assert 1 <= len(sentences) <= 2, r.stage_id
            assert r.description_en.endswith("."), r.stage_id

    def test_zh_keys_match_taxonomy_keywords(self):
        meta = stages_metadata(TAX).set_index("stage_id")
        for stage, keywords in TAX.items():
            assert meta.loc[stage, "zh_keys"] == ";".join(keywords), stage

    def test_unclassified_has_no_zh_keys(self):
        meta = stages_metadata(TAX).set_index("stage_id")
        assert meta.loc["unclassified", "zh_keys"] == ""


# ---------------------------------------------------------- verify: totals ---


def write_all_months_pkl(data_root: Path, amounts: list[float]) -> None:
    pkl_dir = data_root / "pkl" / "zh"
    pkl_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"amount": amounts, "qty": [1.0] * len(amounts),
                  "unit_price": amounts}).to_pickle(pkl_dir / "all_months.pkl")


def write_reports(
    tmp_path: Path,
    by_day_rows: list[tuple],
    summary_rows: list[tuple],
) -> Path:
    """Synthetic audit CSVs. Rows: (date|stage, stage, amount, n_lines)."""
    audit = tmp_path / "reports" / "audit"
    audit.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(by_day_rows, columns=["date", "stage", "amount_cny", "n_lines"]).to_csv(
        audit / "by_day_stage.csv", index=False
    )
    pd.DataFrame(summary_rows, columns=["stage", "n_lines", "amount_cny", "share_pct"]).to_csv(
        audit / "stage_summary.csv", index=False
    )
    return tmp_path / "reports"


BY_DAY_ROWS = [
    ("2026-03-01", "packaging", 30.0, 1),
    ("2026-03-02", "packaging", 10.0, 1),
    ("2026-03-01", "tooling_molds", 20.5, 1),
]
SUMMARY_ROWS = [("packaging", 2, 40.0, 66.67), ("tooling_molds", 1, 20.5, 33.33)]


class TestCheckAuditTotalsIncludesByDay:
    def test_by_day_stage_csv_checked_ok(self, tmp_path):
        write_all_months_pkl(tmp_path, [30.0, 20.5, 10.0])
        reports = write_reports(tmp_path, BY_DAY_ROWS, SUMMARY_ROWS)
        res = check_audit_totals(reports, tmp_path)
        assert res.status == "ok", res.details

    def test_by_day_stage_drift_fails(self, tmp_path):
        write_all_months_pkl(tmp_path, [30.0, 20.5, 10.0])
        drifted = [row if row[2] != 20.5 else ("2026-03-01", "tooling_molds", 999.0, 1)
                   for row in BY_DAY_ROWS]
        reports = write_reports(tmp_path, drifted, SUMMARY_ROWS)
        res = check_audit_totals(reports, tmp_path)
        assert res.status == "fail"
        assert any("by_day_stage.csv" in d for d in res.details)


class TestCheckStageTotals:
    def test_per_stage_totals_match_ok(self, tmp_path):
        reports = write_reports(tmp_path, BY_DAY_ROWS, SUMMARY_ROWS)
        res = check_stage_totals(reports)
        assert res.status == "ok", res.details

    def test_amount_drift_fails(self, tmp_path):
        reports = write_reports(
            tmp_path, BY_DAY_ROWS, [("packaging", 3, 41.0, 66.67), ("tooling_molds", 1, 20.5, 33.33)]
        )
        res = check_stage_totals(reports)
        assert res.status == "fail"
        assert any("packaging" in d for d in res.details)

    def test_line_count_drift_fails(self, tmp_path):
        reports = write_reports(
            tmp_path, BY_DAY_ROWS, [("packaging", 3, 40.0, 66.67), ("tooling_molds", 1, 20.5, 33.33)]
        )
        res = check_stage_totals(reports)
        assert res.status == "fail"

    def test_stage_missing_from_summary_fails(self, tmp_path):
        reports = write_reports(tmp_path, BY_DAY_ROWS, [("packaging", 2, 40.0, 100.0)])
        res = check_stage_totals(reports)
        assert res.status == "fail"
        assert any("tooling_molds" in d for d in res.details)

    def test_missing_reports_pending(self, tmp_path):
        res = check_stage_totals(tmp_path / "reports")
        assert res.status == "pending"

    def test_tolerance_respected(self, tmp_path):
        reports = write_reports(
            tmp_path, BY_DAY_ROWS, [("packaging", 2, 40.0 + TOL, 66.67), ("tooling_molds", 1, 20.5, 33.33)]
        )
        assert check_stage_totals(reports).status == "ok"


def init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q"], cwd=repo, check=True, capture_output=True,
        env={"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
             "HOME": str(repo), "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )
    (repo / ".gitignore").write_text("data/\nreports/\n", encoding="utf-8")
    return repo


class TestRunChecksIncludesStageTotals:
    def test_stage_totals_in_runner(self, tmp_path):
        write_all_months_pkl(tmp_path, [30.0, 20.5, 10.0])
        write_reports(tmp_path, BY_DAY_ROWS, SUMMARY_ROWS)
        repo = init_repo(tmp_path)
        results = run_checks(tmp_path, tmp_path / "reports", repo, tmp_path / "dist" / "index.html")
        names = {r.name for r in results}
        assert "stage_totals" in names
        stage_res = next(r for r in results if r.name == "stage_totals")
        assert stage_res.status == "ok", stage_res.details
