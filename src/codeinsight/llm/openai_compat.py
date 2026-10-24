"""OpenAI 兼容的模型供应商（DeepSeek / SiliconFlow / 本地 vLLM 都走这里）。

源文档 §3.2「可配置 LLM API」。协议只认 `/chat/completions` 这一套：
换 provider 只需要换 `CI_LLM_BASE_URL` 与 `CI_LLM_MODEL`，不改 Agent 代码。

三件事在这个文件里被**显式**处理：

1. **流式与工具调用的组合**。`stream_with_tools` 边吐字边拼工具调用——
   工具调用的参数是分片到达的（`{"index":0,"function":{"arguments":"{\\"q"}`），
   只有按 `index` 累加才能还原。
2. **重试**走 `transport`，但是流一旦开始就不重试（否则用户看到重复前缀）。
3. **错误归一**：上游错误统一成 `UpstreamError`，Agent 层据此发 SSE `error`
   事件并保证 `done` 仍然发出。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from codeinsight.llm.provider import StreamChunk, ToolCall, ToolCallResponse
from codeinsight.llm.transport import request_with_retry, stream_with_retry


class LLMNotConfigured(RuntimeError):
    """没有 API key。调用方应当直接告诉用户去哪配，而不是抛网络错误。"""


def _tool_schema(tool: Mapping[str, Any]) -> dict[str, Any]:
    """内部工具描述 → OpenAI function schema。"""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": dict(tool["parameters"]),
        },
    }


class OpenAICompatProvider:
    """一个 OpenAI 兼容的 `/chat/completions` 端点。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: float = 120.0,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self.extra_headers = dict(extra_headers or {})

    # ── 元信息 ────────────────────────────────────────────────

    @property
    def model_id(self) -> str:
        """完整模型标识。评测报告要记录它——不同版本的数字不能混着比。"""
        return self.model

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    # ── 公共接口 ──────────────────────────────────────────────

    async def complete(
        self,
        system: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        max_tokens: int = 0,
        temperature: float = 0.0,
    ) -> str:
        payload = self._payload(system, messages, temperature=temperature, max_tokens=max_tokens)
        data = await self._post(payload)
        return self._content(data)

    async def complete_with_tools(
        self,
        system: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        *,
        max_tokens: int = 0,
        temperature: float = 0.0,
        tool_choice: str | Mapping[str, Any] = "auto",
    ) -> ToolCallResponse:
        payload = self._payload(
            system,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
        )
        data = await self._post(payload)
        return self._tool_response(data)

    async def stream_with_tools(
        self,
        system: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        *,
        max_tokens: int = 0,
        temperature: float = 0.0,
        tool_choice: str | Mapping[str, Any] = "auto",
    ) -> AsyncIterator[StreamChunk]:
        """流式补全。

        正文增量**立即**交出；工具调用在流末尾一次性给出。
        正文与工具调用可能同时出现（模型先解释一句再调工具），
        两样都保留——调用方自己决定正文算不算答案。
        """
        payload = self._payload(
            system,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            stream=True,
        )
        self._require_key()
        pending: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None

        async with stream_with_retry(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout_s,
        ) as response:
            if response.status_code >= 400:
                text = (await response.aread()).decode("utf-8", "replace")
                raise _http_error(response.status_code, text)
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choice = (event.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                text = delta.get("content")
                if isinstance(text, str) and text:
                    yield StreamChunk(text=text)
                for piece in delta.get("tool_calls") or []:
                    _accumulate_tool_call(pending, piece)
                if choice.get("finish_reason"):
                    finish_reason = str(choice["finish_reason"])

        yield StreamChunk(tool_calls=_finalize_tool_calls(pending), finish_reason=finish_reason)

    # ── 内部 ──────────────────────────────────────────────────

    def _require_key(self) -> None:
        if not self.api_key:
            raise LLMNotConfigured("没有 CI_LLM_API_KEY——先配置模型服务再提问")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }

    def _payload(
        self,
        system: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        temperature: float,
        max_tokens: int,
        tools: Sequence[Mapping[str, Any]] | None = None,
        tool_choice: str | Mapping[str, Any] = "auto",
        stream: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": temperature,
        }
        if max_tokens > 0:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = [_tool_schema(tool) for tool in tools]
            payload["tool_choice"] = tool_choice
        if stream:
            payload["stream"] = True
        return payload

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_key()
        response = await request_with_retry(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout_s,
        )
        if response.status_code >= 400:
            raise _http_error(response.status_code, response.text)
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamPayloadError(f"上游返回的不是 JSON：{exc}") from exc

    @staticmethod
    def _content(data: Mapping[str, Any]) -> str:
        try:
            return str(data["choices"][0]["message"].get("content") or "")
        except (KeyError, IndexError, TypeError) as exc:
            raise UpstreamPayloadError(f"上游响应缺少 choices[0].message：{exc}") from exc

    @staticmethod
    def _tool_response(data: Mapping[str, Any]) -> ToolCallResponse:
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise UpstreamPayloadError(f"上游响应缺少 choices[0].message：{exc}") from exc
        calls = [
            ToolCall(
                id=str(item.get("id") or f"call-{index}"),
                name=str((item.get("function") or {}).get("name") or ""),
                arguments=_parse_arguments((item.get("function") or {}).get("arguments")),
            )
            for index, item in enumerate(message.get("tool_calls") or [])
        ]
        return ToolCallResponse(content=str(message.get("content") or ""), tool_calls=calls)


class UpstreamPayloadError(RuntimeError):
    """上游 200 了，但响应体不是我们要的形状。"""


def _http_error(status: int, text: str) -> Exception:
    from codeinsight.llm.transport import UpstreamError

    return UpstreamError(f"上游返回 {status}：{text[:300]}", status=status)


def _parse_arguments(raw: Any) -> dict[str, Any]:
    """工具参数是 JSON 字符串；空串按空对象处理。"""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _accumulate_tool_call(pending: dict[int, dict[str, Any]], piece: Mapping[str, Any]) -> None:
    index = int(piece.get("index", 0))
    slot = pending.setdefault(index, {"id": "", "name": "", "arguments": ""})
    if piece.get("id"):
        slot["id"] = str(piece["id"])
    function = piece.get("function") or {}
    if function.get("name"):
        slot["name"] = str(function["name"])
    if function.get("arguments"):
        slot["arguments"] += str(function["arguments"])


def _finalize_tool_calls(pending: dict[int, dict[str, Any]]) -> list[ToolCall]:
    return [
        ToolCall(
            id=slot["id"] or f"call-{index}",
            name=slot["name"],
            arguments=_parse_arguments(slot["arguments"]),
        )
        for index, slot in sorted(pending.items())
        if slot["name"]
    ]


__all__ = [
    "LLMNotConfigured",
    "OpenAICompatProvider",
    "StreamChunk",
    "UpstreamPayloadError",
]
