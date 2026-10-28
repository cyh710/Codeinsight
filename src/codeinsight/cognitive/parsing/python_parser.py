"""Python 解析器。

只用标准库 `ast`（ADR 0001）：少一个编译依赖、免跨平台编译坑，
`LanguageParser` Protocol 留口，以后换 tree-sitter 或加别的语言都不动上层。

产出的三类东西（源文档 §2.1-4 符号 · §2.2-1/2/3 关系）：
- **符号**：module / class / function / method / property / constant
- **边**：call / inherits / imports / decorator / references
- **导入**：给依赖识别（§2.1-1）用

两个不能妥协的点（源文档 §2.2、AGENTS.md 3.4）：

1. **静态分析定不了的调用不能丢弃，也不能假装确定。**
   `getattr(obj, "name")()` 这类动态调用产出 `confidence=0.5` 的边，
   `dst_qualname=None`。上层据此标"不确定"。
2. **解析失败不抛异常**（ADR 0012）。语法错误文件产出空符号集，
   由索引器记为 skipped——一个坏文件不该让整次索引失败。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from codeinsight.cognitive.parsing.base import ParseContext
from codeinsight.models import (
    EdgeKind,
    ParsedEdge,
    ParsedFile,
    ParsedImport,
    ParsedSymbol,
    SymbolKind,
)

# 动态调用标记：命中就是"静态分析定不了"。
DYNAMIC_CALL_NAMES: frozenset[str] = frozenset(
    {
        "getattr",
        "setattr",
        "delattr",
        "hasattr",
        "__import__",
        "import_module",
        "eval",
        "exec",
        "compile",
        "globals",
        "locals",
        "vars",
    }
)

# 这些装饰器把函数变成 property。
PROPERTY_DECORATORS: frozenset[str] = frozenset(
    {"property", "cached_property", "cached", "lazy_attribute"}
)


@dataclass
class _Scope:
    """当前正在收集的作用域。"""

    owner: str
    """产生边的符号 qualname（边挂在谁身上）。"""

    class_qualname: str | None = None
    """外层类的 qualname，用来解析 `self.method()`。"""


@dataclass
class _Collector:
    """一次文件解析的累加器。"""

    module_qualname: str
    symbols: list[ParsedSymbol] = field(default_factory=list)
    edges: list[ParsedEdge] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)

    # 名字 → 本文件内符号的 qualname。用于把调用解析到具体符号。
    local: dict[str, str] = field(default_factory=dict)
    # qualname → 符号类型，用来区分 method / function
    kinds: dict[str, SymbolKind] = field(default_factory=dict)
    shadowed: dict[str, set[str]] = field(default_factory=dict)
    parents: dict[str, str] = field(default_factory=dict)

    def add_symbol(self, sym: ParsedSymbol) -> None:
        self.symbols.append(sym)
        self.local.setdefault(sym.name, sym.qualname)
        self.local[sym.qualname] = sym.qualname
        self.kinds[sym.qualname] = sym.kind

    def add_edge(
        self,
        src: str,
        dst_name: str,
        kind: EdgeKind,
        lineno: int,
        *,
        dst_qualname: str | None = None,
        confidence: float = 1.0,
    ) -> None:
        self.edges.append(
            ParsedEdge(
                src_qualname=src,
                dst_name=dst_name,
                kind=kind,
                lineno=lineno,
                dst_qualname=dst_qualname,
                confidence=confidence,
            )
        )


def _dotted_name(node: ast.AST) -> str | None:
    """把 `a.b.c` 形式的 AST 还原成点号字符串；不是属性链则返回 None。"""
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


def _base_name(node: ast.AST) -> str | None:
    """取属性链最底层的名字（`a.b.c` → `a`）。"""
    current = node
    while isinstance(current, ast.Attribute):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


def _decorator_name(node: ast.expr) -> str:
    """装饰器名：`@app.get` → `app.get`，`@decorator` → `decorator`。"""
    if isinstance(node, ast.Call):
        return _dotted_name(node.func) or "<call>"
    return _dotted_name(node) or "<expr>"


def _leaf(name: str) -> str:
    """取点号路径的最后一段。"""
    return name.rsplit(".", 1)[-1]


def _is_constant_name(name: str) -> bool:
    """模块级常量命名：`MAX_CHUNK_LINES` / `_PRIVATE_CONST` / `X1` 都算。"""
    stripped = name.lstrip("_")
    return bool(stripped) and stripped.upper() == stripped and any(c.isalpha() for c in stripped)


class PythonParser:
    """标准库 `ast` 实现的 Python 解析器。"""

    language = "python"

    def supports(self, path: str) -> bool:
        return path.endswith((".py", ".pyi"))

    # ── 对外入口 ────────────────────────────────────────────────

    def parse(self, path: str, source: str, ctx: ParseContext) -> ParsedFile:
        """解析一个 Python 文件。

        **不抛异常**（ADR 0012）：语法错误、编码错误都降级成空符号集。
        """
        module_qn = _module_qualname(path)
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            return ParsedFile(path=path, language=self.language)

        collector = _Collector(module_qualname=module_qn)
        lines = source.splitlines()
        n_lines = len(lines)

        collector.add_symbol(
            ParsedSymbol(
                qualname=module_qn,
                name=module_qn.rsplit(".", 1)[-1] or path,
                kind=SymbolKind.MODULE,
                lineno=1,
                end_lineno=max(1, n_lines),
                header=lines[0].strip() if lines else "",
                docstring=ast.get_docstring(tree),
                n_lines=n_lines,
            )
        )

        # 当前文件所属的**包**——相对导入要靠它解析成绝对模块路径。
        # `backend/api/__init__.py` 的包是它自己；`backend/api/pet.py` 的包是 `backend.api`。
        if path.endswith("__init__.py"):
            package = module_qn
        else:
            package = module_qn.rsplit(".", 1)[0] if "." in module_qn else ""

        self._visit_body(collector, tree.body, module_qn, None, module_qn, lines, package)
        return ParsedFile(
            path=path,
            language=self.language,
            module_docstring=ast.get_docstring(tree),
            imports=tuple(collector.imports),
            symbols=tuple(collector.symbols),
            edges=tuple(collector.edges),
        )

    # ── 符号收集 ────────────────────────────────────────────────

    def _visit_body(
        self,
        col: _Collector,
        body: list[ast.stmt],
        prefix: str,
        class_qualname: str | None,
        owner: str,
        lines: list[str],
        package: str,
    ) -> None:
        """遍历一段语句体，收集符号与边。

        `prefix` 是 qualname 前缀，`owner` 是边挂在哪个符号上，
        `class_qualname` 用于解析 `self.method()`。
        """
        for node in body:
            if isinstance(node, ast.ClassDef):
                self._handle_class(col, node, prefix, lines, package)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._handle_function(col, node, prefix, class_qualname, lines, package)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                self._handle_import(col, node, owner, package)
            elif isinstance(node, ast.Assign):
                self._handle_assign(col, node, prefix, class_qualname, owner, lines)
            elif isinstance(node, ast.AnnAssign):
                self._handle_ann_assign(col, node, prefix, class_qualname, owner, lines)
            else:
                # 其余语句：只找调用与引用
                self._scan(col, node, _Scope(owner=owner, class_qualname=class_qualname))

    def _handle_class(
        self,
        col: _Collector,
        node: ast.ClassDef,
        prefix: str,
        lines: list[str],
        package: str,
    ) -> None:
        qualname = f"{prefix}.{node.name}"
        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        col.add_symbol(
            ParsedSymbol(
                qualname=qualname,
                name=node.name,
                kind=SymbolKind.CLASS,
                lineno=node.lineno,
                end_lineno=end,
                header=_header_of(lines, node.lineno),
                docstring=ast.get_docstring(node),
                parent_qualname=prefix,
                is_private=node.name.startswith("_") and not _is_dunder(node.name),
                is_dunder=_is_dunder(node.name),
                n_lines=end - node.lineno + 1,
            )
        )

        for base in node.bases:
            dst = _dotted_name(base)
            if dst:
                col.add_edge(
                    qualname,
                    dst,
                    EdgeKind.INHERITS,
                    node.lineno,
                    dst_qualname=self._resolve(col, dst, qualname),
                )
            else:
                # 基类是动态表达式（如 `metaclass=...` 之外的计算结果）——记不出来就记不出来
                continue

        for deco in node.decorator_list:
            col.add_edge(qualname, _decorator_name(deco), EdgeKind.DECORATOR, node.lineno)

        # 类体里继续收集：方法、嵌套类、类属性
        self._visit_body(col, node.body, qualname, qualname, qualname, lines, package)

    def _handle_function(
        self,
        col: _Collector,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        prefix: str,
        class_qualname: str | None,
        lines: list[str],
        package: str,
    ) -> None:
        qualname = f"{prefix}.{node.name}"
        bindings = _LocalBindings()
        for statement in node.body:
            bindings.visit(statement)
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        arguments += [arg for arg in (node.args.vararg, node.args.kwarg) if arg is not None]
        parameters = {arg.arg for arg in arguments}
        if class_qualname:
            parameters -= {"self", "cls"}
        col.shadowed[qualname] = bindings.names | parameters
        col.parents[qualname] = prefix
        end = getattr(node, "end_lineno", node.lineno) or node.lineno

        deco_names = [_decorator_name(d) for d in node.decorator_list]
        is_property = any(_leaf(n) in PROPERTY_DECORATORS for n in deco_names)
        if class_qualname is not None:
            kind = SymbolKind.PROPERTY if is_property else SymbolKind.METHOD
        else:
            kind = SymbolKind.FUNCTION

        col.add_symbol(
            ParsedSymbol(
                qualname=qualname,
                name=node.name,
                kind=kind,
                lineno=node.lineno,
                end_lineno=end,
                header=_header_of(lines, node.lineno),
                docstring=ast.get_docstring(node),
                parent_qualname=prefix,
                is_async=isinstance(node, ast.AsyncFunctionDef),
                is_private=node.name.startswith("_") and not _is_dunder(node.name),
                is_dunder=_is_dunder(node.name),
                n_lines=end - node.lineno + 1,
            )
        )

        for deco in node.decorator_list:
            col.add_edge(qualname, _decorator_name(deco), EdgeKind.DECORATOR, node.lineno)

        # 函数体里的调用/引用挂在函数上；嵌套函数与嵌套类继续收集。
        # 扫描交给 _visit_body 统一做——在这里再扫一遍会重复记边。
        self._visit_body(col, node.body, qualname, class_qualname, qualname, lines, package)

    def _handle_assign(
        self,
        col: _Collector,
        node: ast.Assign,
        prefix: str,
        class_qualname: str | None,
        owner: str,
        lines: list[str],
    ) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name) and _is_constant_name(target.id):
                end = getattr(node, "end_lineno", node.lineno) or node.lineno
                col.add_symbol(
                    ParsedSymbol(
                        qualname=f"{prefix}.{target.id}",
                        name=target.id,
                        kind=SymbolKind.CONSTANT,
                        lineno=node.lineno,
                        end_lineno=end,
                        header=_header_of(lines, node.lineno),
                        parent_qualname=prefix,
                        n_lines=1,
                    )
                )
        self._scan(col, node.value, _Scope(owner=owner, class_qualname=class_qualname))

    def _handle_ann_assign(
        self,
        col: _Collector,
        node: ast.AnnAssign,
        prefix: str,
        class_qualname: str | None,
        owner: str,
        lines: list[str],
    ) -> None:
        target = node.target
        if isinstance(target, ast.Name) and _is_constant_name(target.id):
            end = getattr(node, "end_lineno", node.lineno) or node.lineno
            col.add_symbol(
                ParsedSymbol(
                    qualname=f"{prefix}.{target.id}",
                    name=target.id,
                    kind=SymbolKind.CONSTANT,
                    lineno=node.lineno,
                    end_lineno=end,
                    header=_header_of(lines, node.lineno),
                    parent_qualname=prefix,
                    n_lines=1,
                )
            )
        if node.value is not None:
            self._scan(col, node.value, _Scope(owner=owner, class_qualname=class_qualname))

    def _handle_import(
        self,
        col: _Collector,
        node: ast.Import | ast.ImportFrom,
        owner: str,
        package: str,
    ) -> None:
        """记录导入。

        边上的 `dst_name` 用**完整模块路径**，不是顶层包名——
        `from backend.config import settings` 记成 'backend.config' 而不是 'backend'，
        否则项目内部 110 条导入全变成同一个名字，既没法分析模块依赖（§2.2-3），
        也没法做概念检测。

        代价是本体里的 `import_names: [jwt]` 要按「相等或前缀」匹配
        （'jwt' 命中 'jwt'，也命中 'jwt.algorithms'）。这条规则写进规格了。
        """
        if isinstance(node, ast.Import):
            for alias in node.names:
                col.imports.append(
                    ParsedImport(
                        module=alias.name,
                        names=(alias.asname or alias.name.split(".")[0],),
                        lineno=node.lineno,
                    )
                )
                col.add_edge(owner, alias.name, EdgeKind.IMPORTS, node.lineno)
            return

        module = node.module or ""
        names = tuple(a.name for a in node.names)
        # 本地名与原始名可能不同（`from a import b as c`）——
        # 名字解析要用本地名匹配调用点，用原始名拼仓库内 qualname。
        local_names = tuple(a.asname or a.name for a in node.names)
        is_relative = node.level > 0
        if is_relative:
            # 相对导入要解析成绝对模块路径——相对路径本身没法用于依赖分析。
            base = package
            for _ in range(node.level - 1):
                base = base.rsplit(".", 1)[0] if "." in base else ""
            module = f"{base}.{node.module}" if node.module and base else (node.module or base)

        col.imports.append(
            ParsedImport(
                module=module,
                names=names,
                lineno=node.lineno,
                is_relative=is_relative,
                local_names=local_names,
            )
        )
        if module:
            # 相对导入能确定是仓库内部的模块，直接给 dst_qualname；
            # 绝对导入要靠索引器用全局模块表解析（这里还不知道）。
            col.add_edge(
                owner,
                module,
                EdgeKind.IMPORTS,
                node.lineno,
                dst_qualname=module if is_relative else None,
            )

    # ── 调用与引用扫描 ──────────────────────────────────────────

    def _scan(self, col: _Collector, node: ast.AST, scope: _Scope) -> None:
        """处理一个节点，并递归它的子节点。

        自己递归而不是用 `ast.walk`——要避免把 `a.b()` 的 `a.b` 又记成一条引用。
        注意**节点自身**也要判：传进来的是 `obj.attr` 时，要记的是它本身，
        不是它的子节点。
        """
        if isinstance(node, ast.Call):
            self._emit_call(col, node, scope)
            func = node.func
            if isinstance(func, ast.Attribute):
                # 属性链只取最底层：`a.b.c()` 记成一条调用，不是三条
                base = func
                while isinstance(base, ast.Attribute):
                    base = base.value
                self._scan(col, base, scope)
            elif isinstance(func, ast.Call):
                # `getattr(obj, "x")()` —— 被调者本身是个调用表达式，
                # 里层那一次也得扫，否则动态调用的边就丢了。
                self._scan(col, func, scope)
            for arg in node.args:
                self._scan(col, arg, scope)
            for kw in node.keywords:
                self._scan(col, kw.value, scope)
            return

        if isinstance(node, ast.Attribute):
            self._emit_reference(col, node, scope)
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            self._scan(col, base, scope)
            return

        for child in ast.iter_child_nodes(node):
            self._scan(col, child, scope)

    def _emit_call(self, col: _Collector, node: ast.Call, scope: _Scope) -> None:
        func = node.func
        root = func.id if isinstance(func, ast.Name) else _base_name(func)
        owner = scope.owner
        shadowed = False
        while owner in col.shadowed:
            if root in col.shadowed[owner]:
                shadowed = True
                break
            owner = col.parents.get(owner, "")
        if shadowed:
            col.add_edge(
                scope.owner, _dotted_name(func) or root, EdgeKind.CALL, node.lineno, confidence=0.5
            )
            return
        if isinstance(func, ast.Name):
            dst_name = func.id
            dst_qual = col.local.get(func.id)
        elif isinstance(func, ast.Attribute):
            dst_name = _dotted_name(func)
            if dst_name is None:
                return
            dst_qual = self._resolve(col, dst_name, scope)
        else:
            # 订阅调用 `f[0]()`、lambda 立即调用等——记不出被调者
            return

        if dst_name.split(".")[0] in DYNAMIC_CALL_NAMES or dst_name in DYNAMIC_CALL_NAMES:
            # 动态调用：保留边，但标不确定（源文档 §2.2）
            col.add_edge(
                scope.owner,
                dst_name,
                EdgeKind.CALL,
                node.lineno,
                dst_qualname=None,
                confidence=0.5,
            )
            return

        col.add_edge(
            scope.owner,
            dst_name,
            EdgeKind.CALL,
            node.lineno,
            dst_qualname=dst_qual,
        )

    def _emit_reference(self, col: _Collector, node: ast.Attribute, scope: _Scope) -> None:
        """属性被读取但没被调用。"""
        dst_name = _dotted_name(node)
        if dst_name is None:
            return
        base = _base_name(node)
        if base in {"self", "cls"}:
            # 实例/类属性：记属性名本身，`self.redis` → 'redis'
            dst_name = node.attr
            dst_qual = f"{scope.class_qualname}.{node.attr}" if scope.class_qualname else None
        else:
            dst_qual = self._resolve(col, dst_name, scope)
        col.add_edge(
            scope.owner,
            dst_name,
            EdgeKind.REFERENCES,
            node.lineno,
            dst_qualname=dst_qual,
        )

    def _resolve(self, col: _Collector, dotted: str, scope: _Scope) -> str | None:
        """把点号路径解析成**本文件内**的符号 qualname。

        解析不出来就返回 None——同名多义时更不能随便挑一个（规格 §1.2 A3）。
        """
        parts = dotted.split(".")
        # `self.method()` / `cls.method()`
        if parts[0] in {"self", "cls"} and len(parts) == 2 and scope.class_qualname:
            candidate = f"{scope.class_qualname}.{parts[1]}"
            return candidate if candidate in col.local else None
        # `Class.method()`：Class 是本文件的类
        if len(parts) == 2 and parts[0] in col.local:
            candidate = f"{col.local[parts[0]]}.{parts[1]}"
            return candidate if candidate in col.local else None
        # 单个名字：本文件定义过的函数/类
        if len(parts) == 1:
            return col.local.get(parts[0])
        return None


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__") and len(name) > 4


class _LocalBindings(ast.NodeVisitor):
    """仅收集当前函数的值绑定，内层作用域不能污染外层调用解析。"""

    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.names.add(node.id)

    def visit_Import(self, node: ast.Import) -> None:
        self.names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.names.update(alias.asname or alias.name for alias in node.names)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.names.add(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return


def _header_of(lines: list[str], lineno: int) -> str:
    """取定义行的文本。"""
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].strip()
    return ""


def _module_qualname(path: str) -> str:
    """文件路径 → 模块 qualname。

    `backend/core/chunk_bm25.py` → `backend.core.chunk_bm25`
    `backend/__init__.py`         → `backend`
    """
    p = path
    if p.endswith(".py"):
        p = p[:-3]
    parts = [seg for seg in p.split("/") if seg]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)
