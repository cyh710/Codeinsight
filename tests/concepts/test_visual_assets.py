"""图文同版本、缺图降级、图意检索与已发布教学断言的回归。"""

import contextlib
import io
import json
import re
import runpy
import shutil
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from codeinsight.api import learning
from codeinsight.api.app import create_app
from codeinsight.cognitive.concepts import library_loader
from codeinsight.cognitive.concepts.learning_models import KnowledgeError
from codeinsight.cognitive.concepts.library import LearningLibrary

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def visuals(tmp_path):
    return Path(shutil.copytree(ROOT / "knowledge/learning", tmp_path / "learning"))


def test_api_serves_exact_version_and_no_server_paths(library, monkeypatch, data_dir):
    monkeypatch.setattr(learning, "get_learning_library", lambda: library)
    with TestClient(create_app()) as client:
        topic = client.get("/knowledge/topics/sql-database").json()
        asset = topic["assets"][0]
        assert "file" not in asset
        response = client.get(asset["href"])
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/svg+xml")
        assert "immutable" in response.headers["cache-control"]
        assert response.headers["etag"] == f'"{asset["sha256"]}"'
        assert client.get(asset["href"].replace(asset["sha256"], "0" * 64)).status_code == 404
        assert client.get("/knowledge/assets/missing/" + "0" * 64).status_code == 404


@pytest.mark.parametrize("change", ["missing", "corrupt"])
def test_bad_image_does_not_block_text_or_reuse_stale_cache(visuals, monkeypatch, change, data_dir):
    old = library_loader.get_learning_library(visuals)
    asset = old.visuals.records["sql-table-relation"]
    path = visuals / asset.file
    if change == "missing":
        path.unlink()
    else:
        path.write_text("<svg>broken update</svg>", encoding="utf-8")
    new = library_loader.get_learning_library(visuals)
    changed = {tid for tid in old.topics if old.get(tid).version != new.get(tid).version}
    assert changed == {"sql-database"}
    monkeypatch.setattr(learning, "get_learning_library", lambda: new)
    with TestClient(create_app()) as client:
        topic = client.get("/knowledge/topics/sql-database")
        assert topic.status_code == 200 and "SELECT" in topic.json()["body"]
        failure = client.get(asset.href)
        assert failure.status_code == 404
        assert failure.json()["error"]["code"] == "not_found"


def test_updated_image_manifest_invalidates_only_owner_and_old_url(visuals):
    import hashlib

    before = LearningLibrary(visuals)
    asset = before.visuals.records["python-return-path"]
    path = visuals / asset.file
    path.write_bytes(path.read_bytes() + b"\n")
    manifest = json.loads((visuals / "assets.json").read_text(encoding="utf-8"))
    for entry in manifest:
        if entry["id"] == asset.id:
            entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (visuals / "assets.json").write_text(json.dumps(manifest), encoding="utf-8")
    after = LearningLibrary(visuals)
    assert {t for t in before.topics if before.get(t).version != after.get(t).version} == {
        "python-functions"
    }
    with pytest.raises(KnowledgeError, match="版本"):
        after.visuals.read(asset.id, asset.sha256)
    assert after.visuals.read(asset.id, after.visuals.records[asset.id].sha256)[1]


def test_paths_and_figure_ownership_are_validated(visuals):
    path = visuals / "assets.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows[0]["file"] = "../../outside.svg"
    path.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(KnowledgeError, match="assets"):
        LearningLibrary(visuals)
    rows[0]["file"] = "assets/python-functions/python-return-path.svg"
    rows[0]["section_id"] = "missing"
    path.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(KnowledgeError, match="章节"):
        LearningLibrary(visuals)


def test_figure_meaning_is_text_context_not_svg_or_resource_url(library):
    target = library.target("sql-database", "relationships")
    context = library.reading_context(target)
    assert "101 和 102" in context.content
    assert "/knowledge/assets/" not in context.content
    assert "<svg" not in context.content
    assert context.references[0].snippet in context.content
    assert library.search("HMR")[0].target.topic_id == "state-lifecycle"


def test_figure_projection_preserves_fenced_examples(library):
    image = "![图注](/knowledge/assets/python-return-path)"
    fenced = f"```markdown\n{image}\n```"
    assert library.visuals.describe(fenced) == fenced
    assert library.visuals.describe(image).startswith("[教学图：")


def test_generated_figures_are_reproducible_and_self_contained(library):
    generator = runpy.run_path(str(ROOT / "scripts/build_learning_figures.py"))
    for record, svg in generator["figures"]():
        asset, content = library.visuals.read(record["id"], record["sha256"])
        assert content.decode() == svg
        root = ET.fromstring(content)
        assert root.attrib["width"] == str(asset.width)
        assert root.attrib["height"] == str(asset.height)
        for node in root.iter():
            assert node.tag.rsplit("}", 1)[-1] not in {"script", "foreignObject", "image"}
            assert not any(k.lower().startswith("on") or "href" in k for k in node.attrib)


def test_python_article_outputs_and_sql_statements_are_executable(library):
    blocks = re.findall(r"```python\n(.*?)```", library.get("python-functions").body, re.S)
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        exec(blocks[0], {})
    assert printed.getvalue().splitlines() == ["36", "None"]
    namespace = {}
    exec(blocks[1], namespace)
    fn = namespace["calculate_total"]
    assert [fn(12), fn(12, 3), fn(12, quantity=3)] == [12, 36, 36]
    sql_blocks = re.findall(r"```sql\n(.*?)```", library.get("sql-database").body, re.S)
    conn = sqlite3.connect(":memory:")
    try:
        for statement in sql_blocks:
            conn.executescript(statement)
        assert conn.execute("SELECT name FROM goods ORDER BY id").fetchall() == [
            ("笔记本",),
            ("钢笔",),
        ]
        condition = re.search(r"`(WHERE price \* 0\.8 < 30)`", library.get("sql-database").body)[1]
        assert len(conn.execute("SELECT name FROM goods " + condition).fetchall()) == 2
    finally:
        conn.close()
    example = runpy.run_path(str(ROOT / "knowledge/learning/examples/sql_basics.py"))
    result = example["run_demo"]()
    assert result["joined"] == [
        (101, "笔记本", 2, 24.0),
        (102, "笔记本", 1, 12.0),
        (103, "钢笔", 1, 35.0),
    ]
    assert result["invalid_foreign_key_rejected"] and result["renamed_rows"] == 2
