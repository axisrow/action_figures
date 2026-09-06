"""Shared synthetic xlsx fixtures.

All fixtures are 100% FAKE data with realistic Chinese column names
(序号 日期 款号 批 报销事项 数量 单价 单位 金额 用途 供应商 备注).
No real financial data ever enters this repo or its tests.
"""

import random
import subprocess
from pathlib import Path

import pandas as pd
import pytest

ZH_COLUMNS = [
    "序号",
    "日期",
    "款号",
    "批",
    "报销事项",
    "数量",
    "单价",
    "单位",
    "金额",
    "用途",
    "供应商",
    "备注",
]

# Fake values for random generation — deliberately invented, not from any real file.
ITEMS = ["开模", "注塑", "喷油", "丝印", "组装", "包装", "运费", "原料", "检测", "设计"]
STYLES = ["AF-1001", "AF-1002", "AF-1003", "AF-2001", "AF-2002"]
BATCHES = ["A", "B", "C", "D"]
UNITS = ["个", "套", "件", "公斤"]
SUPPLIERS = ["杭州宏达", "东莞精密", "深圳彩印", "宁波货运", "广州艺品"]
PURPOSES = ["生产用", "样品", "批量订单", "试产"]


def make_fake_frame(n_rows: int = 10, seed: int = 42) -> pd.DataFrame:
    """Deterministic fake reimbursement rows with the real zh column names."""
    if not 1 <= n_rows <= 1000:
        raise ValueError("n_rows must be between 1 and 1000")
    rng = random.Random(seed)
    rows = []
    for i in range(1, n_rows + 1):
        qty = rng.randint(1, 500)
        price = rng.choice([0.5, 1.2, 3.8, 12.0, 45.0, 120.0, 1500.0])
        rows.append(
            {
                "序号": i,
                "日期": f"2026-0{rng.randint(1, 6)}-{rng.randint(10, 28):02d}",
                "款号": rng.choice(STYLES),
                "批": rng.choice(BATCHES),
                "报销事项": rng.choice(ITEMS),
                "数量": qty,
                "单价": price,
                "单位": rng.choice(UNITS),
                "金额": round(qty * price, 2),
                "用途": rng.choice(PURPOSES),
                "供应商": rng.choice(SUPPLIERS),
                "备注": "",
            }
        )
    return pd.DataFrame(rows, columns=ZH_COLUMNS)


@pytest.fixture(scope="session")
def fake_df() -> pd.DataFrame:
    """Medium synthetic frame: 10 rows, all zh columns present."""
    return make_fake_frame(n_rows=10, seed=42)


@pytest.fixture()
def fake_xlsx(tmp_path) -> Path:
    """Synthetic single-sheet xlsx file (5-20 fake rows) on disk."""
    path = tmp_path / "fake_reimbursement.xlsx"
    make_fake_frame(n_rows=12, seed=7).to_excel(path, index=False)
    return path


# --- Ingest-style fixture: title row + zh header + 3 data rows (all fake) ---

ZH_HEADER = ["序号", "日期", "款号", "报销事项", "单位", "数量", "单价", "金额", "用途", "供应商", "备注"]


def _fake_rows():
    # title row, header row, 3 data rows; date: serial, text, empty
    return [
        ["5月份费用报销明细"] + [None] * 10,
        ZH_HEADER[:],
        [1, 46146, "AF-1003", "过朴费测试", "码", 16, 2.3, 36.8, "测试用布料", "杭州宏达", None],
        [2, 46146, "AF-1001", "运费测试", "个", 2, 13, 26, "收测试布", "星辰快运", None],
        [3, "2026/5/19", "AF-1002", "买测试皮料", "尺", 20, 16, 320, "测试布件用", "华丰皮具", None],
    ]


@pytest.fixture()
def ingest_xlsx(tmp_path) -> Path:
    """Synthetic xlsx mimicking real reimbursement sheet shape (fake values only)."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "5月份"
    for row in _fake_rows():
        ws.append(row)
    # «пустая стилизованная» ячейка и стилизованные пустые хвостовые строки
    ws.cell(row=6, column=1).style = "Bad"
    ws.cell(row=7, column=4).style = "Bad"
    ws.cell(row=3, column=13).style = "Bad"  # лишняя хвостовая колонка
    path = tmp_path / "fake_ingest.xlsx"
    wb.save(path)
    return path


# --- Synthetic git repo for hygiene checks (mirrors the real repo layout) ---


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "HOME": str(repo),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    ).stdout


def init_repo(repo: Path) -> Path:
    """Empty git repo whose .gitignore matches the real one (data/reports/issues)."""
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "T")
    (repo / ".gitignore").write_text("data/\nreports/\nissues/\n*.xls\n*.xlsx\n*.pkl\n")
    (repo / "README.md").write_text("synthetic repo\n")
    git(repo, "add", ".gitignore", "README.md")
    git(repo, "commit", "-q", "-m", "init")
    return repo
