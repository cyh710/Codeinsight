"""显式恢复被探索收尾覆盖的项目回答；不扫描或自动修改其他历史。"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from codeinsight.agent.answer import Grounding, split_answer
from codeinsight.agent.answer_body import is_answer_attachment, merge_answer_body
from codeinsight.agent.evidence_review import assess
from codeinsight.agent.exploration import version
from codeinsight.agent.runtime import _absorb_grounding
from codeinsight.models import Answer


@dataclass(frozen=True)
class AnswerRestoration:
    """预览绑定原始行与索引版本，应用时再次比较，避免覆盖并发改动。"""

    project_id: int
    conversation_id: str
    request_id: str
    task_id: str
    original_status: str
    original_json: str
    source_version: dict[str, Any]
    restored: dict[str, Any]

    def summary(self) -> dict[str, Any]:
        """只报告变更规模与引用核查，不把用户正文打印到日志。"""
        original = json.loads(self.original_json)
        return {
            "project_id": self.project_id,
            "request_id": self.request_id,
            "before_chars": len(original.get("text", "")),
            "after_chars": len(self.restored["text"]),
            "citations": len(self.restored["citations"]),
            "unverified_citations": len(self.restored["evidence_review"]["unverified_citations"]),
            "changed": original.get("raw_text") != self.restored["raw_text"],
        }


def prepare_answer_restoration(
    conn: sqlite3.Connection, project_id: int, conversation_id: str, request_id: str
) -> AnswerRestoration:
    """只从同回合公开文本及取证恢复；任务、版本或记录不完整时拒绝猜测。"""
    row = conn.execute(
        "SELECT task_id,question,status,answer_json FROM conversation_turn "
        "WHERE project_id=? AND conversation_id=? AND request_id=?",
        (project_id, conversation_id, request_id),
    ).fetchone()
    if row is None or row[2] not in {"completed", "abstained"}:
        raise ValueError("回合不存在或尚未正常结束，不能恢复")
    task_id, question, original_status, original_json = row
    task = conn.execute(
        "SELECT project_id,conversation_id,question,status FROM agent_task WHERE id=?", (task_id,)
    ).fetchone()
    if task is None or tuple(task)[:3] != (project_id, conversation_id, question):
        raise ValueError("任务不属于这个项目、会话与问题")
    if task[3] not in {"completed", "abstained"}:
        raise ValueError("任务尚未正常结束，不能恢复")
    original = json.loads(original_json)
    source = (original.get("evidence_review") or {}).get("source_version")
    if not source or source != version(conn, project_id):
        raise ValueError("索引版本已变化或缺失，不能自动恢复")
    if original.get("incomplete") or original.get("error"):
        raise ValueError("回合未完成或出错，不能作为完整答案恢复")

    parts: list[str] = []
    grounding = Grounding()
    has_final = False
    for kind, raw in conn.execute(
        "SELECT type,payload_json FROM agent_event WHERE task_id=? ORDER BY id", (task_id,)
    ):
        data = json.loads(raw)
        if kind == "assistant.tool_calls" and is_answer_attachment(
            [call.get("name", "") for call in data.get("tool_calls", [])]
        ):
            parts.append(data.get("content", ""))
        elif kind == "tool.finished":
            _absorb_grounding(grounding, data.get("data") or {})
        elif kind == "assistant.answer":
            has_final = True
    if not parts or not has_final or "raw_text" not in original:
        raise ValueError("缺少附加阶段正文或最终原文，不能恢复")
    raw_text = merge_answer_body(parts, original["raw_text"])
    split = split_answer(raw_text, grounding, preserve_invalid=True)
    answer = Answer(
        text=split.text,
        facts=split.facts,
        inferences=split.inferences,
        citations=split.citations,
        dropped_citations=list(split.dropped_citations),
        evidence_review=original.get("evidence_review"),
    )
    review = assess(answer, knowledge_only=False, source_version=source)
    restored = {
        **original,
        "raw_text": raw_text,
        "text": split.text,
        "facts": split.facts,
        "inferences": split.inferences,
        "citations": [asdict(citation) for citation in split.citations],
        "evidence_review": review,
        "abstained": not bool(split.citations),
        "reason": review["message"] if not split.citations else "",
    }
    return AnswerRestoration(
        project_id,
        conversation_id,
        request_id,
        task_id,
        original_status,
        original_json,
        source,
        restored,
    )


def apply_answer_restoration(
    conn: sqlite3.Connection, plan: AnswerRestoration, backup_dir: Path
) -> Path | None:
    """先备份，再原值比较更新这一回合；原始事件不改，重复应用无副作用。"""
    if not plan.summary()["changed"]:
        return None
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT task_id,status,answer_json FROM conversation_turn "
            "WHERE project_id=? AND conversation_id=? AND request_id=?",
            (plan.project_id, plan.conversation_id, plan.request_id),
        ).fetchone()
        if not current or tuple(current) != (
            plan.task_id,
            plan.original_status,
            plan.original_json,
        ):
            raise ValueError("回合已被其他操作更新，请重新预览")
        if version(conn, plan.project_id) != plan.source_version:
            raise ValueError("索引版本已变化，请重新核对")
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"answer-{plan.request_id}-{secrets.token_hex(4)}.json"
        with backup.open("x", encoding="utf-8") as stream:
            json.dump(
                {
                    "project_id": plan.project_id,
                    "conversation_id": plan.conversation_id,
                    "request_id": plan.request_id,
                    "task_id": plan.task_id,
                    "status": plan.original_status,
                    "answer_json": plan.original_json,
                },
                stream,
                ensure_ascii=False,
                indent=2,
            )
        conn.execute(
            "UPDATE conversation_turn SET answer_json=?,status=? "
            "WHERE project_id=? AND conversation_id=? AND request_id=? AND answer_json=?",
            (
                json.dumps(plan.restored, ensure_ascii=False),
                "abstained" if plan.restored["abstained"] else "completed",
                plan.project_id,
                plan.conversation_id,
                plan.request_id,
                plan.original_json,
            ),
        )
        conn.execute(
            "INSERT INTO agent_event(task_id,type,payload_json) VALUES(?,?,?)",
            (
                plan.task_id,
                "assistant.answer_restored",
                json.dumps(
                    {
                        **plan.summary(),
                        "backup": str(backup.resolve()),
                        "original_sha256": hashlib.sha256(plan.original_json.encode()).hexdigest(),
                    },
                    ensure_ascii=False,
                ),
            ),
        )
    return backup
