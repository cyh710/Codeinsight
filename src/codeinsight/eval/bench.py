"""评测题库：从索引**自动生成**，并落 `eval_task`。

为什么不手工标：手工标注的题集只在标的人手里可复现，换个人就说不清
ground truth 是怎么来的。这里的每一道题的答案都是索引里的一条真实记录
（某个符号的 `file:line`、某条调用边），谁都能重跑一遍核对。

题库落库（`eval_task`）是为了**同一批题能反复跑不同臂**：
臂与臂之间题目必须完全相同，否则比的不是通道，是运气。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass

from codeinsight.eval.locator import DEFAULT_SEED, LocatorTask, generate_tasks


@dataclass(frozen=True)
class BenchTask:
    """一道题。`kind` 与 `eval_task.template` 同名。"""

    task_id: str
    kind: str
    question: str
    target_path: str
    target_lineno: int
    target_qualname: str
    match_by_qualname: bool = False
    """概念题的 ground truth 是**实例所在符号**，行号可能和块边界不同，
    所以按 qualname 判定命中；定位题按 path+lineno 判定。"""

    target_qualnames: tuple[str, ...] = ()
    """概念题接受**该概念任意一处实例**：问的是「项目里哪里用了 X」，
    答到同概念的另一处实例不算错。只有定位题才认唯一答案。"""

    def answer_json(self) -> dict:
        return {
            "path": self.target_path,
            "lineno": self.target_lineno,
            "qualname": self.target_qualname,
        }


def task_id_of(kind: str, question: str, answer: dict) -> str:
    raw = f"{kind}|{question}|{json.dumps(answer, ensure_ascii=False, sort_keys=True)}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _from_locator(task: LocatorTask) -> BenchTask:
    return BenchTask(
        task_id=task.task_id,
        kind=task.kind,
        question=task.query,
        target_path=task.target_path,
        target_lineno=task.target_lineno,
        target_qualname=task.target_qualname,
    )


def build_tasks(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    n_per_kind: int = 25,
    seed: int = DEFAULT_SEED,
    kinds: tuple[str, ...] = ("name", "docstring", "concept"),
) -> list[BenchTask]:
    """生成题库。未知题型直接报错，不静默跳过。

    `concept` 题型的意义：**每种通道要在它能起作用的题上被评测**。
    概念通道设计给的是「项目用了哪些概念、在哪」，拿「知道名字找实现」
    去测它，测出来的 0 说明不了任何问题——那只是题型不对。
    """
    tasks: list[BenchTask] = []
    for kind in kinds:
        if kind in {"name", "docstring"}:
            tasks.extend(
                _from_locator(task)
                for task in generate_tasks(
                    conn, project_id=project_id, n=n_per_kind, seed=seed, kind=kind
                )
            )
        elif kind == "concept":
            tasks.extend(_concept_tasks(conn, project_id=project_id, n=n_per_kind, seed=seed))
        else:
            raise ValueError(f"未知题型：{kind}（可用：name, docstring, concept）")
    return tasks


def _concept_tasks(
    conn: sqlite3.Connection, *, project_id: int, n: int, seed: int
) -> list[BenchTask]:
    """概念题：给出概念名，ground truth 是它在**源码**里的实例集合。

    判定口径是「命中该概念**任意一处**实例」：题目问的是
    「项目里哪里用了 X」，答到另一处实例同样是正确答案。
    这和定位题不同——定位题问的是具体某个符号，必须唯一。
    """
    import random

    rows = conn.execute(
        """
        SELECT ci.concept_id, c.name, ci.path, ci.lineno, ci.qualname, f.role
        FROM concept_instance ci
        JOIN concept c ON c.id = ci.concept_id
        JOIN file f ON f.path = ci.path AND f.project_id = ci.project_id
        WHERE ci.project_id = ? AND ci.qualname IS NOT NULL AND ci.qualname != ''
        ORDER BY ci.concept_id, ci.path, ci.lineno
        """,
        (project_id,),
    ).fetchall()
    # 接受**任意一处**实例，所以 qualname 集合取全部（含测试文件）——
    # 只取源码会让「检索到测试里的用法」被判成没命中。
    qualnames_by_concept: dict[str, set[str]] = {}
    source_rows: dict[str, list] = {}
    for row in rows:
        qualnames_by_concept.setdefault(row[0], set()).add(row[4])
        if row[5] == "source":
            source_rows.setdefault(row[0], []).append(row)
    concepts = sorted(source_rows)
    if not concepts:
        return []

    rng = random.Random(seed + 1)
    picked = rng.sample(concepts, min(n, len(concepts)))
    tasks: list[BenchTask] = []
    for concept_id in picked:
        candidates = source_rows[concept_id]
        concept_name = candidates[0][1]
        _cid, _name, path, lineno, qualname, _role = candidates[rng.randrange(len(candidates))]
        question = f"项目里哪里用到了「{concept_name}」？"
        tasks.append(
            BenchTask(
                task_id=f"concept:{concept_id}",
                kind="concept",
                question=question,
                target_path=path,
                target_lineno=int(lineno),
                target_qualname=qualname,
                match_by_qualname=True,
                target_qualnames=tuple(sorted(qualnames_by_concept[concept_id])),
            )
        )
    return tasks


def persist_tasks(conn: sqlite3.Connection, *, project_id: int, tasks: list[BenchTask]) -> int:
    """写入 `eval_task`（幂等）。返回写入条数。"""
    for task in tasks:
        conn.execute(
            """
            INSERT INTO eval_task (id, project_id, template, question, answer_json, split)
            VALUES (?, ?, ?, ?, ?, 'test')
            ON CONFLICT(id) DO UPDATE SET
                template = excluded.template,
                question = excluded.question,
                answer_json = excluded.answer_json,
                split = excluded.split
            """,
            (
                task_id_of(task.kind, task.question, task.answer_json()),
                project_id,
                task.kind,
                task.question,
                json.dumps(task.answer_json(), ensure_ascii=False),
            ),
        )
    conn.commit()
    return len(tasks)
