"""配置失败必须暴露，并分别维护内容和规则版本。"""

from dataclasses import replace

import pytest

from codeinsight.cognitive.concepts.learning_models import KnowledgeError
from codeinsight.cognitive.concepts.ontology import (
    detection_version,
    load_ontology,
    ontology_version,
)


def test_twenty_concepts_have_rules_and_tradeoffs(concepts, library):
    assert len(concepts) == 20
    for concept in concepts.values():
        assert concept.tradeoffs and concept.principles and concept.references
        assert library.topics_for_concept(concept.id)


def test_prose_update_does_not_reindex_code(concepts):
    updated = {**concepts, "jwt": replace(concepts["jwt"], summary="新的教材讲解")}
    assert ontology_version(updated) != ontology_version(concepts)
    assert detection_version(updated) == detection_version(concepts)
    updated["jwt"] = replace(
        updated["jwt"], detection=replace(updated["jwt"].detection, call_names=("new.jwt.decode",))
    )
    assert detection_version(updated) != detection_version(concepts)


@pytest.mark.parametrize(
    "text",
    [
        "id: jwt\nname: JWT\ncategory: invalid\nsummary: 定义\ntradeoffs: 代价\ndetection: {}\n",
        "id: jwt\nname: JWT\ncategory: auth\nsummary: 定义\ntradeoffs: 代价\ndetection: {surprise: []}\n",
        "id: jwt\nname: JWT\ncategory: auth\nsummary: 定义\ndetection: {}\n",
        "[unterminated",
    ],
)
def test_bad_assets_report_path(tmp_path, text):
    (tmp_path / "jwt.yaml").write_text(text, encoding="utf8")
    with pytest.raises(KnowledgeError, match="jwt.yaml"):
        load_ontology(tmp_path)


def test_missing_and_empty_directories_are_not_empty_ontologies(tmp_path):
    with pytest.raises(KnowledgeError, match="不存在"):
        load_ontology(tmp_path / "none")
    with pytest.raises(KnowledgeError, match="为空"):
        load_ontology(tmp_path)
