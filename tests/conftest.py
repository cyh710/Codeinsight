"""共享测试夹具。

约定：**离线优先**——全套件不许打真实 provider（沿用 Tapestry `tests/conftest.py` 的做法）。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from codeinsight.config import settings
from codeinsight.storage.sqlite import db_path, ensure_schema, open_sqlite


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把 settings.data_dir 指到临时目录，并建好 schema。"""
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setattr(settings, "data_dir", d)
    ensure_schema(db_path(d))
    return d


@pytest.fixture
def conn(data_dir: Path) -> Iterator[sqlite3.Connection]:
    """一个已建好 schema 的连接。"""
    connection = open_sqlite(db_path(data_dir), row_factory=True)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """禁止测试意外连上真实模型服务。"""
    monkeypatch.setattr(settings, "llm_api_key", "test-dummy-key")
    monkeypatch.setattr(settings, "embedding_api_key", "test-dummy-key")
    monkeypatch.setattr(settings, "llm_base_url", "http://127.0.0.1:9/v1")
    monkeypatch.setattr(settings, "embedding_base_url", "http://127.0.0.1:9/v1")
