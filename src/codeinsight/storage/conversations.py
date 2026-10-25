"""会话投影的唯一落盘入口；所有查询显式绑定项目，失败不能伪装成保存成功。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codeinsight.agent.session import Focus

NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class ConversationRepository:
    """每请求使用自己的连接，不跨线程共享 SQLite 连接。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, project_id: int, conversation_id: str = "") -> dict[str, Any]:
        """创建或取得项目内会话，不覆盖已有标题与历史。"""
        cid = conversation_id or f"conv-{uuid.uuid4().hex}"
        self.conn.execute(
            "INSERT OR IGNORE INTO conversation(project_id,id) VALUES (?,?)", (project_id, cid)
        )
        self.conn.commit()
        return self.get(project_id, cid)

    def get(self, project_id: int, cid: str) -> dict[str, Any]:
        """返回指定项目的会话；不能按裸 ID 越过项目边界。"""
        row = self.conn.execute(
            "SELECT c.*, p.name project_name, "
            "(SELECT t.status FROM conversation_turn t WHERE t.project_id=c.project_id "
            "AND t.conversation_id=c.id ORDER BY t.created_at DESC,t.rowid DESC LIMIT 1) status, "
            "(SELECT t.task_id FROM conversation_turn t WHERE t.project_id=c.project_id "
            "AND t.conversation_id=c.id AND t.status='running' LIMIT 1) task_id "
            "FROM conversation c JOIN project p ON p.id=c.project_id WHERE c.project_id=? AND c.id=?",
            (project_id, cid),
        ).fetchone()
        if row is None:
            raise LookupError("会话不存在或不属于当前项目")
        result = dict(row)
        result["pinned"] = bool(result["pinned"])
        result["archived"] = bool(result["archived"])
        result.pop("focus_json", None)
        result["unread"] = result["updated_at"] > result["last_read_at"]
        return result

    def list(
        self, *, project_id: int | None, query: str, archived: bool, cursor: int, limit: int
    ) -> dict[str, Any]:
        """仅匹配可见消息正文；分页不返回工具原始结果或整段会话。"""
        terms = query.strip().split()
        where = ["c.archived=?"]
        args: list[Any] = [int(archived)]
        if project_id is not None:
            where.append("c.project_id=?")
            args.append(project_id)
        # 子串匹配保持中文与代码标识符完整；分页不把全部正文传给浏览器。
        for term in terms:
            where.append(
                "(instr(lower(c.title),lower(?))>0 OR EXISTS (SELECT 1 FROM conversation_turn t "
                "WHERE t.project_id=c.project_id AND t.conversation_id=c.id "
                "AND instr(lower(t.question || ' ' || COALESCE(json_extract(t.answer_json,'$.text'),'')),lower(?))>0))"
            )
            args.extend([term, term])
        rows = self.conn.execute(
            "SELECT c.project_id,c.id FROM conversation c WHERE "
            + " AND ".join(where)
            + " ORDER BY c.pinned DESC,c.updated_at DESC,c.id LIMIT ? OFFSET ?",
            (*args, limit + 1, cursor),
        ).fetchall()
        items = []
        for row in rows[:limit]:
            item = self.get(row["project_id"], row["id"])
            match = self.conn.execute(
                "SELECT request_id,question,answer_json FROM conversation_turn "
                "WHERE project_id=? AND conversation_id=? "
                + (
                    "AND instr(lower(question || ' ' || COALESCE(json_extract(answer_json,'$.text'),'')),lower(?))>0 "
                    if terms
                    else ""
                )
                + "ORDER BY created_at DESC,rowid DESC LIMIT 1",
                (row["project_id"], row["id"], *([terms[0]] if terms else [])),
            ).fetchone()
            if match:
                text = match["question"] + " " + json.loads(match["answer_json"]).get("text", "")
                position = text.lower().find(terms[0].lower()) if terms else 0
                item["snippet"] = text[max(0, position - 30) : max(0, position - 30) + 180]
                item["match_request_id"] = match["request_id"]
            items.append(item)
        return {"items": items, "next_cursor": cursor + limit if len(rows) > limit else None}

    def patch(self, project_id: int, cid: str, updates: dict[str, Any]) -> dict[str, Any]:
        """修改会话组织属性，已读只影响展示，不改变模型上下文。"""
        self.get(project_id, cid)
        for key in ("title", "pinned", "archived"):
            if key in updates:
                value = updates[key]
                if key == "title":
                    value = str(value).strip()[:120]
                    if not value:
                        raise ValueError("对话名称不能为空")
                self.conn.execute(
                    f"UPDATE conversation SET {key}=? WHERE project_id=? AND id=?",
                    (value, project_id, cid),
                )
        if updates.get("mark_read"):
            self.conn.execute(
                f"UPDATE conversation SET last_read_at={NOW} WHERE project_id=? AND id=?",
                (project_id, cid),
            )
        self.conn.commit()
        return self.get(project_id, cid)

    def turn(self, project_id: int, cid: str, request_id: str) -> dict[str, Any] | None:
        """精确读取幂等请求；不存在返回 None，不猜测其他会话。"""
        row = self.conn.execute(
            "SELECT rowid,* FROM conversation_turn WHERE project_id=? AND conversation_id=? AND request_id=?",
            (project_id, cid, request_id),
        ).fetchone()
        return self._turn(dict(row)) if row else None

    @staticmethod
    def _turn(row: dict[str, Any]) -> dict[str, Any]:
        row["answer"] = json.loads(row.pop("answer_json"))
        row["reading_context"] = json.loads(row.pop("reading_json") or "null")
        return row

    def turns(self, project_id: int, cid: str, cursor: int, limit: int) -> dict[str, Any]:
        """返回按行 ID 锚定的历史页，新增回合不移动旧页边界。"""
        self.get(project_id, cid)
        rows = self.conn.execute(
            "SELECT rowid,* FROM conversation_turn WHERE project_id=? AND conversation_id=? "
            "AND (?=0 OR rowid<?) ORDER BY rowid DESC LIMIT ?",
            (project_id, cid, cursor, cursor, limit + 1),
        ).fetchall()
        return {
            "items": [self._turn(dict(row)) for row in reversed(rows[:limit])],
            "next_cursor": rows[limit - 1]["rowid"] if len(rows) > limit else None,
        }

    def reserve(
        self, project_id: int, cid: str, request_id: str, question: str, reading: Any
    ) -> tuple[dict[str, Any], bool]:
        """原子占用会话：相同请求重用，不同并发请求触发唯一约束。"""
        self.create(project_id, cid)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            existing = self.turn(project_id, cid, request_id)
            if existing:
                if existing["question"] != question or existing["reading_context"] != reading:
                    raise ValueError("同一请求 ID 不能对应不同的问题或阅读目标")
                self.conn.commit()
                return existing, False
            self.conn.execute(
                "INSERT INTO conversation_turn(project_id,conversation_id,request_id,question,reading_json) "
                "VALUES (?,?,?,?,?)",
                (project_id, cid, request_id, question, encode(reading)),
            )
            self.conn.execute(
                f"UPDATE conversation SET title=CASE WHEN title='新对话' THEN ? ELSE title END, "
                f"updated_at={NOW},archived=0 WHERE project_id=? AND id=?",
                (question[:36], project_id, cid),
            )
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise
        return self.turn(project_id, cid, request_id), True  # type: ignore[return-value]

    def event(self, project_id: int, cid: str, rid: str, kind: str, data: dict[str, Any]) -> None:
        """提交可展示投影后方可发出事件；增量不覆盖结构化来源。"""
        turn = self.turn(project_id, cid, rid)
        if turn is None:
            raise LookupError("请求记录不存在")
        answer = turn["answer"]
        status = turn["status"]
        if kind == "meta":
            self.conn.execute(
                "UPDATE conversation_turn SET task_id=? WHERE project_id=? AND conversation_id=? AND request_id=?",
                (data["task_id"], project_id, cid, rid),
            )
        elif kind == "delta":
            answer["text"] = answer.get("text", "") + data["text"]
        elif kind == "answer":
            answer.update(data)
        elif kind == "error":
            answer["error"] = data
        elif kind == "tool":
            tools = answer.setdefault("tools", [])
            if tools and tools[-1]["name"] == data["name"] and tools[-1]["status"] == "running":
                tools[-1] = data
            else:
                tools.append(data)
        elif kind == "evidence":
            answer.setdefault("evidence", []).append(data)
        elif kind == "done":
            status = (
                "interrupted"
                if answer.get("error", {}).get("code") == "aborted"
                else "failed"
                if answer.get("error")
                else "abstained"
                if data.get("abstained")
                else "completed"
            )
        self.conn.execute(
            f"UPDATE conversation_turn SET answer_json=?,status=?,updated_at={NOW} "
            "WHERE project_id=? AND conversation_id=? AND request_id=?",
            (encode(answer), status, project_id, cid, rid),
        )
        self.conn.execute(
            f"UPDATE conversation SET updated_at={NOW} WHERE project_id=? AND id=?",
            (project_id, cid),
        )
        self.conn.commit()

    def recover(self) -> None:
        """仅在服务启动时执行；不能在每个请求里误停其他活动任务。"""
        error = encode(
            {
                "code": "aborted",
                "title": "服务重启，回答已中断",
                "hint": "已保存的内容保留，可以恢复问题后重试。",
            }
        )
        self.conn.execute(
            "UPDATE conversation_turn SET status='interrupted', "
            "answer_json=json_set(answer_json,'$.error',json(?)) WHERE status='running'",
            (error,),
        )
        self.conn.execute(
            "UPDATE agent_task SET status='interrupted',reason='服务重启',finished_at=datetime('now') "
            "WHERE status='running'"
        )
        self.conn.commit()

    def backfill(self) -> None:
        """只回填账本实际具有的字段；没有保存过的来源不补造。"""
        rows = self.conn.execute(
            "SELECT a.* FROM agent_task a WHERE a.conversation_id<>'' AND NOT EXISTS "
            "(SELECT 1 FROM conversation_turn t WHERE t.task_id=a.id) ORDER BY a.created_at,a.rowid"
        ).fetchall()
        for row in rows:
            pid, cid = row["project_id"], row["conversation_id"]
            self.create(pid, cid)
            event = self.conn.execute(
                "SELECT payload_json FROM agent_event WHERE task_id=? AND type='assistant.answer' "
                "ORDER BY id DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            answer = json.loads(event[0]) if event else {}
            status = row["status"] if row["status"] != "running" else "interrupted"
            self.conn.execute(
                "INSERT OR IGNORE INTO conversation_turn(project_id,conversation_id,request_id,task_id,"
                "question,answer_json,status,legacy,created_at) VALUES (?,?,?,?,?,?,?,1,?)",
                (
                    pid,
                    cid,
                    row["id"],
                    row["id"],
                    row["question"],
                    encode(answer),
                    status,
                    row["created_at"],
                ),
            )
            self.conn.execute(
                "UPDATE conversation SET title=CASE WHEN title='新对话' THEN ? ELSE title END WHERE project_id=? AND id=?",
                (row["question"][:36], pid, cid),
            )
        self.conn.commit()


class PersistentConversationStore:
    """运行时兼容存储；历史来自已完成的投影，焦点独立持久化。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def history(self, key: str) -> list[dict[str, str]]:
        """只取最后六个有效问答对；失败和中断不作为已完成历史。"""
        pid, cid = key.split(":", 1)
        rows = self.conn.execute(
            "SELECT question,answer_json FROM conversation_turn WHERE project_id=? AND conversation_id=? "
            "AND status IN ('completed','abstained') ORDER BY created_at DESC,rowid DESC LIMIT 6",
            (int(pid), cid),
        ).fetchall()
        return [
            message
            for row in reversed(rows)
            for message in (
                {"role": "user", "content": row[0]},
                {"role": "assistant", "content": json.loads(row[1]).get("text", "")},
            )
        ]

    def focus(self, key: str) -> Focus:
        """焦点独立于消息保存，避免把检索提示冒充正文。"""
        from codeinsight.agent.session import Focus

        pid, cid = key.split(":", 1)
        row = self.conn.execute(
            "SELECT focus_json FROM conversation WHERE project_id=? AND id=?", (int(pid), cid)
        ).fetchone()
        raw = json.loads(row[0]) if row else {}
        return Focus(
            **{
                **raw,
                "concept_ids": tuple(raw.get("concept_ids", [])),
                "paths": tuple(raw.get("paths", [])),
            }
        )

    def record_turn(
        self, key: str, question: str, answer: str, *, focus: Focus | None = None
    ) -> None:
        """正文由事件投影保存；此兼容入口仅提交本轮检索焦点。"""
        pid, cid = key.split(":", 1)
        if focus is not None:
            self.conn.execute(
                "UPDATE conversation SET focus_json=? WHERE project_id=? AND id=?",
                (encode(asdict(focus)), int(pid), cid),
            )
            self.conn.commit()
