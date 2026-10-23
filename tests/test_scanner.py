"""仓库扫描器。

验收口径（规格 §1.2 A1）：取到的文件数与 `git ls-tree` 一致；不含 dist/ .venv/；
非 ASCII 路径不能被加引号（ADR / 规格里的 quotepath 陷阱）。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from codeinsight.cognitive.indexing.scanner import (
    list_repo_files,
    module_qualname,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=True
    ).stdout.decode()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """造一个小仓库。"""
    (tmp_path / "backend" / "core").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "build_cache" / "tiktoken").mkdir(parents=True)
    (tmp_path / "mobile_sam").mkdir()

    (tmp_path / "backend" / "core" / "chunk_bm25.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "backend" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "tests" / "test_x.py").write_text("def t():\n    pass\n", encoding="utf-8")
    (tmp_path / "node_modules" / "pkg" / "index.js").write_text("x", encoding="utf-8")
    (tmp_path / "build_cache" / "tiktoken" / "9b5ad71b").write_bytes(b"\x00\x01binary")
    (tmp_path / "mobile_sam" / "predictor.py").write_text("class SamPredictor:\n    pass\n")
    (tmp_path / "README.md").write_text("# 织忆\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "色库扩展.md").write_text("# 色库\n", encoding="utf-8")

    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def test_excluded_dirs_are_not_listed(repo: Path) -> None:
    paths = {f.path for f in list_repo_files(repo)}
    assert not any(p.startswith("node_modules/") for p in paths)
    assert not any(p.startswith("build_cache/") for p in paths)
    assert not any(p.startswith(".git/") for p in paths)


def test_file_count_matches_git_ls_tree(repo: Path) -> None:
    """取到的文件数与 git 报的一致（扣除排除规则）。"""
    listed = {f.path for f in list_repo_files(repo)}
    tracked = set(
        _git(repo, "-c", "core.quotepath=false", "ls-tree", "-r", "--name-only", "HEAD").split()
    )
    excluded = {p for p in tracked if p.startswith(("node_modules/", "build_cache/"))}
    assert listed == tracked - excluded


def test_non_ascii_path_is_not_quoted(repo: Path) -> None:
    """非 ASCII 路径必须是原样，不能是八进制转义。"""
    paths = {f.path for f in list_repo_files(repo)}
    assert "docs/色库扩展.md" in paths
    assert not any("\\" in p for p in paths)


def test_role_classification(repo: Path) -> None:
    by_path = {f.path: f for f in list_repo_files(repo)}
    assert by_path["backend/core/chunk_bm25.py"].role == "source"
    assert by_path["tests/test_x.py"].role == "test"
    assert by_path["mobile_sam/predictor.py"].role == "vendored"
    assert by_path["pyproject.toml"].role == "config"
    assert by_path["README.md"].role == "doc"


def test_vendored_keeps_symbols_but_no_chunks(repo: Path) -> None:
    """ADR 0015 第二档：符号入库（import 边要用），chunk 不入库（不参与检索）。"""
    by_path = {f.path: f for f in list_repo_files(repo)}
    vendored = by_path["mobile_sam/predictor.py"]
    assert vendored.in_index is True
    assert vendored.in_chunk_index is False

    source = by_path["backend/core/chunk_bm25.py"]
    assert source.in_chunk_index is True


def test_tests_are_not_downweighted(repo: Path) -> None:
    """ADR 0015 第三档：测试同等对待，不降权——降权会污染 §5 的对照实验。"""
    by_path = {f.path: f for f in list_repo_files(repo)}
    assert by_path["tests/test_x.py"].in_chunk_index is True
    assert by_path["tests/test_x.py"].in_index is True


def test_blob_sha_is_recorded(repo: Path) -> None:
    by_path = {f.path: f for f in list_repo_files(repo)}
    sha = _git(repo, "rev-parse", "HEAD:backend/core/chunk_bm25.py").strip()
    assert by_path["backend/core/chunk_bm25.py"].blob_sha == sha


def test_ref_selects_commit(repo: Path) -> None:
    """按 ref 取文件树——索引要绑定确定 commit，不能跟着工作区漂移。"""
    _git(repo, "checkout", "-qb", "other")
    (repo / "backend" / "core" / "new.py").write_text("y = 2\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "second")
    _git(repo, "checkout", "-q", "master")

    on_master = {f.path for f in list_repo_files(repo)}
    on_other = {f.path for f in list_repo_files(repo, ref="other")}
    assert "backend/core/new.py" not in on_master
    assert "backend/core/new.py" in on_other


def test_module_qualname() -> None:
    assert module_qualname("backend/core/chunk_bm25.py") == "backend.core.chunk_bm25"
    assert module_qualname("backend/__init__.py") == "backend"
    assert module_qualname("main.py") == "main"
