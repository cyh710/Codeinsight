"""读取状态按异步请求隔离；短来源编号不跨请求授予读取资格。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class ReadScope:
    versions: dict[str, str] = field(default_factory=dict)
    sources: dict[str, dict] = field(default_factory=dict)

    def register(self, target: dict) -> str:
        """同一目标复用编号；不同版本的同一路径保持分离。"""
        for key, item in self.sources.items():
            if item == target:
                return key
        key = f"s{len(self.sources) + 1}"
        self.sources[key] = dict(target)
        return key

    def resolve(self, raw: dict) -> dict | None:
        """路径只能命中唯一版本，范围必须在实际取得的来源内。"""
        ref = raw.get("source_ref")
        if "source_ref" in raw and (not isinstance(ref, str) or ref not in self.sources):
            return None
        candidates = [self.sources[ref]] if isinstance(ref, str) and ref in self.sources else []
        if raw.get("source_ref") and not candidates:
            return None
        if not candidates:
            candidates = [s for s in self.sources.values() if s.get("path") == raw.get("path")]
        versions = {
            (
                s.get("source_kind"),
                s.get("content_sha256"),
                s.get("index_epoch"),
                s.get("head_commit"),
            )
            for s in candidates
        }
        if len(versions) > 1 and not ref and not raw.get("content_sha256"):
            return None
        line = raw.get("lineno", candidates[0]["lineno"] if candidates else 1)
        end = raw.get("end_lineno", line)
        if type(line) is not int or type(end) is not int or end < line:
            return None
        candidates = [
            s
            for s in candidates
            if s["lineno"] <= line <= end <= s.get("end_lineno", s["lineno"])
            and (not raw.get("source_kind") or s.get("source_kind") == raw["source_kind"])
            and (not raw.get("content_sha256") or s.get("content_sha256") == raw["content_sha256"])
            and (not raw.get("path") or s["path"] == raw["path"])
        ]
        identities = {
            (
                s.get("source_kind"),
                s.get("content_sha256"),
                s.get("index_epoch"),
                s.get("head_commit"),
            )
            for s in candidates
        }
        if len(identities) != 1:
            return None
        return {**candidates[0], "lineno": line, "end_lineno": end}


CURRENT_SCOPE: ContextVar[ReadScope | None] = ContextVar("codeinsight_read_scope", default=None)


@contextmanager
def source_scope() -> Iterator[ReadScope]:
    """结束、异常和取消均恢复外层状态，不清理其他并发调用的缓存。"""
    scope = ReadScope()
    token = CURRENT_SCOPE.set(scope)
    try:
        yield scope
    finally:
        CURRENT_SCOPE.reset(token)
