"""工作区工具在没有索引的项目也可用，结果不冒充索引关系。"""

from __future__ import annotations

import fnmatch
import re
from typing import Any

from codeinsight.agent.tool import ToolContext, ToolResult
from codeinsight.agent.tools import BaseTool
from codeinsight.cognitive.indexing.source_store import SourceError
from codeinsight.cognitive.workspace import (
    MAX_SEARCH_BYTES,
    list_paths,
    read_current,
    read_workspace,
)


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "浏览当前项目的实际文件，包含未提交和未索引文件；不依赖索引。可按路径或glob筛选。"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "路径片段或glob，如 experiments 或 *.py"},
            "path": {"type": "string", "description": "可选子目录，从此处开始扫描，避免根目录限额"},
        },
        "required": [],
    }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """仅列举当前根内文件，达到扫描限额时不能宣称目录已完整覆盖。"""
        try:
            paths, truncated = list_paths(
                self.services.repo_root, path=str(arguments.get("path") or "")
            )
            pattern = str(arguments.get("pattern") or "").strip()
            paths = [
                p
                for p in paths
                if not pattern
                or pattern.lower() in p.lower()
                or fnmatch.fnmatch(p.lower(), pattern.lower())
            ]
            more = len(paths) > 100
            return self.result(
                "当前工作区文件：\n"
                + "\n".join(paths[:100])
                + ("\n扫描或展示已截断，可缩小路径范围。" if truncated or more else ""),
                data={
                    "paths": paths[:100],
                    "source_kind": "workspace",
                    "truncated": truncated or more,
                },
            )
        except (SourceError, OSError) as exc:
            return self.result(str(exc), error="read_failed")


class SearchFilesTool(BaseTool):
    name = "search_files"
    description = "在当前工作区直接搜索字面文本，包含代码、配置、README、txt/csv实验结果和未提交文件；不依赖索引。关键词可分开用空格输入，任一命中。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "path": {"type": "string", "description": "可选子目录，从此处开始搜索"},
            "pattern": {"type": "string", "description": "可选路径片段或glob"},
        },
        "required": ["query"],
    }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """命中内容先保存后引用；截断与跳过文件均保留在结果中。"""
        query = str(arguments.get("query") or "").strip()
        if not query:
            return self.result("请输入要搜索的文本。", error="bad_request")
        terms = [s.casefold() for s in re.split(r"\s+", query) if s][:12]
        pattern = str(arguments.get("pattern") or "")
        try:
            paths, truncated = list_paths(
                self.services.repo_root, path=str(arguments.get("path") or "")
            )
            items, size, skipped = [], 0, 0
            for path in paths:
                if (
                    pattern
                    and pattern.lower() not in path.lower()
                    and not fnmatch.fnmatch(path.lower(), pattern.lower())
                ):
                    continue
                if size >= MAX_SEARCH_BYTES:
                    truncated = True
                    break
                try:
                    raw = read_current(self.services.repo_root, path)
                except SourceError:
                    skipped += 1
                    continue
                size += len(raw)
                matches = [
                    (i, text)
                    for i, text in enumerate(raw.decode("utf-8", "replace").splitlines(), 1)
                    if any(term in text.casefold() for term in terms)
                ]
                if not matches:
                    continue
                source = read_workspace(
                    self.services.conn,
                    self.services.project_id,
                    path,
                    self.services.workspace_versions.get(path),
                )
                self.services.workspace_versions[path] = source.sha256
                # 引用必须来自保存的字节；文件在扫描与保存之间变化时重新匹配。
                matches = [
                    (i, text)
                    for i, text in enumerate(source.raw.decode("utf-8", "replace").splitlines(), 1)
                    if any(term in text.casefold() for term in terms)
                ]
                for line, text in matches[:3]:
                    items.append(
                        {
                            "path": path,
                            "lineno": line,
                            "end_lineno": line,
                            "snippet": text[:400],
                            "source_kind": "workspace",
                            "content_sha256": source.sha256,
                        }
                    )
                if len(items) >= 20:
                    truncated = True
                    break
            items = items[:20]
            text = (
                "\n".join(f"{item['path']}:{item['lineno']}  {item['snippet']}" for item in items)
                or "本次有界工作区搜索未命中；可改用标识符、英文关键词或缩小目录。"
            )
            text += f"\n扫描字节：{size}；跳过不可读/超限文件：{skipped}。" + (
                "结果或扫描已截断。" if truncated else ""
            )
            return self.result(
                text,
                data={
                    "items": items,
                    "citations": items,
                    "source_kind": "workspace",
                    "truncated": truncated,
                    "skipped": skipped,
                },
            )
        except (SourceError, OSError) as exc:
            return self.result(str(exc), error="read_failed")
