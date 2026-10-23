"""变更源接口。

源文档 §2.4 / §2.5：持续项目认知与变更解释。当前实现是 Git，
但把接口抽象出来是为了以后能接别的变更源（文件监听、外部 agent 的操作日志）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ChangedFile:
    """一个变更过的文件。"""

    path: str
    status: str  # added | modified | deleted | renamed
    old_path: str | None = None
    lines_added: int = 0
    lines_removed: int = 0


@runtime_checkable
class DiffSource(Protocol):
    """提供仓库的变更历史。"""

    def head(self) -> str:
        """当前 HEAD 的 commit sha。"""
        ...

    def changed_files(self, since: str | None) -> list[ChangedFile]:
        """相对 `since`（None 表示与工作区对比）发生变化的文件。"""
        ...

    def diff(self, since: str | None) -> str:
        """统一 diff 文本。"""
        ...

    def file_at(self, path: str, commit: str) -> str | None:
        """取某个 commit 下的文件内容（用于对比符号是否真的变了）。"""
        ...


class LocalFileDiffSource:
    """占位实现：M6 之前不接变更源，M1 阶段用不到。"""

    def __init__(self, root: Path) -> None:
        self.root = root

    def head(self) -> str:
        raise NotImplementedError("变更源在 M6 实现")

    def changed_files(self, since: str | None) -> list[ChangedFile]:
        raise NotImplementedError("变更源在 M6 实现")

    def diff(self, since: str | None) -> str:
        raise NotImplementedError("变更源在 M6 实现")

    def file_at(self, path: str, commit: str) -> str | None:
        raise NotImplementedError("变更源在 M6 实现")
