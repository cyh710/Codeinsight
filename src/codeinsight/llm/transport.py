"""带重试与熔断的上游 HTTP 传输。

源文档 §3.2「可配置 LLM API」。移植自织忆 `ai-companion-agent`
`backend/llm/transport.py`（Apache-2.0，见 `docs/ported-from-tapestry.md`）：
保留重试策略与同源熔断，去掉与产品绑定的 provider 路由。

为什么这两件事值得单独一层：

- **重试**：上游 429/5xx 与连接超时是常态，调用方不该各自写一遍退避。
  只在**建立流之前**重试——流已经开始吐字了再重试，用户会看到重复内容。
- **熔断**：连续失败说明上游是真的不可用。继续打只会把等待时间
  乘以重试次数，还会拖慢整个回合。冷却期内直接失败，让 Agent 立即
  把「上游不可用」告诉用户，而不是转十次圈。
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

_CLIENT: httpx.AsyncClient | None = None
_FAILURES: dict[str, tuple[int, float]] = {}
_MAX_ATTEMPTS = 3
_OPEN_AFTER_FAILURES = 3
_OPEN_SECONDS = 20.0


class UpstreamCircuitOpen(RuntimeError):
    """熔断中：同源最近连续失败次数已达阈值。"""


class UpstreamError(RuntimeError):
    """上游返回了不可重试的错误，或重试用尽。"""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def get_http_client() -> httpx.AsyncClient:
    global _CLIENT
    if _CLIENT is None or _CLIENT.is_closed:
        _CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=10.0),
            limits=httpx.Limits(max_connections=12, max_keepalive_connections=6),
        )
    return _CLIENT


async def close_http_client() -> None:
    """测试与进程退出时释放连接池。"""
    global _CLIENT
    if _CLIENT is not None:
        await _CLIENT.aclose()
    _CLIENT = None
    _FAILURES.clear()


def _origin(url: str) -> str:
    parsed = httpx.URL(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{parsed.scheme}://{parsed.host}:{port}"


def _retryable_status(status: int) -> bool:
    return status in (408, 429) or 500 <= status <= 599


def _check_circuit(origin: str) -> None:
    failures, opened_at = _FAILURES.get(origin, (0, 0.0))
    if failures >= _OPEN_AFTER_FAILURES and time.monotonic() - opened_at < _OPEN_SECONDS:
        raise UpstreamCircuitOpen("模型服务暂时不可用，正在短暂冷却后重试")


def _record_success(origin: str) -> None:
    _FAILURES.pop(origin, None)


def _record_failure(origin: str) -> None:
    failures, _ = _FAILURES.get(origin, (0, 0.0))
    _FAILURES[origin] = (failures + 1, time.monotonic())


async def _sleep_before_retry(attempt: int) -> None:
    """指数退避 + 抖动：避免多个请求在同一时刻一起重试。"""
    await asyncio.sleep((0.2 * (2**attempt)) + random.uniform(0, 0.08))


async def request_with_retry(method: str, url: str, **kwargs) -> httpx.Response:
    """发请求；可重试状态与连接错误最多重试 `_MAX_ATTEMPTS` 次。"""
    origin = _origin(url)
    _check_circuit(origin)
    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = await get_http_client().request(method, url, **kwargs)
            if not _retryable_status(response.status_code):
                _record_success(origin)
                return response
            last_error = UpstreamError(
                f"上游返回 {response.status_code}：{response.text[:200]}",
                status=response.status_code,
            )
            await response.aclose()
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.RemoteProtocolError,
        ) as exc:
            last_error = exc
        if attempt + 1 < _MAX_ATTEMPTS:
            await _sleep_before_retry(attempt)
    _record_failure(origin)
    assert last_error is not None
    raise last_error


@asynccontextmanager
async def stream_with_retry(method: str, url: str, **kwargs) -> AsyncIterator[httpx.Response]:
    """流式请求：**只在第一个字节到达之前**重试。

    一旦调用方开始消费响应体，就不能再重试——否则用户会看到重复的前缀。
    """
    origin = _origin(url)
    _check_circuit(origin)
    last_error: Exception | None = None
    manager = None
    response = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            manager = get_http_client().stream(method, url, **kwargs)
            response = await manager.__aenter__()
            if not _retryable_status(response.status_code):
                _record_success(origin)
                break
            last_error = UpstreamError(
                f"上游返回 {response.status_code}：{(await response.aread())[:200]!r}",
                status=response.status_code,
            )
            await manager.__aexit__(None, None, None)
            manager = None
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.RemoteProtocolError,
        ) as exc:
            last_error = exc
        if attempt + 1 < _MAX_ATTEMPTS:
            await _sleep_before_retry(attempt)
    else:
        _record_failure(origin)
        assert last_error is not None
        raise last_error

    try:
        assert response is not None
        yield response
    finally:
        if manager is not None:
            await manager.__aexit__(None, None, None)
