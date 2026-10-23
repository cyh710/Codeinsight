"""知识层接口（源文档 §2.6 项目关联知识探索）。

核心设计：**概念不靠手工维护"概念 → 代码位置"映射表**，而是从已有的符号/关系索引里
**自动派生**。检测规则声明在 `knowledge/concepts/*.yaml` 里，检测器在符号与关系上跑一遍，
产出 `ConceptInstance`。

这样"这张表"永远不会过期——代码改了，重跑检测就同步了。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from codeinsight.models import ConceptInstance, EdgeKind, SymbolKind


@runtime_checkable
class ConceptDetector(Protocol):
    """把技术概念识别到具体代码位置。"""

    def detect(
        self,
        symbols: Sequence[SymbolView],
        edges: Sequence[EdgeView],
    ) -> list[ConceptInstance]:
        """在符号与关系上跑检测规则，返回概念实例。

        每个实例必须带 `evidence`（命中了哪条规则），保证结论可追溯、可质疑。
        """
        ...


class SymbolView:
    """检测器看到的符号视图（只读投影，避免把数据库行对象泄漏进规则层）。"""

    __slots__ = ("qualname", "name", "kind", "path", "lineno", "end_lineno", "header", "docstring")

    def __init__(
        self,
        qualname: str,
        name: str,
        kind: SymbolKind,
        path: str,
        lineno: int,
        end_lineno: int,
        header: str = "",
        docstring: str | None = None,
    ) -> None:
        self.qualname = qualname
        self.name = name
        self.kind = kind
        self.path = path
        self.lineno = lineno
        self.end_lineno = end_lineno
        self.header = header
        self.docstring = docstring


class EdgeView:
    """检测器看到的关系视图。"""

    __slots__ = ("src_qualname", "dst_name", "dst_qualname", "kind", "path", "lineno")

    def __init__(
        self,
        src_qualname: str,
        dst_name: str,
        kind: EdgeKind,
        path: str,
        lineno: int,
        dst_qualname: str | None = None,
    ) -> None:
        self.src_qualname = src_qualname
        self.dst_name = dst_name
        self.dst_qualname = dst_qualname
        self.kind = kind
        self.path = path
        self.lineno = lineno
