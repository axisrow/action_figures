"""Tests for the dashboard HTML generator (mock data path + payload fidelity)."""

import copy
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
        "stages",
        "stage_pages",
        "ideal_timeline",
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
    assert "M8 18h6" in svg  # A has a crossbar, or 16px tabs read a caret


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


# --- UX pass 2: headings/hints, Unattributed, gantt notes & sort ---------


def test_html_has_no_unknown_label(html):
    assert "(unknown)" not in html


def test_html_every_chart_has_heading_and_hint(html):
    headings = [
        "Money flow: spend → stages → suppliers",  # overview sankey
        "Total spend by stage",  # cost bar
        "Monthly spend by stage",  # cost stacked
        "Share of total spend",  # cost treemap
        "Month × stage heatmap",  # cost heatmap
        "Production timeline per style",  # gantt
        "Ours vs market range",  # benchmarks
        "Ideal production timeline (reference)",  # ideal gantt
    ]
    for heading in headings:
        assert f"<h3>{heading}</h3>" in html
    assert html.count('class="hint"') >= len(headings)  # one hint per chart


@pytest.fixture()
def patched_html(mock_data):
    """Mock payload with UX-pass-2 fields forced on (notes must show up)."""
    data = copy.deepcopy(mock_data)
    data["timelines"]["gantt"] = (data["timelines"]["gantt"] * 10)[:25]
    data["timelines"]["gantt_truncated"] = True
    data["timelines"]["gantt_total_styles"] = 95
    data["timelines"]["unlinked"] = {"n_lines": 12, "amount_cny": 3456.0}
    ua = {"n_lines": 34, "amount_cny": 118048.0, "share_pct": 31.6}
    data["suppliers"]["unattributed"] = ua
    data["overview"]["unattributed"] = ua
    return bd.render_html(data, "MOCK synthetic data (test)")


def test_html_gantt_truncation_note_visible(patched_html):
    assert "Showing top 25 of 95 styles by spend" in patched_html
    assert "by_style_timeline.csv" in patched_html


def test_html_gantt_unlinked_footnote(patched_html):
    assert "12 lines / ¥3,456 not linked to a style" in patched_html


def test_html_gantt_unlinked_footnote_without_amount(mock_data):
    data = copy.deepcopy(mock_data)
    data["timelines"]["unlinked"] = {"n_lines": 7, "amount_cny": 0.0}
    html2 = bd.render_html(data, "MOCK synthetic data (test)")
    assert "7 lines not linked to a style" in html2


def test_html_gantt_sort_control(html):
    assert 'id="gantt-sort"' in html
    assert "By total spend" in html
    assert "By duration" in html


def test_html_unattributed_callout_and_explainer(patched_html):
    # overview data-quality callout
    assert "31.6% of spend is unattributed to a supplier" in patched_html
    # suppliers-tab explainer line
    assert (
        "34 rows / ¥118,048 (31.6% of spend) have no supplier recorded "
        "— lump-sum internal payments" in patched_html
    )
    assert "Unattributed" in patched_html


# --- PE-2: stage menu + hash routing skeleton (Process Explorer) ----------

PRODUCTION_STAGES = [
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
]


def test_payload_stages_lists_all_12_in_process_order(mock_data):
    stages = mock_data["stages"]
    assert [s["stage_id"] for s in stages] == PRODUCTION_STAGES + [
        "admin_other",
        "unclassified",
    ]
    assert [s["order"] for s in stages] == list(range(1, 13))
    assert sum(s["service"] for s in stages) == 2
    # every menu entry carries its metadata + money numbers
    assert all(
        {"stage_id", "order", "label_en", "description_en",
         "amount_cny", "share_pct"} <= set(s)
        for s in stages
    )


def test_stage_menu_lists_ten_production_stages_in_order(html):
    assert "<h3>How an action figure is made — 10 stages</h3>" in html
    menu = html.split('id="stage-menu"', 1)[1].split('id="stage-other"', 1)[0]
    import re

    assert re.findall(r'href="#/stage/([\w-]+)"', menu) == PRODUCTION_STAGES


def test_stage_menu_amounts_match_stage_summary(html):
    # the mock stage_summary row: tooling_molds 182000.00 / 28.4
    item = html.split('href="#/stage/tooling_molds"', 1)[1]
    assert "¥182,000 · 28.4%" in item


def test_service_stages_collapsed_into_other(html):
    assert '<details id="stage-other">' in html  # no `open` attribute — collapsed
    other = html.split('id="stage-other"', 1)[1].split("</details>", 1)[0]
    import re

    assert re.findall(r'href="#/stage/([\w-]+)"', other) == [
        "admin_other",
        "unclassified",
    ]


def test_stage_menu_nojs_fallback_table(html):
    table = html.split("Stage menu (no-JS fallback)", 1)[1].split("</table>", 1)[0]
    assert table.count("<tr>") == 13  # header row + all 12 stages
    assert "Design &amp; Prototyping" in table
    assert "Unclassified" in table


def test_hash_router_and_stage_page_skeleton(html):
    assert "addEventListener('hashchange'" in html  # back/forward support
    view = html.split('id="stage-view"', 1)[1].split("</section>", 1)[0]
    assert "← Back to overview" in view
    assert 'id="stage-title"' in view
    assert 'id="stage-desc"' in view
    # content slots PE-3 fills in the next sub-issue
    for slot in ("monthly", "daily", "suppliers", "styles"):
        assert f'id="stage-slot-{slot}"' in view


def test_hash_router_defaults_to_overview(html):
    """Back from a stage page to the entry URL with the empty hash fires
    hashchange with a hash matching neither route — the router must land on
    the overview tab, not leave a dead stage view with no tab highlighted
    (review on PR 19)."""
    router = html.split("function route()", 1)[1].split(
        "window.addEventListener('hashchange'", 1
    )[0]
    # unguarded fallback: any non-stage hash (empty, '#/overview', stray)
    assert "showTab('overview');" in router
    assert "location.hash === '#/overview'" not in router


# --- PE-4: ideal production timeline (reference Gantt on the Overview) ----


def test_payload_has_ideal_timeline_section(mock_data):
    it = mock_data["ideal_timeline"]
    assert it["weeks_axis"] == [0, 26]
    assert it["bars"]
    assert all(b["source_url"].startswith("https://") for b in it["bars"])


def test_html_ideal_timeline_heading_and_disclaimer(html):
    assert "<h3>Ideal production timeline (reference)</h3>" in html
    assert (
        "typical durations from market benchmarks; our payment dates are "
        "not the physical cycle" in html
    )
    assert 'id="chart-ideal"' in html


def test_html_ideal_timeline_nojs_fallback_table(html):
    """Static twin: stage → week range → typical duration → source link."""
    table = html.split("Ideal timeline (no-JS fallback)", 1)[1]
    table = table.split("</table>", 1)[0]
    # one row per reference bar, read from the embedded payload
    import json

    payload = html[html.index(">", html.index('id="dash-data"')) + 1:
                   html.index("</script>", html.index('id="dash-data"'))]
    bars = json.loads(payload)["ideal_timeline"]["bars"]
    assert table.count("<tr>") == 1 + len(bars)
    # week range of the first bar (design: week 0 → …) is in the table
    first = bars[0]
    assert f'{first["start_week"]}–{first["end_week"]}' in table
    # every source row links out to its benchmark URL
    for b in bars:
        assert f'href="{b["source_url"]}"' in table


def test_html_ideal_gantt_click_routes_to_stage_page(html):
    """The ideal-gantt bar click handler must navigate to #/stage/<id>."""
    ideal_js = html.split("chart-ideal", 1)[1]
    assert "location.hash = '#/stage/' +" in ideal_js


# --- PE-3: stage page content (charts, tables, stats, plate) --------------


def test_mock_payload_has_stage_pages_for_all_12(mock_data):
    pages = mock_data["stage_pages"]
    assert set(pages) == {s["stage_id"] for s in mock_data["stages"]}
    # every booked production stage carries both series and both tables
    tooling = pages["tooling_molds"]
    assert tooling["months"] and tooling["days"]
    assert tooling["top_suppliers"] and tooling["top_styles"]
    assert set(tooling["stats"]) == {
        "total_cny", "share_pct", "n_lines", "avg_line_cny",
    }
    # synthetic stand-in for the real grand-total check (¥373,437.41)
    assert sum(p["stats"]["total_cny"] for p in pages.values()) == (
        mock_data["overview"]["tiles"]["total_spend_cny"]
    )


def test_mock_stage_pages_top_lists_capped_at_10(mock_data):
    for page in mock_data["stage_pages"].values():
        assert len(page["top_suppliers"]) <= 11  # top-10 + Unattributed
        assert len(page["top_styles"]) <= 10


def test_html_stage_page_charts_and_tables_present(html):
    assert 'id="stage-chart-monthly"' in html
    assert 'id="stage-chart-daily"' in html
    assert 'id="stage-tbl-suppliers"' in html
    assert 'id="stage-tbl-styles"' in html


def test_html_stage_page_daily_chart_smooths_with_ma7(html):
    """The daily line carries a 7-day moving average series (calendar-filled)."""
    assert "ma7" in html
    assert "86400000" in html  # calendar day step when filling gaps


def test_html_stage_page_header_disclaimer(html):
    assert "payments by date, not the physical production cycle" in html


def test_html_stage_page_not_booked_plate(html):
    assert "Not booked in this expense ledger" in html
    assert 'id="stage-plate"' in html


def test_html_stage_page_renders_avg_line_stat(html):
    assert "Avg per line" in html
