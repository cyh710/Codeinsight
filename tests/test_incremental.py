"""增量索引与变更说明（M6）。

验收口径（roadmap）：

    改一个函数后重跑索引：只有相关 chunk 的 `source_sha256` 变化（SQL 断言）。

这条断言是整个 M6 的地基：如果全量重建，所有块都是「新的」，
「哪些知识过期了」就永远没有答案。

用真的 git 仓库：init、提交、改文件、再提交、跑增量。
"""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

from codeinsight.cognitive.changes.incremental import plan_incremental
from codeinsight.cognitive.changes.service import build_changes
from codeinsight.cognitive.changes.staleness import latest_stale_decisions
from codeinsight.cognitive.indexing.indexer import index_project
from codeinsight.storage.sqlite import open_sqlite

CORE_V1 = '''\
"""核心逻辑。"""


def helper() -> int:
    """帮忙。"""
    return 1


class Widget:
    """小组件。"""

    def run(self) -> int:
        """跑。"""
        return helper()
'''

CORE_V2 = '''\
"""核心逻辑。"""


def helper() -> int:
    """帮忙。"""
    total = 1
    return total


class Widget:
    """小组件。"""

    def run(self) -> int:
        """跑。"""
        return helper()
'''

CORE_WITHOUT_HELPER = '''\
"""核心逻辑。"""


class Widget:
    """小组件。"""

    def run(self) -> int:
        """跑。"""
        return 1
'''

MAIN_PY = '''\
"""入口。"""

from pkg.core import Widget, helper


def main() -> int:
    """跑一下。"""
    return helper() + Widget().run()
'''

ADR = """\
# 0001 — 缓存刷新用文件锁

状态：已接受

核心是 `helper` 这个函数：它负责刷新缓存，并用文件锁保护。

```
helper()
```
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "demo"
    (root / "pkg").mkdir(parents=True)
    (root / "docs" / "decisions").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "core.py").write_text(CORE_V1, encoding="utf-8")
    (root / "pkg" / "main.py").write_text(MAIN_PY, encoding="utf-8")
    (root / "docs" / "decisions" / "0001-cache-lock.md").write_text(ADR, encoding="utf-8")
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "test")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "v1")
    return root


def _index(db: Path, repo: Path, *, incremental: bool):
    return index_project(db, root=repo, name="demo", incremental=incremental)


def _conn(db: Path) -> sqlite3.Connection:
    return open_sqlite(db, row_factory=True)


def _chunk_shas(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        "SELECT c.qualname, c.source_sha256 FROM chunk c WHERE c.ordinal = 0"
    ).fetchall()
    return {row["qualname"]: row["source_sha256"] for row in rows}


def test_incremental_touches_only_changed_symbols(tmp_path: Path, repo: Path) -> None:
    db = tmp_path / "ci.db"
    _index(db, repo, incremental=False)
    conn = _conn(db)
    before = _chunk_shas(conn)
    conn.close()

    (repo / "pkg" / "core.py").write_text(CORE_V2, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "v2")

    result = _index(db, repo, incremental=True)
    assert result.stats["changed_symbols"] >= 1

    conn = _conn(db)
    after = _chunk_shas(conn)
    # 改过 body 的函数：哈希变了；没改的函数：哈希**逐字不变**。
    assert before["pkg.core.helper"] != after["pkg.core.helper"]
    assert before["pkg.core.Widget.run"] == after["pkg.core.Widget.run"]
    assert before["pkg.main.main"] == after["pkg.main.main"]

    # 粗筛层更新到新文件版本，精确层不动。
    rows = conn.execute(
        "SELECT file_content_sha256 FROM chunk c JOIN file f ON f.id = c.file_id"
        " WHERE f.path = 'pkg/main.py'"
    ).fetchall()
    assert len({row[0] for row in rows}) == 1

    payload = build_changes(conn, 1)
    assert payload["head"]
    assert any(
        symbol["qualname"] == "pkg.core.helper" and symbol["change"] == "body_changed"
        for symbol in payload["changed_symbols"]
    )
    assert any(item["path"] == "pkg/core.py" for item in payload["files"]["modified"])
    conn.close()


def test_removed_symbol_reports_its_former_callers(tmp_path: Path, repo: Path) -> None:
    db = tmp_path / "ci.db"
    _index(db, repo, incremental=False)

    (repo / "pkg" / "core.py").write_text(CORE_WITHOUT_HELPER, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "drop helper")

    _index(db, repo, incremental=True)
    conn = _conn(db)
    payload = build_changes(conn, 1)

    removed = [s for s in payload["changed_symbols"] if s["change"] == "removed"]
    assert any(symbol["qualname"] == "pkg.core.helper" for symbol in removed)
    # 删除时最该告诉用户的是「谁还在用它」——入边会随 CASCADE 消失，
    # 必须在删除前快照。
    impacted = {item["qualname"] for item in payload["impacted"]["symbols"]}
    assert "pkg.main.main" in impacted
    conn.close()


def test_design_decision_is_flagged_stale_when_its_claim_disappears(
    tmp_path: Path, repo: Path
) -> None:
    db = tmp_path / "ci.db"
    _index(db, repo, incremental=False)
    conn = _conn(db)
    assert latest_stale_decisions(conn, project_id=1) == []
    conn.close()

    (repo / "pkg" / "core.py").write_text(CORE_WITHOUT_HELPER, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "drop helper")

    _index(db, repo, incremental=True)
    conn = _conn(db)
    stale = latest_stale_decisions(conn, project_id=1)
    assert stale
    assert stale[0]["doc_id"].startswith("0001")
    assert "helper" in stale[0]["reason"]
    conn.close()


def test_unchanged_repository_is_a_noop(tmp_path: Path, repo: Path) -> None:
    db = tmp_path / "ci.db"
    _index(db, repo, incremental=False)
    result = _index(db, repo, incremental=True)
    assert result.stats.get("changed_symbols", 0) == 0


def test_rewritten_history_falls_back_to_full(tmp_path: Path, repo: Path) -> None:
    """amend / rebase 之后增量没有意义——必须退回全量。"""
    db = tmp_path / "ci.db"
    _index(db, repo, incremental=False)
    (repo / "pkg" / "core.py").write_text(CORE_V2, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--amend", "-m", "rewritten")

    conn = _conn(db)
    assert plan_incremental(conn, 1, repo, None) is None
    conn.close()

    result = _index(db, repo, incremental=True)
    # 退回全量后仍然能建出正确的索引。
    assert result.symbols >= 3


def test_incremental_result_matches_a_full_rebuild(tmp_path: Path, repo: Path) -> None:
    """增量不是「另一种索引」，它必须和全量重建**得到同一份事实**。

    只验证「变了的块变了」是不够的——增量最容易出的错是悄悄漏掉
    某个派生表、或者让边指向旧 id。这里拿两个库逐项比对内容。
    """
    inc_db = tmp_path / "inc.db"
    _index(inc_db, repo, incremental=False)
    (repo / "pkg" / "core.py").write_text(CORE_V2, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "v2")
    _index(inc_db, repo, incremental=True)

    full_db = tmp_path / "full.db"
    _index(full_db, repo, incremental=False)

    def snapshot(db: Path) -> dict:
        conn = _conn(db)
        try:
            return {
                "symbols": conn.execute(
                    "SELECT qualname, lineno, end_lineno, source_sha256 FROM symbol"
                    " ORDER BY qualname, lineno"
                ).fetchall(),
                "chunks": conn.execute(
                    "SELECT qualname, ordinal, source_sha256 FROM chunk"
                    " ORDER BY qualname, ordinal"
                ).fetchall(),
                "edges": conn.execute(
                    "SELECT src_qualname, dst_qualname, dst_name, kind, lineno FROM edge"
                    " ORDER BY src_qualname, kind, lineno, dst_name"
                ).fetchall(),
                "modules": conn.execute("SELECT qualname, docstring FROM module ORDER BY qualname").fetchall(),
                "design": conn.execute(
                    "SELECT doc_id, title, claims_json FROM design_decision ORDER BY doc_id"
                ).fetchall(),
            }
        finally:
            conn.close()

    assert snapshot(inc_db) == snapshot(full_db)


def test_change_payload_matches_contract_shape(tmp_path: Path, repo: Path) -> None:
    db = tmp_path / "ci.db"
    _index(db, repo, incremental=False)
    conn = _conn(db)
    payload = build_changes(conn, 1)
    assert set(payload) == {
        "since",
        "head",
        "summary",
        "files",
        "changed_symbols",
        "impacted",
        "tests",
        "stale_design_decisions",
    }
    assert set(payload["files"]) == {"added", "modified", "deleted"}
    assert set(payload["impacted"]) == {"modules", "symbols", "concept_ids"}
    conn.close()
