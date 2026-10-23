"""索引快照导出。

产出一份**真实仓库的真实解析结果**的 JSON，给 B/C 两条线做开发期数据源：

- **B 线**：`symbols` / `edges` 直接拿来构造 `SymbolView` / `EdgeView` 写检测器测试。
- **C 线**：`frontend/src/api/mock.ts` 按同一形状返回假数据，前端不用等后端跑起来。

关键点：**这不是手写的假数据**。它由真正的扫描器 + 真正的解析器产出，
所以 B/C 看到的形状和线上一致——手写 mock 会骗人，形状对不上是常有的事。

导出的是**快照**，不是索引库：`concepts` 与 `flows` 在 B 线检测器 / A5 流程检测
落地前是空的，届时重跑一次这个命令即可补上。
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from codeinsight.cognitive.indexing.scanner import (
    RepoFile,
    list_repo_files,
    module_qualname,
    read_blobs,
)
from codeinsight.cognitive.parsing.base import ParseContext
from codeinsight.cognitive.parsing.python_parser import PythonParser


def _git_output(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if proc.returncode != 0:
        return ""
    return proc.stdout.decode("utf-8", "replace").strip()


def _stratified_sample(modules: list[str], target: int) -> set[str]:
    """按顶层目录**分层**取样。

    为什么要分层而不是随便抽：符号和边是**按模块**产生的，
    随机抽会漏掉整个目录（比如一个角色的代码全没了），
    而 fixture 的用途正是让 B/C 看到"各种形态都长什么样"。

    分层后每个目录至少留一个模块，各目录内部按等距取——
    于是 `backend/`、`tests/`、`mobile_sam/`（第三方）、根目录模块都在，
    边和符号的各种 kind 也都覆盖得到。
    """
    if target <= 0 or len(modules) <= target:
        return set(modules)

    groups: dict[str, list[str]] = {}
    for m in modules:
        groups.setdefault(m.split(".")[0], []).append(m)

    picked: set[str] = set()
    total = len(modules)
    for group in groups.values():
        group.sort()
        quota = max(1, round(target * len(group) / total))
        quota = min(quota, len(group))
        # 等距取 q 个：索引 floor(i * n / q)
        for i in range(quota):
            picked.add(group[min(len(group) - 1, i * len(group) // quota)])
    return picked


def _module_of(qualname: str, module_quals: set[str]) -> str | None:
    """符号/边属于哪个模块——取**最长的模块前缀**。

    不能用 `rsplit(".")[0]`：`backend.core.mod.Class.method` 的直接父级是
    `backend.core.mod.Class`，那是个**类**不是模块，按父级查会把方法漏掉。

    也不能只看第一段：`backend/__init__.py` 的模块 qualname 是 `backend`，
    按第一段匹配会把整个 backend 树都算进来。

    所以：从长到短找第一个**确实是模块**的前缀。
    """
    parts = qualname.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in module_quals:
            return candidate
    return None


def build_snapshot(
    root: Path,
    *,
    ref: str | None = None,
    project_name: str | None = None,
    max_modules: int = 40,
) -> dict[str, Any]:
    """对仓库做一次扫描 + 解析，返回快照字典。

    形状见 `fixtures/README.md`。

    `max_modules`
        符号与边只覆盖这么多模块（**分层取样**）。
        文件与模块列表是全量的——它们很便宜（688 个文件才 150 KB），
        而符号和边全量有 43k 条边、9 MB，入库不合适。
        传 `0` 表示不取样（要全量时用）。
    """
    root = Path(root)
    files: list[RepoFile] = list_repo_files(root, ref=ref)

    head_commit = _git_output(root, "rev-parse", ref or "HEAD")
    head_branch = _git_output(root, "rev-parse", "--abbrev-ref", ref or "HEAD")
    # 快照是要进公开仓库的，别把本机绝对路径写进去——有远程就用远程地址
    origin = _git_output(root, "remote", "get-url", "origin")
    root_label = origin or root.name

    # 只读 Python 源码——本项目 Python-only（ADR 0001）
    py_paths = [f.path for f in files if f.language == "python"]
    blobs = read_blobs(root, ref, py_paths)

    parser = PythonParser()
    ctx = ParseContext(project_id=1, repo_root=str(root))

    file_entries: list[dict[str, Any]] = []
    module_entries: list[dict[str, Any]] = []
    all_symbols: list[dict[str, Any]] = []
    all_edges: list[dict[str, Any]] = []

    for f in files:
        data = blobs.get(f.path)
        content = data if data is not None else b""
        file_entries.append(
            {
                "path": f.path,
                "language": f.language,
                "role": f.role,
                "content_sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": f.size_bytes,
                "line_count": content.count(b"\n") + 1 if content else 0,
                "in_chunk_index": f.in_chunk_index,
            }
        )

        if f.language != "python":
            continue

        source = content.decode("utf-8", "replace")
        parsed = parser.parse(f.path, source, ctx)
        module_qn = module_qualname(f.path)

        module_entries.append(
            {
                "qualname": module_qn,
                "path": f.path,
                "docstring": parsed.module_docstring or "",
            }
        )

        for sym in parsed.symbols:
            all_symbols.append(
                {
                    "qualname": sym.qualname,
                    "name": sym.name,
                    "kind": str(sym.kind),
                    "path": f.path,
                    "lineno": sym.lineno,
                    "end_lineno": sym.end_lineno,
                    "header": sym.header,
                    "docstring": sym.docstring or "",
                    "n_lines": sym.n_lines,
                    "is_async": sym.is_async,
                    "is_private": sym.is_private,
                }
            )

        for edge in parsed.edges:
            all_edges.append(
                {
                    "src_qualname": edge.src_qualname,
                    "dst_name": edge.dst_name,
                    "dst_qualname": edge.dst_qualname,
                    "kind": str(edge.kind),
                    "path": f.path,
                    "lineno": edge.lineno,
                    "confidence": edge.confidence,
                }
            )

    if max_modules > 0:
        module_quals = {m["qualname"] for m in module_entries}
        sampled = _stratified_sample(sorted(module_quals), max_modules)
        symbol_entries = [
            s for s in all_symbols if _module_of(s["qualname"], module_quals) in sampled
        ]
        edge_entries = [
            e for e in all_edges if _module_of(e["src_qualname"], module_quals) in sampled
        ]
    else:
        symbol_entries = all_symbols
        edge_entries = all_edges

    return {
        "project": {
            "id": 1,
            "name": project_name or root.name,
            "root_path": root_label,
            "head_commit": head_commit,
            "head_branch": head_branch,
        },
        "files": file_entries,
        "modules": module_entries,
        "symbols": symbol_entries,
        "edges": edge_entries,
        "concepts": [],
        "flows": [],
    }
