"""续讲只继承问题来路，代码证据必须在当前回合重新读取。"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from codeinsight.agent.exploration import code_target, version

_REPHRASE = re.compile(
    r"^(?:(?:我|还是|完全|有点|这个|这段|刚才|再|能不能|可以|请|你)[，,\s]*)*"
    r"(?:听不懂|看不懂|没听懂|没看懂|没懂|不明白|不太懂|不理解|换[一种个]+说法|"
    r"说[得的]简单|简单[一点些]+|讲[得的]简单|讲[得的]通俗|解释[得的]简单|"
    r"举[一个]+例子|换(?:个|一个)例子|用例子|画(?:个|一张)?(?:图|示意图)|"
    r"用图(?:解释|说明|讲)|用表(?:解释|说明|讲)|解释一遍|讲一遍|说一遍|具体一点|详细一点|展开讲|"
    r"explain (?:again|more simply)|simplify|i (?:don't|do not) understand)",
    re.I,
)


def prepare_followup(
    conn: sqlite3.Connection | None,
    project_id: int,
    cid: str,
    question: str,
    prior: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """只识别明确的短续讲；无前文不猜对象，跨版本不自动重绑定旧行号。"""
    if len(question) > 160 or not _REPHRASE.search(question.strip()):
        return None
    previous = None
    recent: list[dict[str, Any]] = []
    if conn is not None and cid:
        rows = conn.execute(
            "SELECT request_id,question,answer_json FROM conversation_turn "
            "WHERE project_id=? AND conversation_id=? AND status IN ('completed','abstained') "
            "ORDER BY created_at DESC,rowid DESC LIMIT 6",
            (project_id, cid),
        ).fetchall()
        for row in rows:
            answer = json.loads(row[2])
            # 旧逻辑已覆盖的占位卡没有可重讲正文；回到它前面的真实解释，不补造丢失原文。
            if (
                answer.get("abstained")
                and "raw_text" not in answer
                and answer.get("text") == "在本项目的索引里没有找到与这个问题相关的代码位置。"
            ):
                continue
            if answer.get("incomplete"):
                continue
            recent.append({"request_id": row[0], "question": row[1], "answer": answer})
        previous = recent[0] if recent else None
    elif len(prior) >= 2:
        for index in range(len(prior) - 2, -1, -2):
            if prior[index].get("role") == "user" and prior[index + 1].get("role") == "assistant":
                recent.append(
                    {
                        "request_id": None,
                        "question": prior[index].get("content", ""),
                        "answer": {"text": prior[index + 1].get("content", "")},
                    }
                )
        previous = recent[0] if recent else None
    if previous is None:
        return {
            "kind": "clarification",
            "request_id": None,
            "code": [],
            "knowledge": None,
            "note": "本次是要求重新解释，但本会话没有可关联的上一轮；请简短澄清对象，不猜测项目内容。",
        }
    answer = previous["answer"]
    locations = answer.get("citations") or answer.get("evidence") or []
    requests = [question[:160]]
    topic_question = ""
    for turn in recent:
        text = str(turn["question"])
        if _REPHRASE.search(text.strip()):
            requests.append(text[:160])
        else:
            topic_question = text[:400]
            break
    review = answer.get("evidence_review") or {}
    stored = review.get("source_version") or answer.get("exploration") or {}
    current = version(conn, project_id) if conn is not None else {}
    commit = stored.get("head_commit", answer.get("source_head_commit"))
    same = (
        bool(current)
        and commit == current.get("head_commit")
        and (
            stored.get("index_epoch") == current.get("index_epoch")
            or (stored.get("index_epoch") is None and bool(commit))
        )
    )
    result = {
        "kind": "rephrase",
        "request_id": previous["request_id"],
        "code": [],
        "knowledge": None,
        "project_based": bool(locations),
        "teaching_context": {
            "topic_question": topic_question,
            "attempt": len(requests),
            "requests": requests[:3],
            "previous_explanation": str(answer.get("text", ""))[:1200],
        },
        "note": "用户希望重新理解上一条解释。对照明确反馈与原解释，换一种表示讲清当前障碍。"
        "默认沿用同一个例子，可填入具体值、比较前后状态或只拆一个步骤；用户要求换例子时遵从。"
        "不要只是重排原文，不要推断用户能力；未明确障碍时不要宣称已经知道。"
        "历史输出仅为对话来路；项目事实需本回合取证，明确阅读目标优先。"
        f"\n上一轮问题（数据）：{str(previous['question'])[:400]}",
    }
    workspace_locations = any(c.get("source_kind") == "workspace" for c in locations)
    if locations and not same and not workspace_locations:
        result["note"] += (
            "\n上轮代码版本已变化或版本信息不足，请重新定位，不能沿用旧行号作为当前证据。"
        )
    if same or workspace_locations:
        for citation in locations:
            if not same and citation.get("source_kind") != "workspace":
                continue
            target = code_target(
                conn,
                project_id,
                {
                    **citation,
                    "lineno": max(1, citation["lineno"] - 8),
                    "end_lineno": citation["lineno"] + 28,
                },
            )
            if target and not any(t["path"] == target["path"] for t in result["code"]):
                result["code"].append(target)
            if len(result["code"]) == 2:
                break
    if workspace_locations:
        result["note"] += (
            "\n本次续讲重读上轮保存的工作区源码快照；不声称它等于当前磁盘版本，需要比较最新实现时重新搜索当前工作区。"
        )
    # 已保存的知识目标只是定位线索，prepare_goal 仍核对当前文章及版本。
    if not answer.get("incomplete"):
        source = next(iter(answer.get("knowledge_sources") or []), None)
        if source and isinstance(source.get("target"), dict):
            result["knowledge"] = {"kind": "knowledge", **source["target"]}
    return result
