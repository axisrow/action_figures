"""Headless smoke for the EI-5 noise pass (GH#30).

Full-matrix pass over the generated dashboard: Home, all deep-dive tabs,
every stage page, every supplier page and every optimization / benchmark
sub-screen must activate its panel, show the correct breadcrumb trail, keep
the Print view button reachable — and produce zero console errors. Print
media emulation must hide the interactive chrome while the summary content
(stage menu, KPI tiles) stays on the page.
"""

import sys
from pathlib import Path
from urllib.parse import quote

import pytest

pytest.importorskip("pytest_playwright", reason="headless smoke tests need"
                    " pytest-playwright + a chromium install")

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
sys.path.insert(0, str(DASHBOARD_DIR))

import build_dashboard as bd  # noqa: E402


@pytest.fixture(scope="module")
def dashboard_url(tmp_path_factory):
    out = tmp_path_factory.mktemp("dash") / "index.html"
    missing_reports = tmp_path_factory.mktemp("no_reports") / "reports"
    assert bd.main(["--reports", str(missing_reports), "--out", str(out)]) == 0
    return out.as_uri()


@pytest.fixture()
def page(browser, dashboard_url):
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on(
        "console",
        lambda m: errors.append(m.text) if m.type == "error" else None,
    )
    page.goto(dashboard_url)
    page.wait_for_function("typeof echarts !== 'undefined'", timeout=30000)
    yield page, errors
    page.close()


def _payload(page) -> dict:
    return page.evaluate(
        "JSON.parse(document.getElementById('dash-data').textContent)"
    )


def _goto(page, hash_: str):
    page.evaluate("h => { location.hash = h; }", hash_)


def _wait_active(page, panel_id: str):
    page.wait_for_function(
        "id => { const p = document.querySelector('.tab-panel.active');"
        " return p && p.id === id; }",
        arg=panel_id,
    )


def _active_panel(page) -> str:
    return page.evaluate(
        "document.querySelector('.tab-panel.active').id"
    )


def _crumbs(page) -> list[str]:
    return page.evaluate(
        "Array.from(document.querySelectorAll('#crumbs > *')"
        ").map(e => e.textContent).filter(t => t !== '›')"
    )


def _print_display(page, sel: str) -> str:
    return page.evaluate(
        "sel => { const el = document.querySelector(sel);"
        " return el ? getComputedStyle(el).display : 'absent'; }",
        sel,
    )


# --- smoke: shell routes (Home + 6 deep-dive tabs) --------------------------


def test_home_and_all_tabs_render_clean(page):
    page, errors = page
    routes = _payload(page)["ia"]["routes"]
    assert len(routes) == 7  # Home + six deep-dive tabs
    for r in routes:
        _goto(page, r["hash"])
        _wait_active(page, r["screen"])
        assert _active_panel(page) == r["screen"], r["hash"]
        assert _crumbs(page) == r["crumbs"], r["hash"]
        assert page.is_visible("#print-btn"), r["hash"]
    assert errors == []


# --- smoke: all 12 stage pages ----------------------------------------------


def test_all_stage_pages_render_clean(page):
    page, errors = page
    for s in _payload(page)["stages"]:
        _goto(page, f"#/stage/{s['stage_id']}")
        _wait_active(page, "stage-view")
        assert _active_panel(page) == "stage-view", s["stage_id"]
        assert _crumbs(page) == ["Home", "Process", s["label_en"]], s
        assert page.inner_text("#stage-title").strip(), s["stage_id"]
    assert errors == []


# --- smoke: every supplier page ----------------------------------------------


def test_all_supplier_pages_render_clean(page):
    page, errors = page
    pages = _payload(page)["supplier_pages"]
    assert len(pages) >= 12
    for name, meta in pages.items():
        _goto(page, f"#/supplier/{quote(name)}")
        _wait_active(page, "supplier-view")
        assert _active_panel(page) == "supplier-view", name
        assert _crumbs(page) == ["Home", "Suppliers", meta["label"]], name
        assert page.inner_text("#supplier-title").strip() != "", name
    assert errors == []


# --- smoke: every optimization + benchmark sub-screen ------------------------


def test_all_optimization_pages_render_clean(page):
    page, errors = page
    opts = _payload(page)["optimization_pages"]
    assert opts, "mock payload must exercise optimization sub-screens"
    for oid, meta in opts.items():
        _goto(page, f"#/optimization/{oid}")
        _wait_active(page, "opt-view")
        assert _crumbs(page) == ["Home", "Optimizations", f"#{meta['id']}"], oid
        assert page.inner_text("#opt-detail").strip() != "", oid
    assert errors == []


def test_all_benchmark_pages_render_clean(page):
    page, errors = page
    bench = _payload(page)["benchmark_pages"]
    assert bench, "mock payload must exercise benchmark sub-screens"
    for stage_id, meta in bench.items():
        _goto(page, f"#/bench/{stage_id}")
        _wait_active(page, "bench-view")
        assert _crumbs(page) == ["Home", "Benchmarks", meta["title"]], stage_id
        assert page.inner_text("#bench-detail").strip() != "", stage_id
    assert errors == []


# --- print mode: chrome hidden, summary kept ---------------------------------


def test_print_media_hides_chrome_keeps_summary(page):
    page, errors = page
    page.emulate_media(media="print")
    for sel in ("nav#main-nav", "#crumbs-bar", "#print-btn", "footer",
                "details"):
        assert _print_display(page, sel) == "none", sel
    # Home prints as the stage-menu summary
    assert _print_display(page, "#stage-menu") != "none"
    assert _print_display(page, "h2") != "none"

    # a stage page prints its KPI tiles and verdict plate, not its charts
    _goto(page, "#/stage/tooling_molds")
    _wait_active(page, "stage-view")
    assert _print_display(page, "#stage-stats") != "none"
    assert _print_display(page, "#stage-chart-monthly") == "none"
    page.emulate_media(media="screen")
    assert errors == []
