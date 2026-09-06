# Action Figures — Production Cost Audit Pipeline

[![CI](https://github.com/axisrow/action_figures/actions/workflows/ci.yml/badge.svg)](https://github.com/axisrow/action_figures/actions/workflows/ci.yml)

> **⚠️ Financial data never enters this repo.** Raw expense files, pickle
> datasets, and generated reports live only on the local machine and are
> excluded via `.gitignore` (`data/`, `reports/`, `issues/`, `dashboard/dist/`,
> `*.xls`, `*.xlsx`, `*.pkl`). Only code and synthetic test fixtures are
> committed — every test fixture is 100% fake data with realistic Chinese
> column names.

## What it does

Pipeline that audits action figure production costs from Chinese expense
reimbursement files (费用报销明细, Jan–Jun 2026): ingestion → dictionary-based
translation (zh→en) → stage classification & cost audit → market benchmarks →
optimization recommendations → static HTML dashboard.

Translation status semantics (`data/dict/translation.csv`): `translated`
("ok") — an en translation exists and is used; `gap` ("fallback") — no
translation, consumers fall back to en = zh (reported in
`reports/translation/gaps.md`).

## Layout

```
scripts/     ingest / build_dict / translate / audit / verify
src/         reusable library modules (excel_io, schema, classify, ...)
tests/       pytest suite with synthetic xlsx fixtures (conftest.py)
config/      paths, taxonomy, schema
dashboard/   dashboard builder (dist/ is gitignored)
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

ruff check .   # lint
pytest         # tests (synthetic data only)
```

CI (GitHub Actions) runs `ruff` + `pytest` on Python 3.11 and 3.12.

## Dashboard structure (Executive IA)

The dashboard is one static HTML file (`dashboard/dist/index.html`) with a
client-side hash router. Every screen lives at its own `#/…` address, shows
a breadcrumb trail (`Home › …`) and a `← Back` link — no screen is a dead
end. `#/overview` redirects to `#/home` for old links.

```
#/home                       Executive Home: the stage menu (10 stages + Other)
#/stage/<stage_id>           Stage page: charts, top suppliers/styles, stats
#/tab/cost                   Cost structure (heatmap, monthly totals)
#/tab/timelines              Product timelines (gantt) + ideal timeline
#/tab/suppliers              Supplier catalog → #/supplier/<name> cards
#/tab/benchmarks             Market benchmarks → #/bench/<stage_id> pages
#/tab/optimizations          Savings recommendations → #/optimization/<id>
#/tab/glossary               zh→en glossary
```

- **Home** (`#/home`) IS the stage menu: the production stages in real
  process order (design → tooling → molding → painting → …), each card with
  a plain-English description, total spend and share. Clicking a card (or
  opening `#/stage/tooling_molds`) opens the stage page with monthly/daily
  spend charts (payments by invoice date, not the physical production
  cycle), top suppliers and styles, and — on stages whose costs are tracked
  outside this expense ledger (forensic verdict) — a **Not booked in this
  expense ledger** plate instead of charts.
- **Supplier cards** (`#/supplier/<name>`) show a vendor's total, share,
  stage mix, monthly payments and styles. The blank-supplier bucket gets an
  **Unattributed** card with a forensic explainer, not a fake vendor.
- **Optimization** (`#/optimization/<id>`) and **benchmark**
  (`#/bench/<stage_id>`) sub-screens carry the full what-to-do / savings
  math / market ranges and their sources.
- The **ideal production timeline** (reference Gantt of typical market
  durations per stage) lives on the Timelines tab; every bar links to its
  source. The header has a **Print view** button — print mode drops the
  interactive chrome and prints the current screen as a one-page summary.

**Regenerate:** `python dashboard/build_dashboard.py` reads the report CSVs
(`audit/stage_summary.csv`, `audit/stages.csv`, `audit/by_month_stage.csv`,
`audit/by_day_stage.csv`, `audit/by_style_stage.csv`,
`audit/by_supplier_stage.csv`, …) and writes the single-file
`dashboard/dist/index.html`. ECharts loads from a CDN; every chart also has
an HTML-table twin, so the page stays readable offline.

**Where the data lives:** all report CSVs and the built `dist/` are
generated artifacts on the local machine only — gitignored together with
`data/` (raw sheets, pickles); the absolute roots are in
`config/paths.yaml`. Nothing in this repo contains real financial figures.
`scripts/verify.py` cross-checks every rebuild: every payload route
reconciles against its source CSVs (home stage cards vs
stages×stage_summary, stage/supplier/optimization/benchmark pages vs their
CSVs and reports), the Σ of the Home stage-menu cards equals the grand
total, and the route table is complete — every screen reachable, every
link, breadcrumb and back target resolving (no dead ends).
