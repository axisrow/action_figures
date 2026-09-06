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
        "supplier_pages",
        "ideal_timeline",
        "ia",
    }
    assert mock_data["overview"]["tiles"]["total_spend_cny"] > 0
    assert mock_data["overview"]["sankey"]["links"]
    assert len(mock_data["overview"]["sankey"]["top_suppliers"]) <= 12  # top-10 + Others + Unattributed
    assert len(mock_data["suppliers"]["top"]) == 10
    assert mock_data["timelines"]["gantt"][0]["total_days"] >= \
        mock_data["timelines"]["gantt"][-1]["total_days"]
    json.dumps(mock_data)  # JSON-safe


def test_html_embeds_exact_data_payload(html, mock_data):
    start = html.index('id="dash-data"')
    payload = html[html.index(">", start) + 1 : html.index("</script>", start)]
    assert json.loads(payload) == mock_data


def test_html_tabs_and_fallback_tables(html):
    # EI-1 final direction: Home IS the stage menu — no separate overview panel
    assert 'id="home"' in html
    assert 'id="overview"' not in html
    for tab_id in DEEP_DIVE_TABS:
        assert f'id="{tab_id}"' in html
    assert html.count("<table") >= 7  # no-JS fallback twins across screens
    assert 'id="sup-search"' in html  # client-side supplier search
    assert "echarts" in html  # CDN charts


def test_first_tab_visible_without_js(html):
    # EI-1: the home panel must ship with the active class, or the whole
    # page is blank until the first click (regression)
    assert 'id="home" class="tab-panel active"' in html
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


def test_stage_menu_hover_highlights_whole_card(html):
    """Hovering a menu entry must highlight the whole card background, not
    just the stage title (owner feedback)."""
    assert ".stage-menu li:hover" in html
    assert ".stage-menu li:hover { background:" in html


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
    assert "← Back to stage menu" in view
    assert 'id="stage-title"' in view
    assert 'id="stage-desc"' in view
    # content slots PE-3 fills in the next sub-issue
    for slot in ("monthly", "daily", "suppliers", "styles"):
        assert f'id="stage-slot-{slot}"' in view


def test_hash_router_defaults_to_home(html):
    """EI-1: the empty/unknown hash must land on #/home (the new default),
    not leave a dead screen with no nav highlighted."""
    router = html.split("function route()", 1)[1].split(
        "window.addEventListener('hashchange'", 1
    )[0]
    assert "IA.default_hash" in router  # unguarded fallback to home
    assert "showTab('overview');" not in router


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


def test_html_stage_page_daily_chart_guards_empty_days(html):
    """Stages booked in stage_summary but absent from by_day_stage (mock:
    design_prototyping) must not crash the page — dailyOption returns an
    empty-but-valid option instead of dereferencing days[0] (PR 20 review)."""
    fn = html.split("function dailyOption(", 1)[1].split("\n  }", 1)[0]
    assert fn.index("if (!days.length)") < fn.index("days[0].date")


def test_html_stage_page_header_disclaimer(html):
    assert "payments by date, not the physical production cycle" in html


def test_html_stage_page_not_booked_plate(html):
    assert "Not booked in this expense ledger" in html
    assert 'id="stage-plate"' in html
    # the plate must not claim the page is empty while tables show residual
    # booked rows beneath it (PR 20 review)
    assert "residual entries" in html


def test_html_stage_page_renders_avg_line_stat(html):
    assert "Avg per line" in html


# --- EI-3 (GH#28): supplier cards + clickable catalog ----------------------


def test_mock_payload_has_supplier_pages_for_every_supplier(mock_data):
    pages = mock_data["supplier_pages"]
    assert set(pages) == {s["supplier"] for s in mock_data["suppliers"]["all"]}
    assert "Unattributed" in pages
    page = pages["Ningbo Tooling Co"]
    assert page["months"]  # legacy mock rows carry per-month amounts
    assert page["stage_mix"][0]["stage"] == "tooling_molds"
    assert page["stats"]["months_active"] >= 1
    assert pages["Unattributed"]["is_unattributed"] is True


def test_mock_supplier_pages_totals_reconcile(mock_data):
    """Card totals must equal the catalog table totals (acceptance)."""
    pages = mock_data["supplier_pages"]
    for s in mock_data["suppliers"]["all"]:
        assert pages[s["supplier"]]["stats"]["total_cny"] == s["amount_cny"]


def test_html_supplier_view_skeleton(html):
    view = html.split('id="supplier-view"', 1)[1].split("</section>", 1)[0]
    assert 'id="supplier-title"' in view
    assert 'id="supplier-stats"' in view
    assert 'id="supplier-chart-mix"' in view
    assert 'id="supplier-chart-monthly"' in view
    assert 'id="supplier-tbl-styles"' in view
    assert 'id="supplier-forensics"' in view
    # back button targets the shell's Suppliers tab route
    assert 'href="#/tab/suppliers"' in view
    assert "← Back to suppliers" in view


def test_html_supplier_catalog_rows_are_clickable(html):
    """Every catalog table row links to #/supplier/<encoded name>."""
    import json
    import urllib.parse

    payload = html[html.index(">", html.index('id="dash-data"')) + 1:
                   html.index("</script>", html.index('id="dash-data"'))]
    names = [s["supplier"] for s in json.loads(payload)["suppliers"]["all"]]
    table = html.split('class="supplier-table"', 1)[1].split("</table>", 1)[0]
    hrefs = [urllib.parse.unquote(h) for h in
             __import__("re").findall(r'href="#/supplier/([^"]+)"', table)]
    assert hrefs == names  # every row, in catalog order (Unattributed last)


def test_html_supplier_cards_link_to_subscreen(html):
    import re

    cards = html.split('id="sup-cards"', 1)[1].split("<table", 1)[0]
    assert len(re.findall(r'href="#/supplier/', cards)) == 10  # top-10 cards


def test_html_supplier_router_decodes_names(html):
    """zh supplier names travel URL-encoded; the router must decode before
    the payload lookup or every real-data card 404s into Home."""
    router = html.split("function route()", 1)[1].split(
        "window.addEventListener('hashchange'", 1
    )[0]
    assert "#\\/supplier\\/" in router
    assert "decodeURIComponent" in router
    assert "supplierPages" in router
    # supplier pages ride the shell's breadcrumbs + nav deactivation
    assert "crumbItems(['Home', 'Suppliers'," in router
    assert "setNav('')" in router


def test_html_unattributed_card_forensics_text(html):
    """The Unattributed page carries the forensic explanation (lump sums,
    mold prepayments) from the payload — rendered client-side."""
    assert "lump-sum internal transfers" in html
    assert "mold prepayments" in html


# --- EI-1: IA spec + design tokens + app shell (nav/breadcrumbs/router) ---

DEEP_DIVE_TABS = ["cost", "timelines", "suppliers", "benchmarks",
                  "optimizations", "glossary"]


def test_payload_has_ia_route_table(mock_data):
    ia = mock_data["ia"]
    assert ia["default_hash"] == "#/home"
    # old addresses keep working via redirects
    assert ia["redirects"]["#/overview"] == "#/home"
    routes = {r["hash"]: r for r in ia["routes"]}
    assert routes["#/home"]["title"] == "Home"
    assert "#/tab/overview" not in routes  # Home IS the stage menu now
    for tid in DEEP_DIVE_TABS:
        assert f"#/tab/{tid}" in routes
    # every screen carries breadcrumbs rooted at Home
    assert all(r["crumbs"][0] == "Home" for r in ia["routes"])
    # tab titles in the route table match the rendered TABS
    assert routes["#/tab/cost"]["title"] == "Cost structure"


def test_html_nav_header_home_deep_dive(html):
    assert 'id="main-nav"' in html
    assert '<a href="#/home">Home</a>' in html
    # Home IS the stage menu — a duplicate nav entry would be dead weight
    assert '<a href="#/tab/overview">Stage menu</a>' not in html
    # Deep dive ▾ dropdown carries every deep-dive tab
    assert "Deep dive ▾" in html
    dd = html.split("Deep dive ▾", 1)[1].split("</details>", 1)[0]
    for tid in DEEP_DIVE_TABS:
        assert f'href="#/tab/{tid}"' in dd


def test_html_breadcrumbs_and_back_on_every_screen(html):
    assert 'id="crumbs"' in html
    assert 'id="back-link"' in html
    # JS fills crumbs for tab routes and stage pages alike
    assert "function crumbsRender(" in html


def test_html_router_redirects_old_hashes(html):
    """'#/overview' (old default) must redirect, not render as-is."""
    assert "REDIRECTS" in html
    assert '"#/overview": "#/home"' in html  # in the payload


def test_html_router_maps_tab_hashes(html):
    router = html.split("function route()", 1)[1].split(
        "window.addEventListener('hashchange'", 1
    )[0]
    assert "#/tab/" in html
    assert "location.replace" in router  # redirects keep no dead history entry


def test_html_old_tabs_content_unchanged(html):
    """Deep-dive tab panels stay in the DOM with their ids — only routing
    moved; the overview panel is gone entirely (Home is the stage menu)."""
    assert 'id="overview"' not in html
    for tid in DEEP_DIVE_TABS:
        assert f'id="{tid}"' in html
    assert 'role="tabpanel"' in html


def test_html_stage_back_link_points_home(html):
    view = html.split('id="stage-view"', 1)[1].split("</section>", 1)[0]
    assert 'href="#/home"' in view


def test_html_design_tokens_present(html):
    import re

    for tok in ["--kpi-size", "--kpi-label-size", "--h2-size", "--text-sm",
                "--space-1", "--card-radius", "--card-shadow", "--card-bg",
                "--status-good", "--status-warn", "--status-bad",
                "--status-neutral", "--accent"]:
        assert tok in html, tok
    m = re.search(r"--kpi-size:\s*(\d+)px", html)
    assert m and 40 <= int(m.group(1)) <= 48  # large KPI per IA spec
    # tokens are actually applied, not just declared
    assert "font-size: var(--kpi-size)" in html


def test_home_screen_is_stage_menu_only(html):
    """EI-1 final direction (owner, 2026-09-06): Home IS the stage menu and
    nothing else — data-quality notes live on Cost, money flow on Cost, the
    ideal timeline on Timelines."""
    home = html.split('id="home"', 1)[1].split("</section>", 1)[0]
    assert 'id="stage-menu"' in home
    assert 'id="stage-other"' in home
    assert "Stage menu (no-JS fallback)" in home
    for absent in ("tile kpi", "exec", "Data quality:", "Start here",
                   "Where does the money go?", "chart-sankey", "chart-ideal",
                   'href="#/tab/'):
        assert absent not in home, absent


def test_docs_ia_spec_exists_and_public_safe():
    ia_md = Path(__file__).resolve().parent.parent / "docs" / "ia.md"
    assert ia_md.exists()
    text = ia_md.read_text(encoding="utf-8")
    # principles from the brief
    assert "5-second" in text
    assert "One question per screen" in text
    assert "breadcrumb" in text.lower()
    # the repo is public: no real money figures in the spec
    assert "¥" not in text


def test_ia_tabs_match_rendered_tabs():
    """IA_TABS (payload routes) and TABS (rendered nav) must list the same
    tab ids in the same order — drift would make the nav link to a route the
    router silently drops to Home (PR 33 review)."""
    from action_figures.dashboard_data import IA_TABS

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    assert IA_TABS == [tid for tid, _title, _fn in bd.TABS]
