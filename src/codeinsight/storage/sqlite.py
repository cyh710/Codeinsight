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

SCHEMA_VERSION = 3
"""schema 版本号，写进 `PRAGMA user_version`。

改 `schema.sql` 的表结构时**必须**把这里 +1 并补一条迁移，
否则老库不会升级，`CREATE TABLE IF NOT EXISTS` 也不会给已存在的表补列——
结果是运行时才炸。
"""

# 从 `user_version = N` 升到 `N + 1` 需要的 SQL 步骤。
# 键是**旧版本号**，值是升级到该键+1 的步骤序列。
# 迁移是**原地**的，不删库、不重建——用户的索引数据不能因为 schema 演进而丢。
MIGRATIONS: dict[int, tuple[str, ...]] = {
    2: (),  # 新会话表由 apply_schema 原地创建，账本回填由会话仓储幂等执行。
    1: (
        "CREATE TABLE IF NOT EXISTS concept_rule_version ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, fingerprint TEXT NOT NULL UNIQUE)",
    ),
    0: (
        # file.role 单列取代三个布尔列（ADR 0014）。
        # 先加列并回填，再删旧列——SQLite 的 DROP COLUMN 需要 3.35+。
        "ALTER TABLE file ADD COLUMN role TEXT NOT NULL DEFAULT 'source'",
        (
            "UPDATE file SET role = CASE "
            "WHEN is_vendored = 1 THEN 'vendored' "
            "WHEN is_generated = 1 THEN 'generated' "
            "WHEN is_test = 1 THEN 'test' "
            "ELSE 'source' END"
        ),
        "ALTER TABLE file DROP COLUMN is_generated",
        "ALTER TABLE file DROP COLUMN is_vendored",
        "ALTER TABLE file DROP COLUMN is_test",
    ),
}


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

    **只建对象，不改已有对象**——它不是迁移函数。
    版本不一致时走 `ensure_schema()`。
    """
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def ensure_schema(path: str | Path) -> str:
    """确保 db 文件的 schema 是当前版本，返回这次做了什么。

    返回值：`created`（新建库）· `current`（已是当前版）· `migrated`（升级过）。

    升级是**原地**的：跑 `MIGRATIONS` 里的 SQL，再补建新表，最后更新 `user_version`。
    已有的索引数据（符号、边、块）不会丢——schema 演进不该让用户重新索引一次。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        with open_sqlite(path) as conn:
            apply_schema(conn)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.commit()
        return "created"

    with open_sqlite(path) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            # 已是当前版：再跑一遍 apply_schema 补上新增的索引/触发器（幂等）。
            apply_schema(conn)
            return "current"

        if version > SCHEMA_VERSION:
            # 库比代码新——多半是拿了旧版本代码打开新库。降级会丢数据，明确报错。
            raise RuntimeError(
                f"索引库 schema 版本是 {version}，高于当前代码支持的 {SCHEMA_VERSION}；"
                "请升级 CodeInsight 或换一个数据目录。"
            )

        for old in range(version, SCHEMA_VERSION):
            steps = MIGRATIONS.get(old)
            if steps is None:
                raise RuntimeError(f"缺少从 schema 版本 {old} 升级到 {old + 1} 的迁移")
            for sql in steps:
                conn.execute(sql)
        apply_schema(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    return "migrated"


def db_path(data_dir: str | Path, name: str = "codeinsight.db") -> Path:
    """索引库的落盘位置。"""
    return Path(data_dir) / name
