"""多轮会话状态（源文档 §2.3-5「同一项目上下文连续追问」）。

会话里要记住两种东西：

1. **对话历史**——把上一轮的问答折成 messages 带上，模型才知道
   「这个函数」指的是哪个。
2. **焦点**（当前符号 / 当前模块 / 已看过的概念）——它不是对话内容，
   而是检索时该往哪儿靠的提示。把它塞进 messages 会污染上下文；
   Runtime 用它来给 `search_code` 补一个默认查询词。

v1 放在**进程内**：CodeInsight 是单用户本地工具，重启丢会话是可接受的。
真正需要持久化的是 `agent_task` / `agent_event` 账本（见 `ledger.py`）——
那是审计与复现用的，不是会话记忆。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

MAX_TURNS = 6
"""保留最近几轮问答。再早的历史对追问没有帮助，只会挤占预算。"""


@dataclass(frozen=True)
class Focus:
    """当前话题焦点。字段都可空——不知道就别假装知道。"""

    symbol: str | None = None
    module: str | None = None
    concept_ids: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()

    def merge(self, **updates: Any) -> Focus:
        merged = {
            "symbol": self.symbol,
            "module": self.module,
            "concept_ids": self.concept_ids,
            "paths": self.paths,
            **{key: value for key, value in updates.items() if value},
        }
        return Focus(**merged)

    def as_hint(self) -> str:
        """给检索用的提示串。为空时返回空串，不做无意义拼接。"""
        parts: list[str] = []
        if self.symbol:
            parts.append(self.symbol)
        if self.module:
            parts.append(self.module)
        return " ".join(parts)


@dataclass
class SessionState:
    conversation_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    focus: Focus = field(default_factory=Focus)
    turns: int = 0


class ConversationStore:
    """进程内会话表。线程安全——FastAPI 的请求可能落在不同线程。"""

    def __init__(self, *, max_turns: int = MAX_TURNS) -> None:
        self.max_turns = max_turns
        self._sessions: dict[str, SessionState] = {}
        self._lock = threading.Lock()

    def history(self, conversation_id: str) -> list[dict[str, Any]]:
        with self._lock:
            session = self._sessions.get(conversation_id)
            return list(session.messages) if session else []

    def focus(self, conversation_id: str) -> Focus:
        with self._lock:
            session = self._sessions.get(conversation_id)
            return session.focus if session else Focus()

    def record_turn(
        self,
        conversation_id: str,
        question: str,
        answer: str,
        *,
        focus: Focus | None = None,
    ) -> None:
        with self._lock:
            session = self._sessions.setdefault(conversation_id, SessionState(conversation_id))
            session.messages.append({"role": "user", "content": question})
            session.messages.append({"role": "assistant", "content": answer})
            session.turns += 1
            if focus is not None:
                session.focus = focus
            # 只保留最近 max_turns 轮（两两成对）。
            overflow = max(0, len(session.messages) - self.max_turns * 2)
            if overflow:
                del session.messages[:overflow]

    def drop(self, conversation_id: str) -> None:
        with self._lock:
            self._sessions.pop(conversation_id, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)
