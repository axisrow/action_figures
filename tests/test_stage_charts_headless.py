"""Headless-browser tests for the stage-page charts (GH#24).

Red-first suite: on main the "Spend by month" / "Spend by day" charts render
empty because ``fillStage`` calls ``echarts.init`` while ``#stage-view`` is
still ``display:none`` (the router shows the panel *after* filling it), so the
canvas is 0x0 and never re-laid-out. The option builder is also not a
testable pure function.

Three layers:
- integration: mount the generated dist/index.html, navigate to a stage page,
  assert both charts have non-empty series AND non-zero rendered geometry;
- smoke: every one of the 12 stage pages (10 booked + packaging/qc placeholders);
- unit: the pure ``stageChartOption(stageData)`` builder via window export.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("pytest_playwright", reason="headless chart tests need"
                    " pytest-playwright + a chromium install")

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
sys.path.insert(0, str(DASHBOARD_DIR))

import build_dashboard as bd  # noqa: E402

BOOKED_STAGES = [
    "design_prototyping",
    "tooling_molds",
    "raw_materials",
    "injection_molding",
    "painting_printing",
    "textile_accessories",
    "assembly_processing",
    "logistics_freight",
    "admin_other",
    "unclassified",
]
PLACEHOLDER_STAGES = ["packaging", "qc_testing"]


@pytest.fixture(scope="module")
def dashboard_url(tmp_path_factory):
    """Generated dist/index.html over the MOCK synthetic reports."""
    out = tmp_path_factory.mktemp("dash") / "index.html"
    missing_reports = tmp_path_factory.mktemp("no_reports") / "reports"
    assert bd.main(["--reports", str(missing_reports), "--out", str(out)]) == 0
    return out.as_uri()


@pytest.fixture()
def page(browser, dashboard_url):
    page = browser.new_page()
    page.goto(dashboard_url)
    # ECharts loads from the CDN — wait until the charts can initialize
    page.wait_for_function("typeof echarts !== 'undefined'", timeout=30000)
    yield page
    page.close()


@pytest.fixture()
def payload(page):
    """The embedded dash-data JSON, read back from the mounted page."""
    return page.evaluate(
        "JSON.parse(document.getElementById('dash-data').textContent)"
    )


def _goto_stage(page, stage_id, order):
    page.evaluate(f"location.hash = '#/stage/{stage_id}'")
    page.wait_for_function(
        "([t]) => document.getElementById('stage-title').textContent.indexOf(t)"
        " >= 0",
        arg=[f"Stage {order} — "],
    )


def _chart_state(page, dom_id):
    """Series lengths + rendered geometry of one stage chart container."""
    return page.evaluate(
        """([domId]) => {
            const el = document.getElementById(domId);
            const inst = window.echarts ? echarts.getInstanceByDom(el) : null;
            const opt = inst ? inst.getOption() : null;
            const rect = el.getBoundingClientRect();
            return {
                hidden: el.hidden,
                series: opt ? opt.series.map(s => (s.data || []).length) : null,
                rectW: rect.width,
                rectH: rect.height,
                instW: inst ? inst.getWidth() : 0,
                instH: inst ? inst.getHeight() : 0,
            };
        }""",
        [dom_id],
    )


def _assert_live_chart(state, expected_points, which):
    assert not state["hidden"], f"{which} chart container must be visible"
    assert state["rectW"] > 0 and state["rectH"] > 0, (
        f"{which} chart container has zero rendered geometry: "
        f'{state["rectW"]}x{state["rectH"]}'
    )
    assert state["instW"] > 0 and state["instH"] > 0, (
        f"{which} ECharts canvas is 0x0 — initialized while hidden (GH#24)"
    )
    assert state["series"], f"{which} chart has no series at all"
    for i, n in enumerate(state["series"]):
        assert n == expected_points, (
            f"{which} series[{i}] binds {n} points, payload has {expected_points}"
        )


# --- integration: the reported bug (design_prototyping) --------------------


def test_design_prototyping_stage_charts_have_data_and_geometry(page, payload):
    """GH#24 repro: both stage charts carry non-empty series data and render
    into non-zero geometry after hash navigation to the stage page."""
    stages = {s["stage_id"]: s for s in payload["stages"]}
    sp = payload["stage_pages"]["design_prototyping"]
    assert not sp["not_booked"]
    assert sp["months"] and sp["days"], "mock payload must exercise real series"

    _goto_stage(page, "design_prototyping", stages["design_prototyping"]["order"])
    _assert_live_chart(
        _chart_state(page, "stage-chart-monthly"), len(sp["months"]), "monthly"
    )
    daily = _chart_state(page, "stage-chart-daily")
    # daily chart calendar-fills gaps: at least one point per booked day
    _assert_live_chart(daily, daily["series"][0] if daily["series"] else 0, "daily")
    assert daily["series"] and all(n >= len(sp["days"]) for n in daily["series"])


def test_stage_charts_rebind_on_second_hash_visit(page, payload):
    """Re-entering a stage page must rebind the series (notMerge), not keep
    the previous stage's option."""
    stages = {s["stage_id"]: s for s in payload["stages"]}
    first, second = "tooling_molds", "design_prototyping"
    _goto_stage(page, first, stages[first]["order"])
    _goto_stage(page, second, stages[second]["order"])
    monthly = _chart_state(page, "stage-chart-monthly")
    expected = len(payload["stage_pages"][second]["months"])
    assert monthly["series"] and monthly["series"][0] == expected


# --- smoke: all 12 stage pages ---------------------------------------------


def test_every_stage_page_renders_its_charts(page, payload):
    """10 booked pages: non-empty series + geometry on both charts;
    packaging/qc placeholders: explainer plate instead of charts."""
    stages = {s["stage_id"]: s for s in payload["stages"]}
    assert set(stages) == set(BOOKED_STAGES + PLACEHOLDER_STAGES)

    for sid in BOOKED_STAGES:
        sp = payload["stage_pages"][sid]
        assert not sp["not_booked"], sid
        assert sp["months"], f"mock payload has no months for {sid}"
        _goto_stage(page, sid, stages[sid]["order"])
        _assert_live_chart(
            _chart_state(page, "stage-chart-monthly"), len(sp["months"]),
            f"{sid}/monthly",
        )
        daily = _chart_state(page, "stage-chart-daily")
        assert daily["series"] and all(
            n >= len(sp["days"]) for n in daily["series"]
        ), f"{sid}/daily binds fewer points than booked days"

    for sid in PLACEHOLDER_STAGES:
        sp = payload["stage_pages"][sid]
        assert sp["not_booked"], sid
        _goto_stage(page, sid, stages[sid]["order"])
        plate = page.evaluate(
            "!document.getElementById('stage-plate').hidden"
        )
        assert plate, f"{sid} must show the not-booked plate"
        for dom_id in ("stage-chart-monthly", "stage-chart-daily"):
            assert _chart_state(page, dom_id)["hidden"], f"{sid}/{dom_id}"


# --- unit: pure option builder ---------------------------------------------


def test_stage_chart_option_binds_months_and_days(page):
    """stageChartOption(stageData): months -> matching bar series,
    days -> calendar-filled bar + 7-day-average line of matching length."""
    stage_data = {
        "not_booked": False,
        "months": [
            {"month": "2026-01", "amount_cny": 100.0},
            {"month": "2026-02", "amount_cny": 50.0},
            {"month": "2026-03", "amount_cny": 75.0},
        ],
        "days": [
            {"date": "2026-01-01", "amount_cny": 10.0},
            {"date": "2026-01-09", "amount_cny": 20.0},
        ],
    }
    opt = page.evaluate(
        "(sd) => window.__stageChartOption(sd)"
        " ? window.__stageChartOption(sd) : null",
        stage_data,
    )
    assert opt, "window.__stageChartOption must be exported for testing"
    assert opt["placeholder"] is False

    monthly = opt["monthly"]
    assert monthly["series"][0]["type"] == "bar"
    assert monthly["series"][0]["data"] == [100.0, 50.0, 75.0]
    assert monthly["xAxis"]["data"] == ["2026-01", "2026-02", "2026-03"]

    daily = opt["daily"]
    # 2026-01-01..09 calendar-filled: 9 points, 2 of them non-zero
    assert daily["series"][0]["type"] == "bar"
    assert daily["series"][0]["data"] == [10, 0, 0, 0, 0, 0, 0, 0, 20]
    assert daily["series"][1]["type"] == "line"  # 7-day rolling average
    assert len(daily["series"][1]["data"]) == 9
    assert daily["series"][1]["data"][0] == 10  # first window averages itself


def test_stage_chart_option_placeholder_for_not_booked(page):
    opt = page.evaluate(
        "(sd) => window.__stageChartOption(sd)"
        " ? window.__stageChartOption(sd) : null",
        {"not_booked": True, "months": [], "days": []},
    )
    assert opt, "window.__stageChartOption must be exported for testing"
    assert opt["placeholder"] is True
    assert not opt["monthly"] and not opt["daily"]
