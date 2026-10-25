"""内容更新、并发装配和损坏资产不能被缓存遮蔽。"""

import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from codeinsight.cognitive.concepts import library_loader
from codeinsight.cognitive.concepts.learning_models import KnowledgeError


@pytest.fixture
def assets(tmp_path):
    root = Path(__file__).resolve().parents[2] / "knowledge" / "learning"
    return Path(shutil.copytree(root, tmp_path / "learning"))


def test_concurrent_requests_share_one_immutable_snapshot(assets):
    with patch.object(
        library_loader, "LearningLibrary", wraps=library_loader.LearningLibrary
    ) as build:
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(
                pool.map(lambda _: library_loader.get_learning_library(assets), range(3))
            )
    assert build.call_count == 1
    assert all(result is results[0] for result in results)
    assert len(results[0].topics) == 66


def test_body_update_invalidates_even_when_size_and_mtime_are_preserved(assets):
    first = library_loader.get_learning_library(assets)
    path = assets / "articles/sql/sql-database.md"
    before = path.stat()
    path.write_bytes(path.read_bytes().replace("数据库".encode(), "资料库".encode()))
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    second = library_loader.get_learning_library(assets)
    assert second is not first and second.version != first.version
    assert "资料库" in second.get("sql-database").body


def test_source_and_metadata_updates_are_visible(assets):
    first = library_loader.get_learning_library(assets)
    path = assets / "sources.json"
    sources = json.loads(path.read_text(encoding="utf-8"))
    sources[0]["author"] = "更新后的作者"
    path.write_text(json.dumps(sources, ensure_ascii=False), encoding="utf-8")
    second = library_loader.get_learning_library(assets)
    assert second.sources[sources[0]["id"]].author == "更新后的作者"
    assert second.version != first.version
    index_path = assets / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index[0]["summary"] = "更新后的预览摘要"
    index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    third = library_loader.get_learning_library(assets)
    assert third.get(index[0]["id"]).summary == "更新后的预览摘要"
    assert third.version != second.version


def test_corrupt_update_does_not_fall_back_to_cached_content(assets):
    library_loader.get_learning_library(assets)
    (assets / "index.json").write_text("{", encoding="utf-8")
    with pytest.raises(KnowledgeError):
        library_loader.get_learning_library(assets)
