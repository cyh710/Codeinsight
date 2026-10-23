"""关键业务流程检测（规格 §1.2 A5，对应源文档 §2.2-4 / §2.1-6 / §2.4-4）。

**流程 = 从入口到有外部副作用的符号的一条路径。**

为什么这么定义：源文档 §2.1-6 说「识别主要业务流程」，
但「流程」本身不是代码里的对象——它是**入口**和**副作用**之间的连线。
只讲「入口 A 调用了 B、C、D」是调用图，不是流程；
只讲「这个函数会写数据库」是副作用清单，也不是流程。
两头都定下来，中间那条路才是流程。

副作用的判定用**调用的目标名字**，而不是猜：

- 目标模块在已知清单里（`os` `requests` `sqlite3` `subprocess` …）→ 副作用；
- 目标是某个对象的方法且方法名在动词清单里（`write` `commit` `execute` `post` …）→ 副作用。

这**是启发式**，会有误报（`config.update()` 会被当成写库）。
但流程检测的用途是「给出一条可读的链路」，多一条流比少一条流危害小；
而且这条判定不进入任何对外承诺的数字里——评测用的 ground truth 是人工标的。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

# 已知有外部副作用的模块（按 import 名的顶层部分匹配）
SIDE_EFFECT_MODULES: frozenset[str] = frozenset(
    {
        "os",
        "io",
        "shutil",
        "pathlib",
        "tempfile",
        "sys",
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "urllib3",
        "socket",
        "websockets",
        "subprocess",
        "sqlite3",
        "aiosqlite",
        "sqlalchemy",
        "psycopg",
        "psycopg2",
        "pymongo",
        "redis",
        "aiofiles",
        "chromadb",
        "logging",
        "loguru",
        "openai",
        "anthropic",
    }
)

# 明显是「往外写」的方法名（作用在对象上，不是模块上）
SIDE_EFFECT_VERBS: frozenset[str] = frozenset(
    {
        "write",
        "writelines",
        "writestr",
        "commit",
        "rollback",
        "execute",
        "executemany",
        "executescript",
        "insert",
        "upsert",
        "save",
        "delete",
        "post",
        "put",
        "patch",
        "publish",
        "send",
        "emit",
        "dump",
        "dumps",
        "remove",
        "unlink",
        "rmtree",
        "makedirs",
        "mkdir",
        "system",
        "popen",
        "run",
        "call",
        "invoke",
    }
)

# 这些动词太常见，单独调用时不作为副作用证据（`x.run()` 满地都是）
_WEAK_VERBS = frozenset({"run", "call", "invoke", "delete", "update", "get", "load"})


@dataclass(frozen=True)
class FlowSymbol:
    """流程检测用到的符号（只留必要字段）。"""

    id: int
    qualname: str
    name: str
    kind: str
    path: str
    lineno: int
    module_qualname: str = ""


@dataclass(frozen=True)
class FlowEdge:
    """流程检测用到的边。"""

    src_id: int
    dst_id: int | None
    kind: str
    dst_name: str
    confidence: float = 1.0


@dataclass(frozen=True)
class FlowEntry:
    """流程的起点。"""

    kind: str
    target: str
    module_qualname: str | None = None
    symbol_qualname: str | None = None


@dataclass
class FlowStep:
    """流程里的一步。"""

    symbol_id: int | None
    qualname: str
    path: str
    lineno: int
    note: str = ""


@dataclass
class Flow:
    """一条流程。"""

    name: str
    entry_symbol_id: int | None = None
    description: str = ""
    steps: list[FlowStep] = field(default_factory=list)


def _is_side_effect_call(dst_name: str) -> bool:
    """这次调用有没有外部副作用。"""
    if not dst_name:
        return False
    head, _, tail = dst_name.partition(".")
    if head in SIDE_EFFECT_MODULES:
        return True
    if not tail:
        # 裸名字：`open(...)` `print(...)` `commit(...)`
        return head in SIDE_EFFECT_VERBS and head not in _WEAK_VERBS
    verb = tail.rsplit(".", 1)[-1]
    if verb in _WEAK_VERBS:
        return False
    return verb in SIDE_EFFECT_VERBS


def _symbol_side_effects(
    symbol_id: int,
    adjacency: dict[int, list[FlowEdge]],
) -> list[str]:
    """一个符号直接触发的副作用调用名。"""
    return [
        edge.dst_name
        for edge in adjacency.get(symbol_id, [])
        if edge.kind == "call" and _is_side_effect_call(edge.dst_name)
    ]


def detect_flows(
    symbols: list[FlowSymbol],
    edges: list[FlowEdge],
    entries: list[FlowEntry],
    *,
    max_depth: int = 12,
    max_flows: int = 24,
) -> list[Flow]:
    """从入口出发，找出到副作用符号的路径。

    参数
    ----
    symbols
        全部符号（用来把 id 换成 qualname/path）。
    edges
        调用边。`dst_id` 为 None 的边（目标是第三方）**不参与路径**，
        但它们的 `dst_name` 参与副作用判定——「调了 `requests.post`」
        是副作用证据，只是被调方不在本仓库。
    entries
        入口。

    返回
    ----
    流程列表。每条流程 = 入口 → … → 副作用符号的一条路径。
    """
    by_id = {s.id: s for s in symbols}
    by_qualname = {s.qualname: s for s in symbols}

    adjacency: dict[int, list[FlowEdge]] = {}
    for edge in edges:
        if edge.kind != "call":
            continue
        adjacency.setdefault(edge.src_id, []).append(edge)

    module_members = _module_level_symbols(symbols)

    flows: list[Flow] = []
    seen_effects: set[str] = set()

    for entry in entries:
        start = _entry_symbol(entry, by_qualname)
        if start is None:
            continue

        # 入口是**模块**时，真正的起点是它里面的模块级函数——
        # 模块本身只定义函数、不调用函数，直接从模块 BFS 只会走到空。
        seeds = [start]
        if start.kind == "module":
            seeds.extend(module_members.get(start.qualname, []))

        for seed in seeds:
            if len(flows) >= max_flows:
                break
            path0 = [start] if seed.id == start.id else [start, seed]
            # BFS：记录每个到达符号的最短路径
            queue: deque[tuple[FlowSymbol, list[FlowSymbol]]] = deque([(seed, path0)])
            visited: set[int] = {seed.id}

            while queue and len(flows) < max_flows:
                current, path = queue.popleft()
                if len(path) > max_depth:
                    continue

                effects = _symbol_side_effects(current.id, adjacency)
                if effects:
                    key = f"{entry.target}->{current.qualname}"
                    if key not in seen_effects:
                        seen_effects.add(key)
                        flows.append(
                            Flow(
                                name=f"{entry.target} → {_endpoint_label(current, start)}",
                                entry_symbol_id=start.id,
                                description=(
                                    f"从 {start.qualname} 到 {current.qualname}，"
                                    f"经由 {max(len(path) - 1, 0)} 步调用；"
                                    f"副作用：{', '.join(sorted(set(effects)))}"
                                ),
                                steps=[
                                    FlowStep(
                                        symbol_id=s.id,
                                        qualname=s.qualname,
                                        path=s.path,
                                        lineno=s.lineno,
                                        note="入口" if i == 0 else "",
                                    )
                                    for i, s in enumerate(path)
                                ],
                            )
                        )
                    continue  # 一个副作用符号只记一条流

                for edge in adjacency.get(current.id, []):
                    if edge.dst_id is None:
                        continue
                    target = by_id.get(edge.dst_id)
                    if target is None or target.id in visited:
                        continue
                    visited.add(target.id)
                    queue.append((target, [*path, target]))

    return flows


def _endpoint_label(current: FlowSymbol, start: FlowSymbol) -> str:
    """流程终点的名字。

    终点就是入口模块本身时（模块级代码自己干了件有副作用的事），
    说成「模块初始化」比说成「模块名 → 模块名」清楚。
    """
    if current.id == start.id:
        return "模块初始化"
    return current.qualname


def _module_level_symbols(symbols: list[FlowSymbol]) -> dict[str, list[FlowSymbol]]:
    """模块 → 它自己定义的模块级符号（函数 / 类 / 常量）。

    判据用 qualname 的层级：模块 `a.b` 的模块级符号是 `a.b.xxx`，
    `a.b.Cls.method` 就不是（那是方法，另有其主）。
    """
    out: dict[str, list[FlowSymbol]] = {}
    for symbol in symbols:
        module = symbol.module_qualname
        if not module:
            continue
        if symbol.kind not in {"function", "class", "constant"}:
            continue
        if symbol.qualname.count(".") != module.count(".") + 1:
            continue
        out.setdefault(module, []).append(symbol)
    return out


def _entry_symbol(entry: FlowEntry, by_qualname: dict[str, FlowSymbol]) -> FlowSymbol | None:
    """把入口落到具体符号上。

    - `console_script`（`demo = pkg.main:main`）→ 那个函数。
    - `framework_app`（`backend.main:app`）→ 那个模块（app 是模块级变量）。
    - `file`（`backend.main`）→ 那个模块。
    """
    if entry.symbol_qualname:
        found = by_qualname.get(entry.symbol_qualname)
        if found:
            return found
    if entry.module_qualname:
        found = by_qualname.get(entry.module_qualname)
        if found:
            return found
    target = entry.target.split(":", 1)[-1]
    if "." in target:
        return by_qualname.get(target)
    return None
