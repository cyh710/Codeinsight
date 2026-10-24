"""MCP Server：把项目理解能力暴露给外部 agent（源文档 §2.7-3）。

ADR 0008：CodeInsight 自己不做写代码与执行命令——那些交给外部 agent
（Claude Code / Codex 等，自带沙箱）。我们占住「理解 / 变更验证 / 认知更新」，
通过 MCP（Model Context Protocol）把 14 个只读工具递给它们。

这样 §2.7 的闭环四段一段不丢，又不用自建 Docker 沙箱。
"""

from codeinsight.mcp.server import build_server, run_stdio

__all__ = ["build_server", "run_stdio"]
