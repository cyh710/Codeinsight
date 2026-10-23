"""保留证据的概念检测；只把可追踪的名字和结构当确定命中。"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import replace

from codeinsight.cognitive.concepts.base import EdgeView, SymbolView
from codeinsight.cognitive.concepts.ontology import Concept
from codeinsight.models import ConceptInstance, EdgeKind


def _name(node: ast.AST) -> str | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join([node.id, *reversed(parts)])


def _scope_nodes(node: ast.AST):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(
            reversed(
                [
                    child
                    for child in ast.iter_child_nodes(current)
                    if not isinstance(
                        child, ast.Lambda | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
                    )
                ]
            )
        )


class _Source:
    def __init__(self, text: str) -> None:
        self.tree = ast.parse(text)
        self.scopes = [
            n
            for n in ast.walk(self.tree)
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        ]
        self._bindings_cache: dict[tuple[int, ...], dict[str, str | None]] = {}

    def owner(self, lineno: int) -> ast.AST:
        enclosing = [n for n in self.scopes if n.lineno <= lineno <= (n.end_lineno or n.lineno)]
        return (
            min(enclosing, key=lambda n: (n.end_lineno or n.lineno) - n.lineno)
            if enclosing
            else self.tree
        )

    def resolve(self, dotted: str, lineno: int) -> str | None:
        scopes = [
            self.tree,
            *sorted(
                (n for n in self.scopes if n.lineno <= lineno <= (n.end_lineno or n.lineno)),
                key=lambda n: -(n.end_lineno or n.lineno) + n.lineno,
            ),
        ]
        cache_key = tuple(getattr(scope, "lineno", 0) for scope in scopes)
        bindings = self._bindings_cache.get(cache_key)
        if bindings is not None:
            return self._resolve_binding(dotted, bindings)
        bindings = {}
        for scope in scopes:
            if isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef):
                args = scope.args
                for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs):
                    bindings[arg.arg] = None
                for arg in (args.vararg, args.kwarg):
                    if arg:
                        bindings[arg.arg] = None
            for node in _scope_nodes(scope):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        bindings[alias.asname or alias.name.split(".")[0]] = (
                            alias.name if alias.asname else alias.name.split(".")[0]
                        )
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    for alias in node.names:
                        bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
                elif isinstance(node, ast.Assign | ast.AnnAssign):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    target_name = _name(targets[0]) if len(targets) == 1 else None
                    canonical = None
                    if isinstance(node.value, ast.Call) and (called := _name(node.value.func)):
                        head, _, tail = called.partition(".")
                        base = bindings.get(head)
                        if base:
                            canonical = base + (f".{tail}" if tail else "")
                    if target_name:
                        bindings[target_name] = canonical
        self._bindings_cache[cache_key] = bindings
        return self._resolve_binding(dotted, bindings)

    @staticmethod
    def _resolve_binding(dotted: str, bindings: dict[str, str | None]) -> str | None:
        # self.client 之类采用最长的已知绑定，不猜测未知对象的类型。
        for index in range(len(dotted.split(".")), 0, -1):
            key = ".".join(dotted.split(".")[:index])
            if key in bindings:
                value = bindings[key]
                suffix = dotted[len(key) :]
                return value + suffix if value else None
        return None


class RuleBasedDetector:
    """兼容 ConceptDetector；可选冻结源码和原始边置信度加强检测，不读工作区。"""

    def __init__(self, concepts: Mapping[str, Concept]) -> None:
        self.concepts = dict(concepts)
        self.errors: list[str] = []

    def detect(
        self,
        symbols: Sequence[SymbolView],
        edges: Sequence[EdgeView],
        *,
        sources: Mapping[str, str] | None = None,
        edge_confidences: Mapping[tuple[str, int, str, str], float] | None = None,
    ) -> list[ConceptInstance]:
        """每处实例独立带证据；无源码时不做字符串检测，坏文件只记错误。"""
        self.errors = []
        analyses: dict[str, _Source] = {}
        for path, text in (sources or {}).items():
            try:
                analyses[path] = _Source(text)
            except (SyntaxError, ValueError, RecursionError) as exc:
                self.errors.append(f"{path}: 语法分析失败，跳过结构检测：{exc}")
        by_name = {(s.path, s.qualname): s for s in symbols}
        matches: dict[tuple[str, str, int], ConceptInstance] = {}

        def emit(
            cid: str, path: str, lineno: int, qualname: str | None, evidence: str, confidence: float
        ) -> None:
            if cid not in self.concepts or not 0 <= confidence <= 1:
                return
            key = (cid, path, lineno)
            previous = matches.get(key)
            if previous:
                parts = sorted(set(previous.evidence.split("；")) | {evidence})
                matches[key] = replace(
                    previous,
                    evidence="；".join(parts),
                    confidence=max(previous.confidence, confidence),
                )
            else:
                matches[key] = ConceptInstance(
                    cid, path, lineno, qualname=qualname, evidence=evidence, confidence=confidence
                )

        for edge in edges:
            kind = str(edge.kind)
            source = analyses.get(edge.path)
            resolved = source.resolve(edge.dst_name, edge.lineno) if source else None
            key = (edge.path, edge.lineno, kind, edge.dst_name)
            confidence = (edge_confidences or {}).get(key, getattr(edge, "confidence", 0.5))
            if not isinstance(confidence, int | float) or not 0 <= confidence <= 1:
                confidence = 0.5
            for concept in self.concepts.values():
                rules = concept.detection
                matched = False
                qualified = False
                if kind == EdgeKind.IMPORTS:
                    # 导入只证明依赖关系，不证明缓存/事务等机制已经实现。
                    matched = any(
                        edge.dst_name == r or edge.dst_name.startswith(r + ".")
                        for r in rules.import_names
                    )
                    confidence_for_match = min(confidence, 0.6)
                else:
                    candidates = {
                        EdgeKind.CALL: rules.call_names,
                        EdgeKind.DECORATOR: rules.decorator_names,
                        EdgeKind.INHERITS: rules.base_classes,
                        EdgeKind.REFERENCES: rules.attribute_names,
                    }.get(kind, ())
                    qualified = any(resolved == rule for rule in candidates)
                    direct = any(edge.dst_name == rule and "." in rule for rule in candidates)
                    if source:
                        # 源码出现同名局部参数/变量时，不能让原始点号字符串绕过消歧。
                        direct = direct and resolved is not None
                    matched = qualified or direct
                    if not matched and not source:
                        matched = any(
                            edge.dst_name.rsplit(".", 1)[-1] == r.rsplit(".", 1)[-1]
                            for r in candidates
                        )
                    confidence_for_match = min(confidence, 1.0 if qualified or direct else 0.4)
                if not matched:
                    continue
                if concept.id == "db-transaction":
                    # execute/commit 和数据库导入均不足以独立认定事务；结构分支另行取证。
                    continue
                if concept.id in {"redis-cache", "singleton-lazy"}:
                    confidence_for_match = min(confidence_for_match, 0.6)
                if concept.id == "structured-logging" and resolved != "structlog.get_logger":
                    # 普通 logger 不足以证明采用结构化格式；只保留待核对的关联。
                    confidence_for_match = min(confidence_for_match, 0.6)
                if concept.id == "connection-pool" and resolved == "sqlalchemy.create_engine":
                    confidence_for_match = min(confidence_for_match, 0.6)
                emit(
                    concept.id,
                    edge.path,
                    edge.lineno,
                    edge.src_qualname,
                    f"{kind} {edge.dst_name}"
                    + (f" → {resolved}" if resolved and resolved != edge.dst_name else ""),
                    confidence_for_match,
                )

        for path, source in analyses.items():
            for node in [source.tree, *source.scopes]:
                lineno = getattr(node, "lineno", 1)
                owner_symbols = [
                    s for s in symbols if s.path == path and s.lineno <= lineno <= s.end_lineno
                ]
                owner = (
                    min(owner_symbols, key=lambda s: s.end_lineno - s.lineno)
                    if owner_symbols
                    else None
                )
                qualname = owner.qualname if owner else None
                decorators = getattr(node, "decorator_list", ())
                if decorators:
                    emit(
                        "decorator",
                        path,
                        decorators[0].lineno,
                        qualname,
                        "结构 @decorator：定义对象时应用装饰器",
                        1.0,
                    )
                if isinstance(node, ast.ClassDef):
                    continue
                nodes = list(_scope_nodes(node))
                calls = [n for n in nodes if isinstance(n, ast.Call)]
                if isinstance(node, ast.AsyncFunctionDef):
                    emit("async", path, node.lineno, qualname, "结构 async def：协程函数声明", 1.0)
                yields = [n for n in nodes if isinstance(n, ast.Yield | ast.YieldFrom)]
                if yields:
                    emit(
                        "generator",
                        path,
                        yields[0].lineno,
                        qualname,
                        "结构 yield：函数按需产生值",
                        1.0,
                    )
                with_nodes = [n for n in nodes if isinstance(n, ast.With | ast.AsyncWith)]
                if with_nodes:
                    emit(
                        "context-manager",
                        path,
                        with_nodes[0].lineno,
                        qualname,
                        "结构 with/async with：通过上下文协议管理进入与退出",
                        1.0,
                    )
                commits: dict[str, list[ast.Call]] = defaultdict(list)
                begins: dict[str, list[ast.Call]] = defaultdict(list)
                cache_ops: dict[str, set[str]] = defaultdict(set)
                for call in calls:
                    dotted = _name(call.func)
                    if not dotted or "." not in dotted:
                        continue
                    receiver, method = dotted.rsplit(".", 1)
                    if method == "commit":
                        commits[receiver].append(call)
                    if method == "execute" and call.args and isinstance(call.args[0], ast.Constant):
                        sql = call.args[0].value
                        if isinstance(sql, str) and re.match(
                            r"^\s*(?:BEGIN|SAVEPOINT)\b", sql, re.IGNORECASE
                        ):
                            begins[receiver].append(call)
                    canonical = source.resolve(dotted, call.lineno)
                    if canonical and canonical.startswith(
                        ("redis.Redis.", "redis.StrictRedis.", "redis.asyncio.Redis.")
                    ):
                        cache_ops[receiver].add(method)
                for receiver in begins.keys() & commits.keys():
                    begin = begins[receiver][0]
                    # 同一作用域、同一连接的 BEGIN 与 commit 才构成组合证据。
                    emit(
                        "db-transaction",
                        path,
                        begin.lineno,
                        qualname,
                        f"组合证据：{receiver}.execute 开启事务；同作用域 {receiver}.commit 提交",
                        0.95,
                    )
                for receiver, methods in cache_ops.items():
                    if methods & {"get", "mget"} and methods & {"set", "setex", "mset"}:
                        emit(
                            "redis-cache",
                            path,
                            lineno,
                            qualname,
                            f"组合证据：{receiver} 来源为 Redis 客户端，并有读写键值调用；缓存用途仍需核对",
                            0.8,
                        )
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    if not (
                        node.args.posonlyargs
                        or node.args.args
                        or node.args.kwonlyargs
                        or node.args.vararg
                        or node.args.kwarg
                    ):
                        for decorator in node.decorator_list:
                            function = (
                                decorator.func if isinstance(decorator, ast.Call) else decorator
                            )
                            name = _name(function)
                            canonical = source.resolve(name, node.lineno) if name else None
                            if canonical == "functools.cache" or (
                                canonical == "functools.lru_cache"
                                and isinstance(decorator, ast.Call)
                                and any(
                                    k.arg == "maxsize"
                                    and isinstance(k.value, ast.Constant)
                                    and k.value.value == 1
                                    for k in decorator.keywords
                                )
                            ):
                                emit(
                                    "singleton-lazy",
                                    path,
                                    node.lineno,
                                    qualname,
                                    "组合证据：无参数工厂函数使用 functools 缓存；并发首次构造仍可能重复",
                                    0.9,
                                )

        # 字符串只加强已有同作用域命中，不因注释/文档或单独字符串生成实例。
        string_cache: dict[tuple[str, int], list[tuple[int, str]]] = {}
        for key, instance in list(matches.items()):
            markers = self.concepts[instance.concept_id].detection.string_markers
            source = analyses.get(instance.path)
            if not markers or source is None:
                continue
            owner = source.owner(instance.lineno)
            scope_key = (instance.path, getattr(owner, "lineno", 0))
            if scope_key not in string_cache:
                doc = (
                    ast.get_docstring(owner)
                    if isinstance(
                        owner, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
                    )
                    else None
                )
                string_cache[scope_key] = [
                    (node.lineno, node.value)
                    for node in _scope_nodes(owner)
                    if isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and node.value != doc
                ]
            extra = [
                f"辅助字符串 {line}: {marker}"
                for line, value in string_cache[scope_key]
                for marker in markers
                if marker in value
            ]
            if extra:
                matches[key] = replace(
                    instance, evidence=instance.evidence + "；" + "；".join(sorted(set(extra)))
                )

        # 对只提供符号的调用方仍能确定 async 声明；不从 docstring 猜字符串实例。
        for symbol in by_name.values():
            if symbol.header.lstrip().startswith("async def ") and symbol.path not in analyses:
                emit(
                    "async", symbol.path, symbol.lineno, symbol.qualname, "符号签名 async def", 1.0
                )
        return sorted(matches.values(), key=lambda i: (i.concept_id, i.path, i.lineno))
