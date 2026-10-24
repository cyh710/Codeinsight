"""把一次问答要用的东西装配起来：连接、检索器、工具集、运行时。

CLI 与 API 都从这里拿运行时——**装配逻辑只写一份**。
两边各自拼装是这类项目最常见的漂移来源：CLI 能跑、接口缺一个通道，
而没人发现，因为没人把两边输出的证据对起来看过。

这里不做并发控制：一个 `AgentSession` 对应一个请求（一个 SQLite 连接）。
FastAPI 侧每个请求开一次、用完 `close()`——SQLite 连接不跨线程共享。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from codeinsight.agent.context import ContextBudget
from codeinsight.agent.runtime import AgentRuntime, RuntimeConfig
from codeinsight.agent.session import ConversationStore
from codeinsight.agent.tools import ToolServices, build_tools
from codeinsight.cognitive.concepts.assets import knowledge_directory
from codeinsight.cognitive.concepts.integration import LearningBridge
from codeinsight.cognitive.concepts.learning_models import KnowledgeError
from codeinsight.cognitive.concepts.library import LearningLibrary
from codeinsight.cognitive.concepts.service import KnowledgeService
from codeinsight.cognitive.embedding.siliconflow import SiliconFlowEmbedder
from codeinsight.cognitive.retrieval.retriever import (
    ALL_LANES,
    LANE_BM25,
    LANE_CONCEPT,
    LANE_DENSE,
    LANE_SYMBOL,
    RetrievalConfig,
    Retriever,
)
from codeinsight.config import Settings
from codeinsight.config import settings as default_settings
from codeinsight.llm.openai_compat import LLMNotConfigured, OpenAICompatProvider
from codeinsight.storage.sqlite import ensure_schema, open_sqlite

DEFAULT_AGENT_LANES = frozenset({LANE_BM25, LANE_SYMBOL, LANE_CONCEPT, LANE_DENSE})

_DEFAULT_STORE = ConversationStore()
"""HTTP 每个请求都会调用 `open_agent`，但**会话要跨请求活着**——
连续追问（源文档 §2.3-5）的前提是同一个 `conversation_id` 能找到历史。
所以默认存储是进程级的；CLI 想用独立会话就显式传 `store=`。"""


class ProjectNotFound(LookupError):
    """项目名不存在。"""


@dataclass
class AgentSession:
    """一个请求的生命周期对象。用完必须 `close()`。"""

    conn: sqlite3.Connection
    runtime: AgentRuntime
    project_id: int
    project_name: str
    head_commit: str | None
    repo_root: str

    def close(self) -> None:
        self.conn.close()


def build_provider(settings: Settings | None = None) -> OpenAICompatProvider:
    conf = settings or default_settings
    return OpenAICompatProvider(
        base_url=conf.llm_base_url,
        api_key=conf.llm_api_key,
        model=conf.llm_model,
        timeout_s=conf.llm_timeout_s,
    )


def open_agent(
    db_path: str | Path,
    project: str | int,
    *,
    store: ConversationStore | None = None,
    provider=None,
    embedder=None,
    concepts_dir: str | Path | None = Path("knowledge/concepts"),
    lanes: frozenset[str] | None = None,
    budget: ContextBudget | None = None,
    config: RuntimeConfig | None = None,
    settings: Settings | None = None,
) -> AgentSession:
    """打开某个项目的 Agent 会话。

    `project` 可以是项目名（CLI）或项目 id（API）——两种入口走同一套装配，
    否则 CLI 能跑、接口缺一路的情况迟早出现，而且没人会发现。
    """
    conf = settings or default_settings
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"索引库不存在：{path}（先跑 ci index）")

    ensure_schema(path)
    conn = open_sqlite(path, row_factory=True)
    if isinstance(project, int):
        row = conn.execute(
            "SELECT id, name, root_path FROM project WHERE id = ?", (project,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id, name, root_path FROM project WHERE name = ?", (project,)
        ).fetchone()
    if row is None:
        conn.close()
        raise ProjectNotFound(str(project))

    project_id = int(row["id"])
    state = conn.execute(
        "SELECT head_commit FROM repo_state WHERE project_id = ?", (project_id,)
    ).fetchone()
    head_commit = state["head_commit"] if state else None

    embedder = embedder if embedder is not None else SiliconFlowEmbedder()
    active_lanes = set(lanes if lanes is not None else DEFAULT_AGENT_LANES) & ALL_LANES
    if embedder is None or not getattr(embedder, "enabled", False):
        active_lanes.discard(LANE_DENSE)

    retriever = Retriever(
        conn,
        embedder=embedder,
        db_path=path,
        config=RetrievalConfig(
            lanes=frozenset(active_lanes),
            top_k=conf.retrieval_top_k,
            rrf_k=conf.retrieval_rrf_k,
            neighbor_depth=conf.retrieval_neighbor_depth,
        ),
    )

    budget = budget or ContextBudget(
        max_turn_bytes=conf.max_context_bytes,
        max_message_bytes=conf.max_context_message_bytes,
        max_tool_result_bytes=12_000,
    )
    provider = provider if provider is not None else build_provider(conf)

    if concepts_dir is not None:
        from codeinsight.cognitive.indexing.concepts_sync import refresh_project_concepts

        if Path(concepts_dir) == Path("knowledge/concepts"):
            concepts_dir = knowledge_directory("concepts")
        refresh_project_concepts(conn, project_id=project_id, knowledge_dir=concepts_dir)

    services = ToolServices(
        conn=conn,
        project_id=project_id,
        repo_root=str(row["root_path"]),
        ref=head_commit,
        retriever=retriever,
        budget=budget,
        concepts_dir=Path(concepts_dir) if concepts_dir else None,
        provider=provider,
    )
    # 知识资产损坏时保留已有代码问答；教学端点会单独报告加载错误。
    learning = None
    try:
        learning = LearningBridge(
            KnowledgeService(LearningLibrary(knowledge_directory("learning")))
        )
    except KnowledgeError as exc:
        import logging

        logging.getLogger(__name__).warning("内置知识库暂不可用：%s", exc)
    runtime = AgentRuntime(
        learning=learning,
        provider=provider,
        registry=build_tools(services),
        store=store if store is not None else _DEFAULT_STORE,
        conn=conn,
        repo_root=str(row["root_path"]),
        budget=budget,
        config=config
        or RuntimeConfig(
            max_model_turns=conf.max_model_turns,
            max_tool_calls_per_turn=conf.max_tool_calls_per_turn,
        ),
    )
    return AgentSession(
        conn=conn,
        runtime=runtime,
        project_id=project_id,
        project_name=str(row["name"]),
        head_commit=head_commit,
        repo_root=str(row["root_path"]),
    )


__all__ = [
    "AgentSession",
    "LLMNotConfigured",
    "ProjectNotFound",
    "build_provider",
    "open_agent",
]
