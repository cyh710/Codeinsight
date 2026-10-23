"""加载策展本体；无效资产不能静默混入检测规则。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from codeinsight.cognitive.concepts.learning_models import KnowledgeError

CATEGORIES = frozenset(
    "auth cache db concurrency async http config pattern data-structure security "
    "observability testing build other".split()
)
RULE_KEYS = (
    "import_names",
    "call_names",
    "attribute_names",
    "decorator_names",
    "base_classes",
    "string_markers",
)
ID_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")


@dataclass(frozen=True)
class DetectionRules:
    import_names: tuple[str, ...] = ()
    call_names: tuple[str, ...] = ()
    attribute_names: tuple[str, ...] = ()
    decorator_names: tuple[str, ...] = ()
    base_classes: tuple[str, ...] = ()
    string_markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Concept:
    id: str
    name: str
    category: str
    summary: str
    principles: str
    tradeoffs: str
    alternatives: str
    detection: DetectionRules
    references: tuple[str, ...] = ()


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise KnowledgeError(f"{label} 必须是非空字符串列表（允许空列表）")
    return tuple(dict.fromkeys(value))


def load_ontology(directory: Path) -> dict[str, Concept]:
    """读取目录内 YAML；必填项、分类、规则键和 ID 有误时报告具体文件。"""
    try:
        import yaml
    except ImportError as exc:
        raise KnowledgeError("缺少 PyYAML；请由 A 线落实请求 0001 后安装项目依赖") from exc
    directory = Path(directory)
    if not directory.is_dir():
        raise KnowledgeError(f"本体目录不存在：{directory}")
    concepts: dict[str, Concept] = {}
    paths = sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")])
    if not paths:
        raise KnowledgeError(f"本体目录为空：{directory}")
    for path in paths:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise KnowledgeError("顶层必须是映射")
            required = ("id", "name", "category", "summary", "tradeoffs")
            for key in required:
                if not isinstance(data.get(key), str) or not data[key].strip():
                    raise KnowledgeError(f"缺少有效字段 {key}")
            cid = data["id"]
            if not ID_PATTERN.fullmatch(cid) or path.stem != cid:
                raise KnowledgeError("id 必须为 kebab-case 且与文件名相同")
            if cid in concepts:
                raise KnowledgeError(f"重复 id：{cid}")
            if data["category"] not in CATEGORIES:
                raise KnowledgeError(f"未知 category：{data['category']}")
            rules = data.get("detection")
            if not isinstance(rules, dict) or set(rules) - set(RULE_KEYS):
                raise KnowledgeError("detection 必须是映射且仅含约定的六类规则")
            optional: dict[str, str] = {}
            for key in ("principles", "alternatives"):
                value = data.get(key, "")
                if not isinstance(value, str):
                    raise KnowledgeError(f"{key} 必须是字符串")
                optional[key] = value
            concepts[cid] = Concept(
                **{key: data[key] for key in required},
                **optional,
                detection=DetectionRules(**{k: _strings(rules.get(k, []), k) for k in RULE_KEYS}),
                references=_strings(data.get("references", []), "references"),
            )
        except (KnowledgeError, yaml.YAMLError, OSError) as exc:
            raise KnowledgeError(f"{path}: {exc}") from exc
    return concepts


def ontology_version(concepts: dict[str, Concept]) -> str:
    """正文变化影响本体版本；顺序和文件时间不影响版本。"""
    payload = {key: asdict(concepts[key]) for key in sorted(concepts)}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def detection_version(concepts: dict[str, Concept]) -> str:
    """规则与检测实现共同决定版本；教材正文与文件时间不触发代码重检。"""
    payload = {
        "rules": {key: asdict(concepts[key].detection) for key in sorted(concepts)},
        "implementation": hashlib.sha256(
            Path(__file__).with_name("detector.py").read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest(),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
