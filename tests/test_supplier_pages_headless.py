"""Headless-browser tests for the supplier card sub-screen (GH#28).

Red-first suite: on main the Suppliers tab has no per-supplier pages at all.
Three layers, mirroring test_stage_charts_headless.py:
- integration: click a catalog row, assert the sub-screen fills (title, stats,
  stage-mix and monthly charts, styles table) with no console errors;
- smoke: every supplier page the payload knows (12+ with the mock data)
  opens via its hash without errors;
- unattributed: the forensic explainer renders on the Unattributed card.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("pytest_playwright", reason="headless supplier tests need"
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
    page.goto(dashboard_url)
    page.wait_for_function("typeof echarts !== 'undefined'", timeout=30000)
    yield page, errors
    page.close()


def supplier_names(page) -> list[str]:
    return page.evaluate(
        "JSON.parse(document.getElementById('dash-data').textContent)"
        ".suppliers.all.map(function (s) { return s.supplier; })"
    )


def test_supplier_page_opens_from_catalog_click(page):
    page, errors = page
    # EI-1 shell: tabs live at '#/tab/<id>' behind the Deep dive nav
    page.evaluate("location.hash = '#/tab/suppliers'")
    page.wait_for_selector("#suppliers.active")
    # EI-5: the catalog table hides behind a collapsed "Show details"
    page.evaluate(
        "document.querySelector('.supplier-table')"
        ".closest('details').open = true"
    )
    page.click('.supplier-table a[href^="#/supplier/"]')
    page.wait_for_selector("#supplier-view.active")
    assert page.inner_text("#supplier-title") != ""
    assert "¥" in page.inner_text("#supplier-stats")
    # both charts have non-empty rendered geometry
    for chart_id in ("supplier-chart-mix", "supplier-chart-monthly"):
        box = page.evaluate(
            "function (id) { var c = document.getElementById(id);"
            " return c && c.querySelector('canvas')"
            " ? c.querySelector('canvas').getBoundingClientRect() : null; }",
            chart_id,
        )
        assert box and box["width"] > 0 and box["height"] > 0, chart_id
    assert page.locator("#supplier-tbl-styles table").count() >= 1
    assert errors == []


def test_every_supplier_page_smoke(page):
    """12+ pages (acceptance): every supplier in the payload opens its own
    sub-screen without JS errors and with a non-empty title."""
    page, errors = page
    names = supplier_names(page)
    assert len(names) >= 12
    for name in names:
        page.evaluate(
            "function (n) { location.hash = '#/supplier/'"
            " + encodeURIComponent(n); }", name
        )
        page.wait_for_selector("#supplier-view.active")
        assert page.inner_text("#supplier-title").strip() != "", name
        assert "¥" in page.inner_text("#supplier-stats"), name
    assert errors == []


def test_unattributed_page_shows_forensics(page):
    page, errors = page
    page.evaluate(
        "location.hash = '#/supplier/' + encodeURIComponent('Unattributed')"
    )
    page.wait_for_selector("#supplier-view.active")
    assert not page.locator("#supplier-forensics").is_hidden()
    assert "lump-sum" in page.inner_text("#supplier-forensics")
    assert errors == []


def test_supplier_page_breadcrumbs(page):
    page, errors = page
    page.evaluate(
        "location.hash = '#/supplier/'"
        " + encodeURIComponent('Ningbo Tooling Co')"
    )
    page.wait_for_selector("#supplier-view.active")
    # EI-1 shell renders the trail in the global #crumbs bar; separators
    # carry CSS margins, so compare on whitespace-stripped text
    crumbs = page.evaluate(
        "document.getElementById('crumbs').textContent.replace(/\\s+/g, '')"
    )
    assert crumbs.startswith("Home›Suppliers›")
    assert "NingboToolingCo" in crumbs
    assert errors == []
