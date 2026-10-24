"""Git 变更源。

源文档 §2.4 / §2.5：持续项目认知与变更解释。`DiffSource` 留了口
（文件监听、外部 agent 操作日志都可以接），M6 先实现 git 这一种。

两个决定：

- **只做「上个索引 commit → 目标 ref」的树对树比较**，不看工作区。
  索引绑定 commit，变更也必须绑定 commit——拿未提交的改动去比对，
  会让「这次变更」在你的编辑器存盘时自己变。
- `--no-renames`：重命名一律拆成「删一个、加一个」。跟踪重命名要额外
  的文件相似度判断，而对索引来说结果一样（旧行删掉、新行写入），
  拆开反而少一类边界情况。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from codeinsight.cognitive.changes.base import ChangedFile

_STATUS = {"A": "added", "M": "modified", "T": "modified", "D": "deleted"}


class GitError(RuntimeError):
    """git 调用失败。"""


@dataclass
class GitDiffSource:
    """仓库的 git 变更源。"""

    root: Path

    def _git(self, *args: str) -> str:
        cmd = ["git", "-C", str(self.root), "-c", "core.quotepath=false", *args]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)
        except OSError as exc:  # pragma: no cover —— git 不在 PATH 上
            raise GitError(f"无法执行 git：{exc}") from exc
        if proc.returncode != 0:
            raise GitError(proc.stderr.strip() or f"git {' '.join(args)} 失败")
        return proc.stdout

    def head(self, ref: str | None = None) -> str:
        return self._git("rev-parse", ref or "HEAD").strip()

    def is_ancestor(self, older: str, newer: str) -> bool:
        """`older` 是不是 `newer` 的祖先。

        不是祖先说明历史被改写过（rebase / force-push / 换分支）——
        这时增量比对没有意义，调用方应退回全量。
        """
        proc = subprocess.run(
            ["git", "-C", str(self.root), "merge-base", "--is-ancestor", older, newer],
            capture_output=True,
        )
        return proc.returncode == 0

    def changed_files(self, since: str, until: str | None = None) -> list[ChangedFile]:
        """`since..until` 之间变化的文件（缺省到 HEAD）。"""
        out = self._git("diff", "--name-status", "-z", "--no-renames", since, until or "HEAD")
        parts = [piece for piece in out.split("\0") if piece]
        changed: list[ChangedFile] = []
        for status, path in zip(parts[::2], parts[1::2], strict=False):
            kind = _STATUS.get(status[:1])
            if kind is None:
                continue
            changed.append(ChangedFile(path=path, status=kind))
        return changed

    def diff(self, since: str, until: str | None = None) -> str:
        return self._git("diff", "--no-renames", since, until or "HEAD")

    def file_at(self, path: str, commit: str) -> str | None:
        try:
            return self._git("show", f"{commit}:{path}")
        except GitError:
            return None
