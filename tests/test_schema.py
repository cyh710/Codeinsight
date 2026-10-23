"""Schema 与 FTS5 同步的回归。

重点验三件容易出错的事：

1. FTS5 虚表（external content）与 `chunk` 表通过触发器保持同步——**删 chunk 后 FTS 里不能残留**。
2. `tokenize = "unicode61 tokenchars '_'"` 下 `get_user_name` 是**单个 token**，
   不会被 unicode61 切成 get/user/name（那正是要靠入库前预分词绕开的问题）。
3. 双层哈希的粗筛视图能正确找出"文件变了"的 chunk。
"""

from __future__ import annotations

import sqlite3

CHUNK_BODY = "def get_user_name(user_id):\n    return f'user_{user_id}'\n"
TOKEN_TEXT = "get_user_name get user name user_id"


def _seed(conn: sqlite3.Connection, *, token_text: str = TOKEN_TEXT) -> None:
    conn.execute("INSERT INTO project (id, name, root_path) VALUES (1, 'demo', '/tmp/demo')")
    conn.execute(
        """
        INSERT INTO file (id, project_id, path, language, content_sha256)
        VALUES (1, 1, 'app/user.py', 'python', 'filesha')
        """
    )
    conn.execute(
        """
        INSERT INTO symbol (id, project_id, file_id, qualname, name, kind, lineno,
                            end_lineno, source_sha256)
        VALUES (1, 1, 1, 'get_user_name', 'get_user_name', 'function', 1, 2, 'symsha')
        """
    )
    conn.execute(
        """
        INSERT INTO chunk (id, project_id, symbol_id, file_id, qualname, name, kind,
                           lineno, end_lineno, body, token_text, source_sha256,
                           file_content_sha256)
        VALUES (1, 1, 1, 1, 'get_user_name', 'get_user_name', 'function', 1, 2,
                ?, ?, 'chunksha', 'filesha')
        """,
        (CHUNK_BODY, token_text),
    )
    conn.commit()


def _fts_ids(conn: sqlite3.Connection, query: str) -> list[int]:
    rows = conn.execute(
        "SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH ? ORDER BY rowid",
        (query,),
    ).fetchall()
    return [int(r[0]) for r in rows]


def test_fts_finds_chunk_after_insert(conn: sqlite3.Connection) -> None:
    _seed(conn)
    assert _fts_ids(conn, "get_user_name") == [1]


def test_underscore_identifier_is_one_atomic_term(conn: sqlite3.Connection) -> None:
    """`get_user_name` 在 FTS 索引里必须是一个原子 term。

    unicode61 默认会把 `get_user_name` 切成 get/user/name 三个 term，
    BM25 的长度归一化与词频都会跟着变。`tokenize = "unicode61 tokenchars '_'"`
    把它保持成一个 term —— 用 fts5vocab 查词表验证。
    """
    _seed(conn)
    conn.execute("CREATE VIRTUAL TABLE v USING fts5vocab(chunk_fts, 'row')")
    terms = {str(r[0]) for r in conn.execute("SELECT term FROM v").fetchall()}
    assert "get_user_name" in terms


def test_partial_token_still_matches(conn: sqlite3.Connection) -> None:
    """预分词把 snake 分词也写进了 token_text，所以部分词仍能命中。

    这正是「精确匹配 + 部分匹配兼具」的由来：全名是一个原子 term，
    同时它的各个分词也各自可查。
    """
    _seed(conn)
    assert _fts_ids(conn, "user") == [1]


def test_update_token_text_removes_old_row(conn: sqlite3.Connection) -> None:
    _seed(conn)
    conn.execute("UPDATE chunk SET token_text = 'renamed_symbol' WHERE id = 1")
    conn.commit()
    assert _fts_ids(conn, "get_user_name") == []
    assert _fts_ids(conn, "renamed_symbol") == [1]


def test_delete_chunk_leaves_no_fts_residue(conn: sqlite3.Connection) -> None:
    """这是 external content + 触发器方案要防的头号 bug。"""
    _seed(conn)
    conn.execute("DELETE FROM chunk WHERE id = 1")
    conn.commit()
    assert _fts_ids(conn, "get_user_name") == []
    residue = conn.execute(
        "SELECT COUNT(*) FROM chunk_fts WHERE chunk_fts MATCH 'user'"
    ).fetchone()[0]
    assert residue == 0


def test_bm25_ranking_is_available(conn: sqlite3.Connection) -> None:
    _seed(conn)
    row = conn.execute(
        "SELECT rowid, bm25(chunk_fts) AS score FROM chunk_fts WHERE chunk_fts MATCH ?",
        ("get_user_name",),
    ).fetchone()
    assert int(row[0]) == 1
    assert isinstance(float(row[1]), float)


def test_stale_candidate_view_flags_changed_file(conn: sqlite3.Connection) -> None:
    _seed(conn)
    conn.execute(
        """
        INSERT INTO repo_state (project_id, head_commit, parser_version)
        VALUES (1, 'abc123', 'v1')
        """
    )
    conn.execute(
        """
        INSERT INTO file_snapshot (project_id, commit_sha, path, content_sha256)
        VALUES (1, 'abc123', 'app/user.py', 'newsha')
        """
    )
    conn.commit()
    stale = conn.execute("SELECT chunk_id FROM v_stale_candidate").fetchall()
    assert [int(r[0]) for r in stale] == [1]


def test_no_stale_when_file_hash_matches(conn: sqlite3.Connection) -> None:
    _seed(conn)
    conn.execute(
        """
        INSERT INTO repo_state (project_id, head_commit, parser_version)
        VALUES (1, 'abc123', 'v1')
        """
    )
    conn.execute(
        """
        INSERT INTO file_snapshot (project_id, commit_sha, path, content_sha256)
        VALUES (1, 'abc123', 'app/user.py', 'filesha')
        """
    )
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM v_stale_candidate").fetchone()[0] == 0
