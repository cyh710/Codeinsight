"""模型层：统一的 LLM Provider 接口（源文档 §3.2「可配置 LLM API」）。"""

from codeinsight.llm.provider import LLMProvider, ToolCall, ToolCallResponse

__all__ = ["LLMProvider", "ToolCall", "ToolCallResponse"]
