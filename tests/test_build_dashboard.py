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
    assert html.count("<table") >= 6  # no-JS fallbacks for every data tab
    assert 'id="sup-search"' in html  # client-side supplier search
    assert "echarts" in html  # CDN charts


def test_main_writes_dist_index(tmp_path, monkeypatch):
    out = tmp_path / "dist" / "index.html"
    rc = bd.main(["--reports", str(tmp_path / "missing_reports"), "--out", str(out)])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!DOCTYPE html>")
    assert "MOCK synthetic data" in text
