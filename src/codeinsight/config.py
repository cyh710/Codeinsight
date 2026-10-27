"""配置。

所有可调项走环境变量（前缀 `CI_`），默认值适合本地单机跑。
真实密钥只从环境变量读，**不落库、不入库、不进日志**。
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CI_", env_file=".env", extra="ignore")

    # ── 存储 ──────────────────────────────────────────────
    data_dir: Path = Path("./.ci")

    # ── 模型服务 ──────────────────────────────────────────
    llm_provider: str = "deepseek"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_api_key: str = ""
    llm_timeout_s: float = 120.0

    # ── 嵌入（源文档 §3.2「语义检索：Embedding + BM25」）──
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    embedding_api_key: str = ""
    embedding_dim: int = 1024

    # ── 切块（工程决定）────────────────────────────────────
    max_chunk_lines: int = 120
    """超大符号二次切分的行数上限。符号原子 ≠ 块原子。"""

    # ── 检索 ──────────────────────────────────────────────
    retrieval_top_k: int = 8
    retrieval_rrf_k: int = 60
    retrieval_neighbor_depth: int = 1
    """命中后沿调用边扩展几跳（源文档 §2.3-2「结合上下游调用关系解释」）。"""

    # ── 上下文有界（源文档 §3.2「上下文管理」）────────────
    max_tool_result_bytes: int = 80_000  # 持久化层
    max_context_bytes: int = 64_000  # 模型层
    max_context_message_bytes: int = 24_000
    max_tool_calls_per_turn: int = 16
    max_model_turns: int = 0  # 0 表示不限总轮次；正数仅用于主动启用的限额。

    # ── 编排执行（请求 0018 / ADR 0035）────────────────────
    executor: str = "claude-code"
    """执行驱动器：`claude-code` / `zcode` / `off`（关闭后对话识别退回普通问答）。"""
    executor_command: str = ""
    """驱动器 argv[0]。空 = 按驱动器取缺省（claude-code→`claude`，zcode→`node`）。"""
    executor_extra_args: str = ""
    """驱动器 argv 的附加项，逗号分隔（zcode 经 node 跑时放 cjs 脚本路径）。"""
    executor_timeout_s: int = 1800

    # ── 评测（源文档 §6）───────────────────────────────────
    eval_seed: int = 7
    eval_max_usd: float = 2.0


settings = Settings()
