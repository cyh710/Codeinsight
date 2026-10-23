"""统一 SQLite 连接工厂。

移植自 Tapestry（`ai-companion-agent` @ `agent-v1`，Apache-2.0）的
`backend/storage/sqlite.py`，见 `docs/ported-from-tapestry.md`。

要点保持一致：
- 每个连接都要设安全 pragma（WAL / busy_timeout / synchronous），
  不能让不同模块对同一个 db 文件用不同的锁行为。
- `check_same_thread` 保持开启：**后台线程必须在自己线程内开连接**。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

BUSY_TIMEOUT_MS = 5_000

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def open_sqlite(path: str | Path, *, row_factory: bool = False) -> sqlite3.Connection:
    """打开一个已配置 pragma 的连接。"""
    conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_MS / 1000)
    if row_factory:
        conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    """建表（幂等）。

    schema.sql 里全部是 `IF NOT EXISTS`，所以重复执行安全。
    FTS5 虚表和触发器也在里面，增量更新时不需要额外维护。
    """
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def db_path(data_dir: str | Path, name: str = "codeinsight.db") -> Path:
    """索引库的落盘位置。"""
    return Path(data_dir) / name
