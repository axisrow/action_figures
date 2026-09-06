"""Tests for the dashboard HTML generator (mock data path + payload fidelity)."""

import json
import sys
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
sys.path.insert(0, str(DASHBOARD_DIR))

import build_dashboard as bd  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(scope="module")
def mock_data() -> dict:
    return bd.build_mock_data()


@pytest.fixture(scope="module")
def html(mock_data) -> str:
    return bd.render_html(mock_data, "MOCK synthetic data (test)")


def test_mock_data_matches_real_schema(mock_data):
    # same top-level sections the real reports produce
    assert set(mock_data) == {
        "overview",
        "cost_structure",
        "timelines",
        "suppliers",
        "benchmarks",
        "optimizations",
        "glossary",
    }
    assert mock_data["overview"]["tiles"]["total_spend_cny"] > 0
    assert mock_data["overview"]["sankey"]["links"]
    assert len(mock_data["overview"]["sankey"]["top_suppliers"]) <= 11  # top-10 + Others
    assert len(mock_data["suppliers"]["top"]) == 10
    assert mock_data["timelines"]["gantt"][0]["total_days"] >= \
        mock_data["timelines"]["gantt"][-1]["total_days"]
    json.dumps(mock_data)  # JSON-safe


def test_html_embeds_exact_data_payload(html, mock_data):
    start = html.index('id="dash-data"')
    payload = html[html.index(">", start) + 1 : html.index("</script>", start)]
    assert json.loads(payload) == mock_data


def test_html_has_seven_tabs_and_fallback_tables(html):
    for tab_id in ["overview", "cost", "timelines", "suppliers",
                   "benchmarks", "optimizations", "glossary"]:
        assert f'id="{tab_id}"' in html
    assert html.count("<table") >= 7  # no-JS fallbacks + Top suppliers (overview)
    assert 'id="sup-search"' in html  # client-side supplier search
    assert "echarts" in html  # CDN charts


def test_first_tab_visible_without_js(html):
    # the overview panel must ship with the active class, or the whole
    # page is blank until the first click (regression)
    assert 'id="overview" class="tab-panel active"' in html
    assert html.count('class="tab-panel active"') == 1


def test_echarts_cdn_url_is_pinned_and_valid(html):
    # cdnjs never had 5.5.1 (404) — the pinned URL must be one that exists
    import re

    urls = set(re.findall(r'<script src="(https://[^"]+)"', html))
    assert urls == {"https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"}


def test_html_has_inline_svg_favicon(html):
    # the tab icon must be an inline SVG data URI — no /favicon.ico request,
    # so the page never 404s on a missing asset
    import re
    import urllib.parse

    m = re.search(r'<link rel="icon"[^>]*href="([^"]+)"', html)
    assert m, "generated HTML must carry a <link rel=icon>"
    assert m.group(1).startswith("data:image/svg+xml,")
    assert "favicon.ico" not in html
    svg = urllib.parse.unquote(m.group(1).split(",", 1)[1])
    assert svg.startswith("<svg")
    assert "viewBox='0 0 32 32'" in svg  # crisp at any tab size


def test_no_autoloaded_asset_can_404(html):
    # every resource the browser fetches on page load is inline or on the CDN
    import re

    refs = re.findall(r'<(?:script|link)\b[^>]*?\b(?:src|href)="([^"]+)"', html)
    assert refs  # the template declares its assets
    for ref in refs:
        assert ref.startswith(("data:", "https://cdn.jsdelivr.net/")), ref


def test_main_writes_dist_index(tmp_path, monkeypatch):
    out = tmp_path / "dist" / "index.html"
    rc = bd.main(["--reports", str(tmp_path / "missing_reports"), "--out", str(out)])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!DOCTYPE html>")
    assert "MOCK synthetic data" in text


def test_main_logs_dictionary_status(tmp_path, capsys):
    """The dictionary path is layout-dependent — the build log must say
    whether EN supplier labels are active (review note on PR 2)."""
    reports = tmp_path / "reports"
    (reports / "audit").mkdir(parents=True)
    (reports / "audit" / "stage_summary.csv").write_text(
        "stage,n_lines,amount_cny,share_pct\ns1,1,100.00,100.0\n", encoding="utf-8"
    )
    dict_csv = tmp_path / "data" / "dict" / "translation.csv"
    dict_csv.parent.mkdir(parents=True)
    dict_csv.write_text(
        "zh,en,column_hint,n_occurrences,status\n"
        "假供应商甲,Fake Supplier A,supplier,2,translated\n"
        "假供应商乙,Fake Supplier B,supplier,1,translated\n"
        "假动词,Fake Verb,item,9,translated\n",  # non-supplier hint: not counted
        encoding="utf-8",
    )
    out = tmp_path / "dist" / "index.html"
    assert bd.main(["--reports", str(reports), "--out", str(out)]) == 0
    assert "supplier dictionary: 2 entries" in capsys.readouterr().out

    # without the dictionary the fallback must be visible, not silent
    dict_csv.unlink()
    out2 = tmp_path / "dist2" / "index.html"
    assert bd.main(["--reports", str(reports), "--out", str(out2)]) == 0
    assert "supplier dictionary: missing" in capsys.readouterr().out
