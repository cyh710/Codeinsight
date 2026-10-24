"""「在哪里实现」的定位评测（M2 验收 / M5 的一个臂）。

题目**从索引自动生成**，不用手工标：
从项目里挑一批有代表性的符号，ground truth 就是那个符号的 `file:line`
——索引本身就是事实的来源，不需要人再标一遍。

两种题型（难度差很多，分开报）：

- `name`：**知道名字**（`ILinkBot 在哪实现`）→ 考察精确匹配与定位。
  这是最常见的真实场景——用户已经知道符号叫什么，只是不知道在哪个文件。
- `docstring`：**只知道描述**（把 docstring 当查询）→ 考察语义/词面匹配。
  这题靠「符号名精确匹配」是答不上的——答案在 docstring 里，名字没出现。

题型 `docstring` 才是真正区分「关键词检索」和「结构化检索」的地方：
它逼着系统去匹配**内容**，而不是去匹配**名字**。
"""

from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass, field

DEFAULT_SEED = 7
"""固定随机种子——题目可复现，评测数字才有意义。"""

MIN_NAME_LENGTH = 6
"""名字太短（`run`）在代码库里满地都是，题目就不成立了。"""

MIN_DOCSTRING_LENGTH = 12


@dataclass(frozen=True)
class LocatorTask:
    """一道「在哪里实现」的题。"""

    task_id: str
    query: str
    """检索用的查询文本。"""

    kind: str
    """`name` 或 `docstring`。"""

    target_path: str
    target_lineno: int
    target_qualname: str
    target_symbol_id: int


@dataclass
class LocatorResult:
    """一道题的结果。"""

    task: LocatorTask
    hits: list[tuple[str, int]] = field(default_factory=list)
    """检索返回的 (path, lineno)，按排名。"""

    rank: int | None = None
    """ground truth 出现在第几名（1-based）；没出现是 None。"""

    @property
    def hit(self) -> bool:
        return self.rank is not None

    @property
    def reciprocal_rank(self) -> float:
        return 1.0 / self.rank if self.rank else 0.0


def generate_tasks(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    n: int = 10,
    seed: int = DEFAULT_SEED,
    kind: str = "name",
) -> list[LocatorTask]:
    """从索引里挑出 `n` 道题。

    挑选标准（让题目有意义）：
    - 名字在整个项目里**唯一**（重名的符号没法当 ground truth）；
    - 名字够长（短名字满地都是）；
    - 属于 `source` 角色（测试代码不是「实现在哪」的好答案）；
    - 有 docstring（`docstring` 题型需要）。
    """
    rows = conn.execute(
        """
        SELECT s.id, s.qualname, s.name, s.lineno, f.path, COALESCE(s.docstring, '')
        FROM symbol s JOIN file f ON f.id = s.file_id
        WHERE s.project_id = ? AND f.role = 'source' AND s.kind IN ('function', 'method', 'class')
        ORDER BY s.id
        """,
        (project_id,),
    ).fetchall()

    name_counts = {row[2]: 0 for row in rows}
    for row in rows:
        name_counts[row[2]] += 1

    candidates = [
        row
        for row in rows
        if name_counts[row[2]] == 1
        and len(row[2]) >= MIN_NAME_LENGTH
        and not row[2].startswith("_")
        and (kind != "docstring" or len(row[5]) >= MIN_DOCSTRING_LENGTH)
    ]
    if not candidates:
        return []

    rng = random.Random(seed)
    picked = rng.sample(candidates, min(n, len(candidates)))

    tasks: list[LocatorTask] = []
    for row in picked:
        symbol_id, qualname, name, lineno, path, docstring = row
        if kind == "docstring":
            query = docstring.strip().splitlines()[0][:120]
        else:
            query = f"{name} 在哪实现"
        tasks.append(
            LocatorTask(
                task_id=f"{kind}:{qualname}",
                query=query,
                kind=kind,
                target_path=path,
                target_lineno=int(lineno),
                target_qualname=qualname,
                target_symbol_id=int(symbol_id),
            )
        )
    return tasks


def run_tasks(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    tasks: list[LocatorTask],
    retriever,
    k: int = 8,
) -> list[LocatorResult]:
    """跑题并记录排名。"""
    results: list[LocatorResult] = []
    for task in tasks:
        evidence = retriever.retrieve(task.query, k=k, project_id=project_id)
        hits = [(item.path, item.lineno) for item in evidence]
        rank = None
        for index, (path, lineno) in enumerate(hits, start=1):
            if path == task.target_path and lineno == task.target_lineno:
                rank = index
                break
        results.append(LocatorResult(task=task, hits=hits, rank=rank))
    return results


def summarize(results: list[LocatorResult]) -> dict:
    """汇总成报告用的数字。"""
    total = len(results)
    hits = sum(1 for r in results if r.hit)
    mrr = sum(r.reciprocal_rank for r in results) / total if total else 0.0
    top1 = sum(1 for r in results if r.rank == 1)
    return {
        "total": total,
        "hits": hits,
        "hit_rate": hits / total if total else 0.0,
        "mrr": mrr,
        "top1_rate": top1 / total if total else 0.0,
    }


def format_report(results: list[LocatorResult]) -> str:
    """人看的报告。"""
    lines: list[str] = []
    for result in results:
        mark = "✓" if result.hit else "✗"
        rank = f"第 {result.rank} 名" if result.hit else "未命中"
        lines.append(f"  {mark} [{result.task.kind}] {result.task.query[:60]}")
        lines.append(f"      目标 {result.task.target_path}:{result.task.target_lineno}  {rank}")
    summary = summarize(results)
    lines.append("")
    lines.append(
        f"  命中 {summary['hits']}/{summary['total']}"
        f"（{summary['hit_rate']:.0%}）  MRR {summary['mrr']:.3f}"
        f"  Top-1 {summary['top1_rate']:.0%}"
    )
    return "\n".join(lines)
