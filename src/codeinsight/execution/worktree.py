"""git worktree 隔离（ADR 0035）：执行 agent 与用户检出互不可见。

只开任务分支不开 worktree 是**不可接受**的——切分支会动用户当前检出的
内容与暂存区。worktree 给执行 agent 一份独立检出，用户侧零影响；
拒绝/放弃时整个目录一删，仓库回到原样。

worktree 目录放在 CodeInsight 自己的数据目录（`.ci/exec-worktrees/`）下，
**不放用户仓库里**——否则那个目录会被用户的扫描/检索当成新代码。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from codeinsight.config import settings
from codeinsight.storage.sqlite import db_path


class WorktreeError(RuntimeError):
    """git 操作失败。调用方据此把任务转 failed 并给出可读原因。"""


def _git(repo: Path, *args: str, timeout: float = 60.0) -> str:
    """在 repo 里跑一次 git，失败抛 WorktreeError（带 stderr，可直读）。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[:400]
        raise WorktreeError(f"git {' '.join(args[:2])} 失败：{detail}") from exc
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise WorktreeError(f"git {' '.join(args[:2])} 失败：{exc}") from exc
    return out.stdout.strip()


@dataclass(frozen=True)
class TaskWorktree:
    """一个执行任务的隔离检出。"""

    path: Path
    branch: str
    base_commit: str
    repo_root: Path


def is_git_repo(root: Path) -> bool:
    try:
        _git(root, "rev-parse", "--git-dir", timeout=15)
        return True
    except WorktreeError:
        return False


def repo_is_clean(root: Path) -> bool:
    """工作区是否干净（合入前置检查：用户的未提交改动优先于一切）。"""
    status = _git(root, "status", "--porcelain")
    return status == ""


def head_sha(root: Path) -> str:
    return _git(root, "rev-parse", "HEAD")


def worktree_root() -> Path:
    """所有执行 worktree 的父目录：数据目录下的 exec-worktrees/。"""
    return db_path(settings.data_dir).parent / "exec-worktrees"


def create_task_worktree(repo_root: Path, task_id: str) -> TaskWorktree:
    """为任务建独立检出 + 任务分支。已存在则报错（task_id 应唯一）。"""
    branch = f"ci-exec/{task_id}"
    path = worktree_root() / task_id
    path.parent.mkdir(parents=True, exist_ok=True)
    base = head_sha(repo_root)
    if path.exists():
        raise WorktreeError(f"worktree 目录已存在：{path}")
    _git(repo_root, "worktree", "add", "-b", branch, str(path), base)
    return TaskWorktree(path=path, branch=branch, base_commit=base, repo_root=repo_root)


def remove_task_worktree(task: TaskWorktree) -> None:
    """整目录删除 + 删任务分支。拒绝/放弃/已合入后的清理路径。"""
    try:
        _git(task.repo_root, "worktree", "remove", "--force", str(task.path))
    except WorktreeError:
        # 目录已被外部删除等情况：prune 兜底，不让清理挡住状态机。
        _git(task.repo_root, "worktree", "prune")
    try:
        _git(task.repo_root, "branch", "-D", task.branch)
    except WorktreeError:
        pass  # 分支不存在（未产生提交）时忽略


def ensure_committed(task: TaskWorktree, message: str) -> str:
    """把 worktree 里的改动落成提交，返回该提交的 sha。

    无头 agent 通常不主动 commit（prompt 里要求了，但不可信）——
    这里兜底：有改动就提交，保证 merge/diff 有确定对象。
    """
    status = _git(task.path, "status", "--porcelain")
    if status:
        _git(task.path, "add", "-A")
        _git(task.path, "commit", "-m", message)
    return head_sha(task.path)


def diff_summary(task: TaskWorktree, head: str) -> dict:
    """契约 §16.3 的 diff_summary，全部来自 git 事实。"""
    numstat = _git(task.path, "diff", "--numstat", f"{task.base_commit}..{head}")
    namestatus = _git(task.path, "diff", "--name-status", f"{task.base_commit}..{head}")
    status_map = {"A": "added", "M": "modified", "D": "deleted"}
    files: list[dict] = []
    insertions = deletions = 0
    counts: dict[str, dict] = {}
    for line in namestatus.splitlines():
        if not line.strip():
            continue
        st, _, path = line.partition("\t")
        counts[path.strip()] = {"status": status_map.get(st[0], st), "add": 0, "del": 0}
    for line in numstat.splitlines():
        if not line.strip():
            continue
        add, dele, path = line.split("\t", 2)
        add_i = int(add) if add != "-" else 0
        del_i = int(dele) if dele != "-" else 0
        insertions += add_i
        deletions += del_i
        entry = counts.setdefault(path.strip(), {"status": "modified", "add": 0, "del": 0})
        entry["add"], entry["del"] = add_i, del_i
    for path, meta in counts.items():
        files.append({"path": path, **meta})
    return {
        "files_changed": len(files),
        "insertions": insertions,
        "deletions": deletions,
        "files": files,
    }


def merge_into_current(task: TaskWorktree, message: str) -> str:
    """第二道审批通过后的合入：merge 任务分支到用户当前分支。

    要求用户工作区干净（repo_is_clean 由调用方先查——用户的未提交
    改动永远优先，不为合入让路）。
    """
    _git(task.repo_root, "merge", "--no-ff", task.branch, "-m", message)
    return head_sha(task.repo_root)
