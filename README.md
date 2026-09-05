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
