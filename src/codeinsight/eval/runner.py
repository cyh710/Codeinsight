"""跑对照臂：同一批题，逐个开关跑一遍，结果落 `eval_result`。

**不可用的臂要如实标出来**，不能静默退化成别的臂：
没有向量时 `hybrid` 会退化成 `bm25`，如果照常报一个数，
读报告的人会以为「语义检索没用」——那是对照实验里最坏的一种错误。
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field

from codeinsight.cognitive.retrieval.retriever import RetrievalConfig, Retriever
from codeinsight.eval.arms import Arm
from codeinsight.eval.bench import BenchTask, task_id_of
from codeinsight.eval.metrics import summarize_ranks


@dataclass
class TaskOutcome:
    task: BenchTask
    rank: int | None
    latency_ms: int


@dataclass
class ArmRun:
    arm: Arm
    outcomes: list[TaskOutcome] = field(default_factory=list)
    available: bool = True
    reason: str = ""

    def ranks(self, *, kind: str | None = None) -> list[int | None]:
        return [
            outcome.rank
            for outcome in self.outcomes
            if kind is None or outcome.task.kind == kind
        ]

    def summarize(self, *, k: int, kinds: tuple[str, ...], seed: int) -> dict:
        return {
            "overall": summarize_ranks(self.ranks(), k=k, seed=seed),
            "by_kind": {
                kind: summarize_ranks(self.ranks(kind=kind), k=k, seed=seed)
                for kind in kinds
            },
        }


def new_run_id(seed: int) -> str:
    return f"run-{uuid.uuid4().hex[:12]}-s{seed}"


def dense_available(conn: sqlite3.Connection, *, project_id: int) -> tuple[bool, str]:
    """稠密通道能不能用：既要有向量，也要有可用的 embedder。"""
    count = conn.execute(
        "SELECT COUNT(*) FROM embedding e JOIN chunk c ON c.id = e.chunk_id"
        " WHERE c.project_id = ?",
        (project_id,),
    ).fetchone()[0]
    if count == 0:
        return False, "没有向量（先跑 ci index --embed）"
    return True, ""


def run_arm(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    tasks: list[BenchTask],
    arm: Arm,
    k: int,
    embedder=None,
    db_path: str = ":memory:",
    neighbor_depth: int = 1,
    rrf_k: int = 60,
    dense_ok: bool = True,
) -> ArmRun:
    run = ArmRun(arm=arm)
    if not arm.lanes:
        # 下限臂：不检索，所有题都未命中。这不是「跳过」。
        run.outcomes = [TaskOutcome(task, None, 0) for task in tasks]
        return run
    if arm.needs_dense and not dense_ok:
        run.available = False
        run.reason = "稠密通道不可用（没有向量）"
        return run

    retriever = Retriever(
        conn,
        embedder=embedder,
        db_path=db_path,
        config=RetrievalConfig(
            lanes=arm.lanes,
            top_k=k,
            rrf_k=rrf_k,
            neighbor_depth=neighbor_depth,
        ),
    )
    for task in tasks:
        started = time.perf_counter()
        evidence = retriever.retrieve(task.question, k=k, project_id=project_id)
        elapsed = int((time.perf_counter() - started) * 1000)
        hits = [(item.path, item.lineno, item.qualname) for item in evidence]
        run.outcomes.append(TaskOutcome(task, _rank_of(task, hits), elapsed))
    return run


def _rank_of(task: BenchTask, hits: list[tuple[str, int, str | None]]) -> int | None:
    """命中出现在第几名（1-based）。判定口径随题型变：

    - 定位题：必须命中**那一个**符号（path + lineno）；
    - 概念题：该概念的**任意一处**实例都算对，且按 qualname 比
      （实例行号不一定等于块起始行）。
    """
    for index, (path, lineno, qualname) in enumerate(hits, start=1):
        if task.target_qualnames:
            hit = qualname in task.target_qualnames
        elif task.match_by_qualname:
            hit = qualname == task.target_qualname
        else:
            hit = path == task.target_path and lineno == task.target_lineno
        if hit:
            return index
    return None


def persist_results(
    conn: sqlite3.Connection, *, run_id: str, runs: list[ArmRun]
) -> int:
    """把每次命中写进 `eval_result`（`rank` 为空 = 未命中）。"""
    written = 0
    for run in runs:
        if not run.available:
            continue
        for outcome in run.outcomes:
            task = outcome.task
            conn.execute(
                """
                INSERT INTO eval_result (run_id, task_id, arm, rank, hit, latency_ms, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    task_id_of(task.kind, task.question, task.answer_json()),
                    run.arm.name,
                    outcome.rank,
                    1 if outcome.rank else 0,
                    outcome.latency_ms,
                    json.dumps(
                        {
                            "kind": task.kind,
                            "query": task.question,
                            "target": task.answer_json(),
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            written += 1
    conn.commit()
    return written
