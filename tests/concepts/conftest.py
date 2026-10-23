"""B 线独立夹具；不改写 A 线共享测试配置。"""

from pathlib import Path

import pytest

from codeinsight.cognitive.concepts.library import LearningLibrary
from codeinsight.cognitive.concepts.ontology import load_ontology

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def library():
    return LearningLibrary(ROOT / "knowledge" / "learning")


@pytest.fixture(scope="session")
def concepts():
    return load_ontology(ROOT / "knowledge" / "concepts")
