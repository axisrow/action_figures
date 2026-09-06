"""Tests for the ideal production timeline reference module.

The module holds static reference durations distilled from
reports/benchmarks/*.md — no real financial data and no network/file
access in these tests (the CSV writer is exercised on tmp_path only).
"""

import csv

from action_figures.ideal_timeline import (
    IDEAL_TIMELINE,
    TimelineStage,
    write_csv,
)

EXPECTED_STAGE_IDS = {
    "design_prototyping",
    "tooling_molds",
    "injection_molding",
    "textile_accessories",
    "painting_printing",
    "assembly_processing",
    "packaging",
    "qc_testing",
    "logistics_freight",
}

# Every row must cite one of the benchmark reports (by filename).
BENCHMARK_FILES = {
    "design_prototyping.md",
    "tooling_molds.md",
    "injection_molding.md",
    "painting_printing.md",
    "assembly_processing.md",
    "raw_materials.md",
    "textile_accessories.md",
    "packaging.md",
    "qc_testing.md",
    "logistics_freight.md",
}


def test_stage_count_and_ids() -> None:
    """Exactly 10 reference rows covering the 9 production stage ids."""
    assert len(IDEAL_TIMELINE) == 10
    assert {s.stage_id for s in IDEAL_TIMELINE} == EXPECTED_STAGE_IDS


def test_row_schema() -> None:
    """Every row is a TimelineStage with sane types and min <= max."""
    for stage in IDEAL_TIMELINE:
        assert isinstance(stage, TimelineStage)
        assert isinstance(stage.stage_id, str) and stage.stage_id
        assert isinstance(stage.min_weeks, int) and stage.min_weeks >= 1
        assert isinstance(stage.max_weeks, int) and stage.max_weeks >= 1
        assert stage.min_weeks <= stage.max_weeks
        assert isinstance(stage.parallel_group, str) and stage.parallel_group
        assert isinstance(stage.source_file, str) and stage.source_file
        assert isinstance(stage.source_url, str)
        assert isinstance(stage.variant, str)


def test_sources_present_and_local_to_benchmarks() -> None:
    """Each duration cites a benchmark report file and a non-empty URL."""
    for stage in IDEAL_TIMELINE:
        assert stage.source_file in BENCHMARK_FILES
        assert stage.source_url.startswith(("http://", "https://"))
        assert len(stage.source_url) > 20


def test_tooling_has_steel_and_aluminum_variants() -> None:
    """Tooling is split into a steel and an aluminum/rapid variant row."""
    tooling = [s for s in IDEAL_TIMELINE if s.stage_id == "tooling_molds"]
    by_variant = {s.variant: s for s in tooling}
    assert set(by_variant) == {"steel", "aluminum"}
    assert (by_variant["steel"].min_weeks, by_variant["steel"].max_weeks) == (5, 7)
    assert (by_variant["aluminum"].min_weeks, by_variant["aluminum"].max_weeks) == (1, 3)


def test_textile_overlaps_molding_window() -> None:
    """Textile runs in the same parallel window as molding (issue #8)."""
    groups = {s.stage_id: s.parallel_group for s in IDEAL_TIMELINE}
    assert groups["textile_accessories"] == groups["injection_molding"]
    assert groups["textile_accessories"] != "main"


def test_production_order() -> None:
    """Rows are listed in production order for a reference Gantt."""
    firsts = [s.stage_id for s in IDEAL_TIMELINE]
    assert firsts[0] == "design_prototyping"
    tail = ["packaging", "qc_testing", "logistics_freight"]
    assert firsts[-3:] == tail


def test_total_reference_span_fits_26_weeks() -> None:
    """Serial main chain + parallel molding window stays within 26 weeks."""
    main = [s for s in IDEAL_TIMELINE if s.parallel_group == "main"]
    window = [s for s in IDEAL_TIMELINE if s.parallel_group == "molding_window"]
    worst = sum(s.max_weeks for s in main) + max(s.max_weeks for s in window)
    assert worst <= 26


def test_write_csv_round_trip(tmp_path) -> None:
    """CSV export writes a header plus one row per stage and round-trips."""
    path = tmp_path / "ideal_timeline.csv"
    written = write_csv(path)
    assert written == path
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(IDEAL_TIMELINE)
    assert rows[0]["stage_id"] == IDEAL_TIMELINE[0].stage_id
    assert rows[0]["min_weeks"] == str(IDEAL_TIMELINE[0].min_weeks)
    assert rows[3]["source_url"] == IDEAL_TIMELINE[3].source_url
