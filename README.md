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

## Process Explorer

The **Process Explorer** is the dashboard's guided tour of how an action
figure is actually made. The Overview page lists the production stages in
real process order (design → tooling → molding → painting → …), each with a
plain-English description, its total spend and share. Clicking a stage (or
using a URL like `#/stage/tooling_molds`) opens a dedicated page with:

- monthly and daily spend charts (payments by invoice date, not the
  physical production cycle),
- top suppliers and top styles for that stage,
- a **Not booked in this expense ledger** plate on stages whose costs are
  tracked outside these spreadsheets (forensic review verdict), shown
  instead of charts so residual rows are never mistaken for real cost.

The Overview also shows the *ideal production timeline* — a reference Gantt
of typical market durations per stage, every bar linked to its source.

**Regenerate:** `python dashboard/build_dashboard.py` reads the report CSVs
(`audit/stage_summary.csv`, `audit/stages.csv`, `audit/by_month_stage.csv`,
`audit/by_day_stage.csv`, `audit/by_style_stage.csv`,
`audit/by_supplier_stage.csv`, …) and writes the single-file
`dashboard/dist/index.html`. ECharts loads from a CDN; every chart also has
an HTML-table twin, so the page stays readable offline.

**Where the data lives:** all report CSVs and the built `dist/` are
generated artifacts on the local machine only — gitignored together with
`data/` (raw sheets, pickles). Nothing in this repo contains real financial
figures; `scripts/verify.py` cross-checks the embedded stage pages against
the CSVs (series filters, per-page stats, grand-total reconciliation,
non-empty benchmark sources) after every rebuild.
