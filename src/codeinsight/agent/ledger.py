"""事件账本（`agent_task` / `agent_event`）。

源文档 §3.1 第四层「Agent 任务状态」+ ADR 0010：
**工具结果先落事件，再由装配折回 messages**——账本里看到的与模型看到的
来自同一份记录。这样「模型为什么这么答」才能在事后复现，
而不是靠翻日志猜。

账本写的是**持久化层**（单个工具结果上限 80 KB，见 `context.py`），
比喂给模型的 12 KB 宽——模型看不全的不该从审计里消失。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

PERSIST_RESULT_BYTES = 80_000


def new_task_id() -> str:
    return f"task-{uuid.uuid4().hex[:16]}"


class EventLedger:
    """一次问答对应一个 `agent_task`，过程中的每一步是一条 `agent_event`。"""

    def __init__(self, conn: sqlite3.Connection, *, project_id: int, conversation_id: str) -> None:
        self._conn = conn
        self.project_id = project_id
        self.conversation_id = conversation_id

    def start(self, task_id: str, question: str) -> None:
        self._conn.execute(
            "INSERT INTO agent_task (id, project_id, conversation_id, question, status)"
            " VALUES (?, ?, ?, ?, 'running')",
            (task_id, self.project_id, self.conversation_id, question),
        )
        self.record(task_id, "user.message", {"content": question})
        self._conn.commit()

    def record(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO agent_event (task_id, type, payload_json) VALUES (?, ?, ?)",
            (task_id, event_type, json.dumps(payload, ensure_ascii=False, default=str)),
        )

    def finish(self, task_id: str, *, status: str, reason: str = "") -> None:
        self._conn.execute(
            "UPDATE agent_task SET status = ?, reason = ?, finished_at = datetime('now')"
            " WHERE id = ?",
            (status, reason or None, task_id),
        )
        self._conn.commit()

    def events(self, task_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT type, payload_json FROM agent_event WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()
        return [{"type": row[0], "payload": json.loads(row[1])} for row in rows]
