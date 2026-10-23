"""索引主流程（符号/边/入口/依赖落库）。

用**真的 git 仓库**做端到端测试：临时目录里 `git init`、写几个文件、提交，
然后跑 `index_project`，最后直接查 SQLite 断言。

不 mock git 也不 mock SQLite——这两处的行为（`ls-tree` 的路径转义、
`cat-file --batch` 的输出格式、外键级联）正是最容易出错的地方，
mock 掉就等于没测。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from codeinsight.cognitive.indexing.indexer import index_project

PYPROJECT = """\
[project]
name = "demo"
version = "0.1.0"
dependencies = [
    "fastapi>=0.115",
    "pydantic-settings>=2.5",
]

[project.scripts]
demo = "pkg.main:main"

[project.optional-dependencies]
dev = ["pytest>=8.0"]
"""

MAIN_PY = '''\
"""演示包的入口。"""

from .core import helper, Widget


def main() -> None:
    """跑一下。"""
    helper()
    Widget().run()


if __name__ == "__main__":
    main()
'''

CORE_PY = '''\
"""核心逻辑。"""

import os


def helper() -> int:
    """帮忙。"""
    return len(os.getcwd())


class Widget:
    """小组件。"""

    def run(self) -> None:
        """跑。"""
        helper()
'''

VENDOR_PY = '''\
"""第三方代码（不该进检索，但 import 边要留）。"""

from .core import helper


def vendored() -> int:
    return helper()
'''

TEST_PY = """\
from pkg.core import helper


def test_helper():
    assert helper() >= 0
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def demo_repo(tmp_path: Path) -> Path:
    """一个包含各种边界情况的小仓库。"""
    repo = tmp_path / "demo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "pkg" / "core.py").write_text(CORE_PY, encoding="utf-8")
    (repo / "pkg" / "main.py").write_text(MAIN_PY, encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_core.py").write_text(TEST_PY, encoding="utf-8")
    (repo / "vendor").mkdir()
    (repo / "vendor" / "lib.py").write_text(VENDOR_PY, encoding="utf-8")
    (repo / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (repo / "requirements.txt").write_text(
        "requests>=2.31\n# 注释\n-r other.txt\n", encoding="utf-8"
    )

    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo


@pytest.fixture
def indexed(demo_repo: Path, tmp_path: Path):
    db = tmp_path / "ci.db"
    result = index_project(db, root=demo_repo, name="demo")
    return result, db


def _rows(db: Path, sql: str, *params):
    import sqlite3

    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def test_index_reports_expected_counts(indexed) -> None:
    result, _ = indexed
    assert result.files == 7
    # pkg, pkg.core, pkg.main, tests.test_core, vendor.lib
    assert result.modules == 5
    assert result.symbols > 0
    assert result.skipped == 0


def test_symbol_qualnames_are_fully_qualified(indexed) -> None:
    _, db = indexed
    quals = {r[0] for r in _rows(db, "SELECT qualname FROM symbol")}
    assert "pkg.core.helper" in quals
    assert "pkg.core.Widget" in quals
    assert "pkg.core.Widget.run" in quals
    assert "pkg.main.main" in quals


def test_parent_symbol_is_linked(indexed) -> None:
    _, db = indexed
    rows = _rows(
        db,
        """
        SELECT child.qualname, parent.qualname
        FROM symbol child JOIN symbol parent ON child.parent_symbol_id = parent.id
        """,
    )
    pairs = set(rows)
    assert ("pkg.core.Widget.run", "pkg.core.Widget") in pairs


def test_relative_import_edge_resolves_to_module(indexed) -> None:
    """`from .core import helper` 要能落到 `pkg.core` 这个模块符号上。"""
    _, db = indexed
    rows = _rows(
        db,
        """
        SELECT e.dst_name, d.qualname
        FROM edge e JOIN symbol d ON d.id = e.dst_symbol_id
        WHERE e.kind = 'imports'
        """,
    )
    assert ("pkg.core", "pkg.core") in rows


def test_cross_file_call_edge_resolves(indexed) -> None:
    """`pkg.main` 里调用 `helper()`，要解析到 `pkg.core.helper`。"""
    _, db = indexed
    rows = _rows(
        db,
        """
        SELECT e.src_qualname, e.dst_qualname
        FROM edge e
        WHERE e.kind = 'call' AND e.dst_symbol_id IS NOT NULL
        """,
    )
    assert ("pkg.main.main", "pkg.core.helper") in rows


def test_resolved_edge_qualname_matches_its_target(indexed) -> None:
    """`dst_qualname` 必须和 `dst_symbol_id` 指的是同一个东西。

    否则读边的人会看到「名字是 A、指向的却是 B」——
    这正是「边指向了错误的符号」这种假数据最隐蔽的形态。
    """
    _, db = indexed
    rows = _rows(
        db,
        """
        SELECT e.dst_qualname, s.qualname
        FROM edge e JOIN symbol s ON s.id = e.dst_symbol_id
        """,
    )
    assert rows
    assert all(row[0] == row[1] for row in rows)


def test_builtin_call_is_not_resolved(indexed) -> None:
    """`len(...)` 是内置函数——`dst_symbol_id` 必须留 NULL，不能瞎指一个同名符号。"""
    _, db = indexed
    rows = _rows(
        db,
        "SELECT dst_name FROM edge WHERE kind = 'call' AND dst_name = 'len'",
    )
    assert rows
    assert _rows(db, "SELECT dst_symbol_id FROM edge WHERE kind = 'call' AND dst_name = 'len'") == [
        (None,)
    ]


def test_file_roles_are_classified(indexed) -> None:
    _, db = indexed
    roles = dict(_rows(db, "SELECT path, role FROM file"))
    assert roles["pkg/core.py"] == "source"
    assert roles["tests/test_core.py"] == "test"
    assert roles["vendor/lib.py"] == "vendored"
    assert roles["pyproject.toml"] == "config"


def test_entry_points_are_found(indexed) -> None:
    _, db = indexed
    rows = _rows(db, "SELECT kind, target FROM entry_point")
    kinds = {r[0] for r in rows}
    assert "file" in kinds
    assert "console_script" in kinds
    targets = {r[1] for r in rows}
    assert any(t.startswith("demo = pkg.main:main") for t in targets)


def test_dependencies_come_from_declarations_and_imports(indexed) -> None:
    _, db = indexed
    rows = dict(_rows(db, "SELECT name, source FROM dependency"))
    assert rows["fastapi"] == "pyproject"
    assert rows["pytest"] == "pyproject"
    assert rows["requests"] == "requirements"
    # 自己的包不是依赖
    assert "pkg" not in rows
    assert "vendor" not in rows


def test_stdlib_is_not_listed_as_dependency(indexed) -> None:
    _, db = indexed
    names = {r[0] for r in _rows(db, "SELECT name FROM dependency")}
    assert "os" not in names


def test_reindex_is_idempotent(indexed, demo_repo: Path) -> None:
    """重跑一次索引，数据量不该翻倍。"""
    _, db = indexed
    before = _rows(db, "SELECT COUNT(*) FROM symbol")[0][0]
    edges_before = _rows(db, "SELECT COUNT(*) FROM edge")[0][0]
    index_project(db, root=demo_repo, name="demo")
    assert _rows(db, "SELECT COUNT(*) FROM symbol")[0][0] == before
    assert _rows(db, "SELECT COUNT(*) FROM edge")[0][0] == edges_before


def test_syntax_error_file_does_not_break_index(demo_repo: Path, tmp_path: Path) -> None:
    """坏文件降级成空符号集，不能让整次索引失败（ADR 0012）。"""
    (demo_repo / "pkg" / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    _git(demo_repo, "add", "-A")
    _git(demo_repo, "commit", "-m", "broken")

    db = tmp_path / "ci.db"
    result = index_project(db, root=demo_repo, name="demo")
    assert result.skipped == 1
    assert result.symbols > 0
