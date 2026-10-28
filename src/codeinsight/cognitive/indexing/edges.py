"""关系边落库与解析（规格 §1.2 A3）。

边的三种结局：

1. **能唯一解析到仓库内符号** → `dst_symbol_id` 有值。
2. **目标存在但同名多义** → `dst_symbol_id` 留 NULL，靠 `dst_name`/`dst_qualname`
   保留线索。**不猜。**
3. **目标是仓库外的东西**（第三方库、builtin、动态调用）→ `dst_symbol_id` 为 NULL，
   `confidence < 1` 表示这条边是推断的。

名字解析沿用 Python 的语义：`import a.b` 把名字 `a` 绑到模块 `a`；
`from a import b` 把名字 `b` 绑到 `a` 里的某个符号或子模块。
两种绑定的候选拼法不同，所以 `SymbolIndex` 分开存。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from codeinsight.cognitive.indexing.symbols import SymbolIndex
from codeinsight.models import EdgeKind, ParsedEdge

# 这些名字在运行时才能确定具体目标——静态分析给不出确定答案。
DYNAMIC_BUILTINS: frozenset[str] = frozenset(
    {
        "getattr",
        "setattr",
        "hasattr",
        "delattr",
        "import_module",
        "__import__",
        "eval",
        "exec",
        "compile",
        "globals",
        "locals",
        "vars",
    }
)


@dataclass
class FileSymbolScope:
    """一个文件里的符号（用于把边的 `src` 落到具体符号行）。

    解析器给的 `src_qualname` 是「作用域 qualname」，但一个文件里可能有同名
    的重定义（条件分支里 def 两次）。所以按**行号区间**定位最准：
    边所在的那一行落在哪个符号的范围内，就是哪个符号发出的边。
    """

    entries: list[tuple[str, int, int, int]] = field(default_factory=list)
    """(qualname, lineno, end_lineno, symbol_id)"""

    def resolve(self, qualname: str, lineno: int) -> int | None:
        """找到发出这条边的符号 id。

        优先取行号区间包含 `lineno` 的那个；找不到就退回同名里唯一的那个。
        """
        candidates = [e for e in self.entries if e[0] == qualname]
        if not candidates:
            return None
        for _, start, end, symbol_id in candidates:
            if start <= lineno <= end:
                return symbol_id
        if len(candidates) == 1:
            return candidates[0][3]
        return None


@dataclass
class ImportBindings:
    """一个模块里的名字绑定。

    - `plain`：来自 `import a.b` / `import a.b as z` → 名字绑到**模块路径**。
    - `from_imports`：来自 `from a import b` → 名字绑到**a 里的符号或子模块**，
      值为 `(a, b)`：来源模块 + 原始名（原始名用来拼 qualname）。
    """

    plain: dict[str, str] = field(default_factory=dict)
    from_imports: dict[str, tuple[str, str]] = field(default_factory=dict)

    def candidates(self, local_name: str, rest: str) -> list[str]:
        """给定被调/被引用的名字，列出可能的仓库内 qualname。"""
        if local_name in self.plain:
            path = self.plain[local_name]
            return [f"{path}.{rest}" if rest else path]
        if local_name in self.from_imports:
            path, original = self.from_imports[local_name]
            if rest:
                # 原始名可能是来源模块的子模块（a.b.rest），
                # 也可能是来源模块里的符号（a.rest）。
                return [f"{path}.{original}.{rest}", f"{path}.{rest}"]
            return [f"{path}.{original}"]
        return []


def build_bindings(imports) -> ImportBindings:
    """从解析出的 import 列表构造名字绑定。

    `ParsedImport.module` 是**绝对模块路径**（相对导入已在解析器里解析过）。
    `names` 是原始名，`local_names` 是本地名；缺省时两者相同。
    """
    bindings = ImportBindings()
    for imp in imports:
        module = imp.module
        if not module:
            continue
        locals_ = imp.local_names or imp.names
        for original, local in zip(imp.names, locals_, strict=False):
            if not local or not original:
                continue
            if original == module.split(".")[0] and local == original:
                # `import a.b` → 名字 `a` 绑到顶层包 `a`
                bindings.plain[local] = original
            elif local != original and module.endswith(original):
                # `import a.b as b` → 名字 `b` 绑到模块 `a.b`
                bindings.plain[local] = module
            elif local != original and "." not in module:
                # `import numpy as np` → 名字 `np` 绑到模块 `numpy`
                bindings.plain[local] = module
            else:
                # `from a import b` → 名字 `b` 绑到 `a` 里
                bindings.from_imports[local] = (module, original)
    return bindings


class EdgeResolver:
    """把边的 `dst` 解析成仓库内符号 id。

    解析顺序（先确定的后确定）：
    1. 解析器已经给出的全限定 `dst_qualname`——直接查，唯一命中才用。
    2. 按 import 绑定拼候选 qualname（`import`/`from` 两种拼法不同）。
    3. 同模块的模块级符号（`helper()` 这种）。
    4. 都命中不了 → 留 NULL。**不猜。**

    候选顺序随边种类变：

    - **调用边** `jwt.decode(...)`：目标是 `jwt.decode` 这个函数 → 先试整串。
    - **引用边** `settings.timeout`：目标是 `settings` 这个对象，属性是它的属性 →
      先试头段。解析到 `backend.config.settings` 比解析不到有用得多。

    两种顺序都只接受**唯一命中**，所以先试谁都不会引入错边。
    """

    def __init__(self, index: SymbolIndex, bindings: dict[str, ImportBindings]) -> None:
        self._index = index
        self._bindings = bindings

    def resolve(self, edge: ParsedEdge, src_module: str | None) -> tuple[str, int] | None:
        """解析边的目标，返回 `(qualname, symbol_id)`；解不出来返回 None。

        返回 qualname 是为了让落库时把 `dst_qualname` 写成**解析后的**那个——
        一行边里 `dst_name`（解析器看到的）、`dst_qualname`（解析到的）、
        `dst_symbol_id`（库里的行）必须指向同一个东西，否则读边的人会看到
        「名字是 A、指向的却是 B」。
        """
        if edge.kind is EdgeKind.CALL and edge.confidence < 1:
            return None
        if edge.dst_qualname:
            # 解析器已经给出了全限定名——它是**更强的证据**。
            # 多义就留 NULL，绝不退回按短名猜：短名在全项目里撞车极多
            # （`_provider` 在几十个类里都有），猜错会造出假边。
            found = self._index.unique(edge.dst_qualname)
            return (edge.dst_qualname, found) if found is not None else None

        name = edge.dst_name
        if not name:
            return None

        if edge.kind is EdgeKind.IMPORTS:
            # import 边的目标是**模块**——模块在 `symbol` 表里有一条 kind='module' 的行，
            # 解析到它之后，「模块依赖分析」（§2.2-3）才是真的图而不是字符串列表。
            found = self._index.unique(name)
            return (name, found) if found is not None else None

        local_name, _, rest = name.partition(".")

        head_candidates: list[str] = []
        chain_candidates: list[str] = []
        if src_module:
            bindings = self._bindings.get(src_module)
            if bindings is not None:
                head_candidates = bindings.candidates(local_name, "")
                chain_candidates = bindings.candidates(local_name, rest)

        if edge.kind is EdgeKind.REFERENCES:
            order = head_candidates + chain_candidates
        else:
            order = chain_candidates + head_candidates

        for candidate in order:
            found = self._index.unique(candidate)
            if found is not None:
                return candidate, found

        if not rest:
            # 裸名字：同模块的模块级函数/类/常量。
            if src_module:
                found = self._index.module_level(src_module, local_name)
                if found is not None:
                    return self._index.qualname_by_id[found], found
            # 全项目唯一的同名符号——同名多义就不认。
            ids = self._index.by_name.get(local_name) if edge.kind is not EdgeKind.CALL else None
            if ids and len(ids) == 1:
                qualname = self._index.qualname_by_id.get(ids[0])
                if qualname:
                    return qualname, ids[0]
        return None


def write_edges(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    scope: FileSymbolScope,
    edges: list[ParsedEdge],
    resolver: EdgeResolver,
    src_modules: dict[str, str],
) -> int:
    """写一个文件的边，返回写入条数。

    去重按 `UNIQUE(project_id, src_symbol_id, dst_qualname, dst_name, kind, lineno)`
    ——但 SQLite 认为 NULL 与 NULL 不相等，所以 `dst_qualname IS NULL` 的边
    在库里可以重复。这里在 Python 侧先去重，避免重跑索引时堆出重复行。
    """
    seen: set[tuple] = set()
    written = 0

    for edge in edges:
        src_id = scope.resolve(edge.src_qualname, edge.lineno)
        if src_id is None:
            # 找不到发出者——这条边挂不上去，跳过（宁可少一条边，
            # 也不要造一条 src 指向错误符号的边）。
            continue

        src_module = src_modules.get(edge.src_qualname)
        resolved = resolver.resolve(edge, src_module)
        dst_id = resolved[1] if resolved else None
        dst_qualname = resolved[0] if resolved else edge.dst_qualname

        key = (src_id, dst_qualname, edge.dst_name, str(edge.kind), edge.lineno)
        if key in seen:
            continue
        seen.add(key)

        conn.execute(
            """
            INSERT INTO edge (
                project_id, src_symbol_id, dst_symbol_id, src_qualname,
                dst_name, dst_qualname, kind, lineno, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                src_id,
                dst_id,
                edge.src_qualname,
                edge.dst_name,
                dst_qualname,
                str(edge.kind),
                edge.lineno,
                edge.confidence,
            ),
        )
        written += 1

    return written
