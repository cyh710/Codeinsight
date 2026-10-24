"""把概念本体与检测结果同步进索引库（概念检索通道的供数）。

分工（规格 §2.5 B5）：

- **B 线**拥有资产：本体加载（`concepts/ontology.py::load_ontology`）
  与规则检测器（`concepts/detector.py::RuleBasedDetector`）。
- **A 线**负责接线：把索引里的符号与边投影成检测器要的视图，跑检测，
  再把结果写进 `concept` / `concept_instance` 两张表。

**为什么同步放在 A 线而不是 B 线**：检测的**输入**是索引
（符号、边、源码），那是 A 线的产物；检测**规则**是 B 线的资产。
这里只是把两头接起来，不复制 B 线的任何逻辑——
B 线的 `concepts/` 目录仍然只有它自己能写。

检测要**源码**才能做字符串标记类的检测（`string_markers`）。
源码来自索引时的那一份（不是工作区）——索引绑定 commit，
检测也必须绑定同一个 commit，否则「这个概念在这个项目里怎么用的」
会随工作区的未提交改动漂移。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from codeinsight.cognitive.concepts.base import EdgeView, SymbolView
from codeinsight.cognitive.concepts.detector import RuleBasedDetector
from codeinsight.cognitive.concepts.ontology import Concept, load_ontology
from codeinsight.models import EdgeKind, SymbolKind


@dataclass
class ConceptSyncResult:
    """同步结果。"""

    concepts: int = 0
    instances: int = 0
    errors: list[str] | None = None


def load_project_concepts(knowledge_dir: str | Path) -> dict[str, Concept]:
    """读本体目录。目录不存在时返回空字典（不报错——本体是可选的）。"""
    directory = Path(knowledge_dir)
    if not directory.exists():
        return {}
    return load_ontology(directory)


def build_symbol_views(conn: sqlite3.Connection, *, project_id: int) -> list[SymbolView]:
    """索引里的符号 → 检测器要的视图。"""
    rows = conn.execute(
        """
        SELECT s.qualname, s.name, s.kind, f.path, s.lineno, s.end_lineno,
               COALESCE(s.header, ''), COALESCE(s.docstring, '')
        FROM symbol s JOIN file f ON f.id = s.file_id
        WHERE s.project_id = ?
        """,
        (project_id,),
    ).fetchall()
    return [
        SymbolView(
            qualname=row[0],
            name=row[1],
            kind=SymbolKind(row[2]),
            path=row[3],
            lineno=int(row[4]),
            end_lineno=int(row[5]),
            header=row[6],
            docstring=row[7] or None,
        )
        for row in rows
    ]


def build_edge_views(conn: sqlite3.Connection, *, project_id: int) -> list[EdgeView]:
    """索引里的边 → 检测器要的视图。"""
    rows = conn.execute(
        """
        SELECT e.src_qualname, e.dst_name, e.kind, f.path, e.lineno, e.dst_qualname
        FROM edge e JOIN symbol s ON s.id = e.src_symbol_id
        JOIN file f ON f.id = s.file_id
        WHERE e.project_id = ?
        """,
        (project_id,),
    ).fetchall()
    return [
        EdgeView(
            src_qualname=row[0],
            dst_name=row[1],
            kind=EdgeKind(row[2]),
            path=row[3],
            lineno=int(row[4]),
            dst_qualname=row[5],
        )
        for row in rows
    ]


def write_concepts(conn: sqlite3.Connection, *, concepts: dict[str, Concept]) -> int:
    """本体 → `concept` 表。"""
    count = 0
    for concept in concepts.values():
        detection = {
            "import_names": list(concept.detection.import_names),
            "call_names": list(concept.detection.call_names),
            "attribute_names": list(concept.detection.attribute_names),
            "decorator_names": list(concept.detection.decorator_names),
            "base_classes": list(concept.detection.base_classes),
            "string_markers": list(concept.detection.string_markers),
        }
        conn.execute(
            """
            INSERT INTO concept (id, name, category, summary, principles, tradeoffs,
                                 alternatives, detection_json, references_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                category = excluded.category,
                summary = excluded.summary,
                principles = excluded.principles,
                tradeoffs = excluded.tradeoffs,
                alternatives = excluded.alternatives,
                detection_json = excluded.detection_json,
                references_json = excluded.references_json
            """,
            (
                concept.id,
                concept.name,
                concept.category,
                concept.summary,
                concept.principles,
                concept.tradeoffs,
                concept.alternatives,
                json.dumps(detection, ensure_ascii=False),
                json.dumps(list(concept.references), ensure_ascii=False),
            ),
        )
        count += 1
    return count


def build_symbol_resolver(
    conn: sqlite3.Connection, *, project_id: int
) -> Callable[[str, int], int | None]:
    """`(路径, 行号)` → 包含该行的**最内层**符号 id。

    检测器的实例落点在**边上**（比如 `import jwt` 那一行），
    而符号是从它的定义行开始的——两者不是同一行。
    所以不能按 `(path, lineno)` 精确匹配，要按**行号区间包含**来找，
    并且取范围最小的那个（最内层）。

    找不到就返回 None——实例宁可丢掉，也不能挂到错的符号上。
    """
    rows = conn.execute(
        """
        SELECT f.path, s.lineno, s.end_lineno, s.id FROM symbol s JOIN file f ON f.id = s.file_id
        WHERE s.project_id = ?
        """,
        (project_id,),
    ).fetchall()
    by_path: dict[str, list[tuple[int, int, int]]] = {}
    for path, lineno, end_lineno, symbol_id in rows:
        by_path.setdefault(path, []).append((int(lineno), int(end_lineno), int(symbol_id)))

    def resolve(path: str, lineno: int) -> int | None:
        candidates = [c for c in by_path.get(path, []) if c[0] <= lineno <= c[1]]
        if not candidates:
            return None
        return min(candidates, key=lambda c: c[1] - c[0])[2]

    return resolve


def write_instances(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    instances: list,
    resolve_symbol: Callable[[str, int], int | None],
    file_id_of: dict[str, int],
) -> int:
    """检测结果 → `concept_instance` 表。"""
    count = 0
    for instance in instances:
        symbol_id = resolve_symbol(instance.path, instance.lineno)
        if symbol_id is None:
            continue
        conn.execute(
            """
            INSERT INTO concept_instance (project_id, concept_id, symbol_id, file_id,
                                         path, lineno, qualname, evidence, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, concept_id, path, lineno) DO UPDATE SET
                symbol_id = excluded.symbol_id,
                file_id = excluded.file_id,
                qualname = excluded.qualname,
                evidence = excluded.evidence,
                confidence = excluded.confidence
            """,
            (
                project_id,
                instance.concept_id,
                symbol_id,
                file_id_of.get(instance.path),
                instance.path,
                instance.lineno,
                instance.qualname,
                instance.evidence,
                instance.confidence,
            ),
        )
        count += 1
    return count


def sync_concepts(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    knowledge_dir: str | Path,
    sources: dict[str, str] | None = None,
) -> ConceptSyncResult:
    """跑一次完整同步：本体入库 + 检测实例入库。

    `sources` 是被索引的那个 commit 的源码（路径 → 内容）。
    没有它就只做结构化检测（import / 调用 / 装饰器 / 继承），
    字符串标记类的规则会被跳过——这是有意的：宁可少检一类，
    也不拿工作区的源码去污染一个绑定 commit 的索引。
    """
    concepts = load_project_concepts(knowledge_dir)
    if not concepts:
        return ConceptSyncResult()

    write_concepts(conn, concepts=concepts)

    symbols = build_symbol_views(conn, project_id=project_id)
    edges = build_edge_views(conn, project_id=project_id)

    detector = RuleBasedDetector(concepts)
    instances = detector.detect(symbols, edges, sources=sources or {})

    file_id_of: dict[str, int] = {}
    rows = conn.execute(
        """
        SELECT f.path, f.id FROM file f WHERE f.project_id = ?
        """,
        (project_id,),
    ).fetchall()
    for path, file_id in rows:
        file_id_of[path] = int(file_id)

    written = write_instances(
        conn,
        project_id=project_id,
        instances=instances,
        resolve_symbol=build_symbol_resolver(conn, project_id=project_id),
        file_id_of=file_id_of,
    )
    return ConceptSyncResult(
        concepts=len(concepts),
        instances=written,
        errors=list(detector.errors),
    )
