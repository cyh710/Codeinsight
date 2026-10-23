"""共享领域模型。

这些类型是各层之间传递的**唯一契约**：解析层产出 `ParsedFile`，索引层落库，
检索层返回 `Evidence`，Agent 层把证据拼成答案。

设计原则（对齐源文档 §2.2 / §2.3-6）：
- 任何指向代码的结论都必须能落回 `file:line`。
- 无法静态确定的关系用 `confidence` 表达不确定性，而不是丢弃或假装确定。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class SymbolKind(enum.StrEnum):
    """符号种类。源文档 §2.1-4「提取重要类、函数、方法和代码符号」。"""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    CONSTANT = "constant"


class EdgeKind(enum.StrEnum):
    """符号之间的关系。源文档 §2.2-1/2/3。"""

    CALL = "call"
    INHERITS = "inherits"
    IMPORTS = "imports"
    DECORATOR = "decorator"
    REFERENCES = "references"
    RETURNS = "returns"


class ConceptDepth(enum.StrEnum):
    """知识探索的三级深度。源文档 §2.6。"""

    QUICK = "quick"  # 快速理解：简要解释概念及其用途（读本体，不调 LLM）
    PROJECT = "project"  # 结合项目：实现位置、执行方式、调用关系（自动派生）
    DEEP = "deep"  # 深入探索：原理、设计权衡、其他实现、与现有代码的联系


@dataclass(frozen=True)
class ParsedSymbol:
    """一个符号（类 / 函数 / 方法 / 常量）。"""

    qualname: str
    name: str
    kind: SymbolKind
    lineno: int
    end_lineno: int
    header: str = ""
    docstring: str | None = None
    parent_qualname: str | None = None
    is_async: bool = False
    is_private: bool = False
    is_dunder: bool = False
    n_lines: int = 0


@dataclass(frozen=True)
class ParsedEdge:
    """符号之间的关系。

    `dst_qualname` 为 None 表示目标是仓库外部符号（导入自第三方库、动态调用等）；
    `confidence` < 1 表示这条边是推断出来的（动态调用、属性访问等）。
    """

    src_qualname: str
    dst_name: str
    kind: EdgeKind
    lineno: int
    dst_qualname: str | None = None
    confidence: float = 1.0


@dataclass(frozen=True)
class ParsedImport:
    module: str
    names: tuple[str, ...] = ()
    lineno: int = 0
    is_relative: bool = False


@dataclass(frozen=True)
class ParsedFile:
    """一次解析的产物。"""

    path: str
    language: str
    module_docstring: str | None = None
    imports: tuple[ParsedImport, ...] = ()
    symbols: tuple[ParsedSymbol, ...] = ()
    edges: tuple[ParsedEdge, ...] = ()


@dataclass(frozen=True)
class Evidence:
    """一条可引用的证据。Agent 的每条 fact 都必须指向其中之一。

    `file:line` 放在结构化字段里（而非 content 文本内），这样即使 content 被截断，
    引用信息依然完整——这是源文档 §2.3-4 与织忆「截断用同一个对象写两处」经验的结合。
    """

    chunk_id: int
    path: str
    lineno: int
    end_lineno: int
    qualname: str | None
    snippet: str
    score: float = 0.0
    lanes: tuple[str, ...] = ()
    concept_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConceptInstance:
    """一个技术概念在项目中的具体落点。源文档 §2.6「结合项目」。

    `evidence` 说明是靠什么规则认出来的（例如 `import jwt` / `decorator @app.get`），
    让结论可追溯、可质疑。
    """

    concept_id: str
    path: str
    lineno: int
    qualname: str | None = None
    symbol_id: int | None = None
    evidence: str = ""
    confidence: float = 1.0


@dataclass(frozen=True)
class Citation:
    """答案里的一条引用。"""

    path: str
    lineno: int
    end_lineno: int = 0
    qualname: str | None = None
    snippet: str = ""

    @property
    def location(self) -> str:
        return f"{self.path}:{self.lineno}"


@dataclass
class Answer:
    """Agent 的回答。

    事实与推断**分开存放**（源文档 §2.3-6「区分可验证的代码事实与模型推断」）：
    `facts` 里的每一条都必须有 citation；`inferences` 里的明确标注为推断。
    """

    text: str = ""
    facts: list[dict[str, Any]] = field(default_factory=list)
    inferences: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    abstained: bool = False
    abstention_reason: str = ""
