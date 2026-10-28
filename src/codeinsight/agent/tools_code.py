"""代码侧工具：检索、定位、读源码、调用关系、模块概览。

符号与关系来自索引；read_file 默认读取工作区，历史来源显式绑定对应版本。
"""

from __future__ import annotations

import sqlite3
from typing import Any

from codeinsight.agent.tool import ToolContext, ToolResult
from codeinsight.agent.tools import BaseTool
from codeinsight.cognitive.indexing.source_store import SourceError, read_source
from codeinsight.cognitive.workspace import read_workspace
from codeinsight.models import Citation, Evidence

MAX_READ_LINES = 200
MAX_SNIPPET_LINES = 8


def _snippet(text: str, *, lines: int = MAX_SNIPPET_LINES, width: int = 400) -> str:
    head = "\n".join(text.splitlines()[:lines])
    if len(head) > width:
        head = head[:width] + "…"
    return head


def resolve_symbols(
    conn: sqlite3.Connection, project_id: int, text: str, *, limit: int = 8
) -> list[sqlite3.Row]:
    """按 qualname → 短名 → 后缀的顺序找符号。

    找到一层有结果就停：能唯一确定的时候，不要用模糊匹配去凑数。
    """
    base = (
        "SELECT s.id, s.qualname, s.name, s.kind, s.lineno, s.end_lineno, s.header,"
        " s.docstring, s.n_lines, f.path"
        " FROM symbol s JOIN file f ON f.id = s.file_id WHERE s.project_id = ?"
    )
    for clause, params in (
        (" AND s.qualname = ?", (text,)),
        (" AND s.name = ?", (text,)),
        (" AND s.qualname LIKE ?", (f"%.{text}",)),
    ):
        rows = conn.execute(
            base + clause + " ORDER BY s.lineno LIMIT ?", (project_id, *params, limit)
        ).fetchall()
        if rows:
            return rows
    return []


def _citation_of(row: sqlite3.Row) -> Citation:
    return Citation(
        path=row["path"],
        lineno=int(row["lineno"]),
        end_lineno=int(row["end_lineno"]),
        qualname=row["qualname"],
        snippet=_snippet(row["header"] or row["qualname"], lines=1, width=200),
    )


class SearchCodeTool(BaseTool):
    name = "search_code"
    description = (
        "按自然语言或标识符检索代码，返回带 file:line 的证据。"
        "问「X 在哪实现」「项目怎么处理 Y」时先调这个。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索词：标识符、概念或一句中文问题"},
            "top_k": {
                "type": "integer",
                "description": "返回条数，默认 8",
                "minimum": 1,
                "maximum": 20,
            },
        },
        "required": ["query"],
    }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = str(arguments.get("query") or "").strip()
        if not query:
            return self.result("缺少 query 参数：请给出要检索的标识符或问题。", error="bad_request")
        top_k = int(arguments.get("top_k") or 8)
        if self.services.retriever is None:
            return self.result(
                "语义检索器未配置，可用list_files/search_files直接查当前工作区。",
                error="not_indexed",
            )

        try:
            evidence: list[Evidence] = self.services.retriever.retrieve(
                query, k=top_k, project_id=self.services.project_id
            )
        except Exception:  # noqa: BLE001 —— 索引通道失败不应阻断工作区查阅
            return self.result(
                "索引检索暂不可用，请用list_files/search_files直接查当前工作区。",
                error="search_failed",
            )
        if not evidence:
            return self.result(
                f"在索引里没有检索到「{query}」相关的代码。"
                "这不代表当前工作区没有实现；请用list_files/search_files查当前文件，再用read_file阅读。",
                data={"query": query, "items": [], "citations": []},
            )

        lines = [f"「{query}」命中 {len(evidence)} 条证据："]
        for index, item in enumerate(evidence, start=1):
            lanes = ",".join(item.lanes)
            lines.append(
                f"{index}. {item.path}:{item.lineno}-{item.end_lineno}"
                f"  {item.qualname or ''}  [{lanes}]  score={item.score:.3f}"
            )
            snippet = _snippet(item.snippet, lines=3)
            if snippet:
                lines.append("   " + snippet.replace("\n", "\n   "))

        citations = [
            Citation(item.path, item.lineno, item.end_lineno, item.qualname, item.snippet)
            for item in evidence
        ]
        return self.result(
            "\n".join(lines),
            data={
                "query": query,
                "items": [
                    {
                        "chunk_id": item.chunk_id,
                        "path": item.path,
                        "lineno": item.lineno,
                        "end_lineno": item.end_lineno,
                        "qualname": item.qualname,
                        "snippet": item.snippet,
                        "score": item.score,
                        "lanes": list(item.lanes),
                        "concepts": list(item.concept_ids),
                    }
                    for item in evidence
                ],
                "citations": self.citations(citations),
            },
        )


class FindSymbolTool(BaseTool):
    name = "find_symbol"
    description = (
        "按名字精确查找符号（函数 / 类 / 方法），返回定义位置、签名、docstring 与引用数。"
        "已经知道名字时用它，比 search_code 准。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "符号名，可带模块前缀（如 backend.api.pet.stream_chat）",
            }
        },
        "required": ["name"],
    }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        name = str(arguments.get("name") or "").strip()
        if not name:
            return self.result("缺少 name 参数。", error="bad_request")
        rows = resolve_symbols(self.services.conn, self.services.project_id, name)
        if not rows:
            return self.result(
                f"没有找到名为「{name}」的符号。可以用 search_code 按语义找，"
                "或确认是否带了正确的模块前缀。",
                data={"items": [], "citations": []},
                error="not_found",
            )

        lines = [f"找到 {len(rows)} 个定义："]
        for row in rows:
            refs = self.services.conn.execute(
                "SELECT COUNT(*) FROM edge WHERE project_id = ? AND dst_symbol_id = ?",
                (self.services.project_id, row["id"]),
            ).fetchone()[0]
            lines.append(
                f"- {row['path']}:{row['lineno']}-{row['end_lineno']}  "
                f"{row['qualname']}  ({row['kind']}, {refs} 处引用)"
            )
            if row["header"]:
                lines.append(f"    {row['header']}")
            doc = (row["docstring"] or "").strip()
            if doc:
                lines.append(f"    {doc.splitlines()[0]}")

        return self.result(
            "\n".join(lines),
            data={
                "items": [
                    {
                        "qualname": row["qualname"],
                        "name": row["name"],
                        "kind": row["kind"],
                        "path": row["path"],
                        "lineno": int(row["lineno"]),
                        "end_lineno": int(row["end_lineno"]),
                        "header": row["header"],
                        "docstring": row["docstring"],
                    }
                    for row in rows
                ],
                "citations": self.citations([_citation_of(row) for row in rows]),
            },
        )


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "默认读取当前工作区文件，不要求索引或提交，支持代码/配置/实验文本。一次最多200行。HTTP请求内默认固定首次版本；MCP每次默认调用重读。历史阅读可传完整target或显式source_kind和版本。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "仓库相对路径，如 backend/api/pet.py"},
            "target": {
                "type": "object",
                "description": "跨调用固定版本时传入上一结果的完整target（含项目、路径、source_kind和版本身份）",
            },
            "start_line": {"type": "integer", "description": "起始行（从 1 开始），默认 1"},
            "end_line": {"type": "integer", "description": "结束行（含），默认 start+200"},
            "source_kind": {"type": "string", "enum": ["workspace", "index"]},
            "content_sha256": {"type": "string"},
            "index_epoch": {"type": "integer"},
            "head_commit": {"type": "string"},
        },
        "anyOf": [{"required": ["path"]}, {"required": ["target"]}],
    }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if "target" in arguments:
            target = arguments["target"]
            if (
                not isinstance(target, dict)
                or target.get("kind") != "code"
                or target.get("project_id") != self.services.project_id
                or not target.get("source_kind")
                or not target.get("content_sha256")
            ):
                return self.result(
                    "来源目标缺少完整版本身份或不属于当前项目。", error="bad_request"
                )
            arguments = {
                **arguments,
                **{
                    k: target[k]
                    for k in ("path", "source_kind", "content_sha256", "head_commit", "index_epoch")
                    if k in target
                },
                "start_line": arguments.get("start_line", target.get("lineno", 1)),
                "end_line": arguments.get(
                    "end_line", target.get("end_lineno", target.get("lineno", 1))
                ),
            }
        path = str(arguments.get("path") or "").strip()
        if not path:
            return self.result("缺少 path 参数。", error="bad_request")
        kind = arguments.get("source_kind") or (
            "index"
            if arguments.get("index_epoch")
            or arguments.get("head_commit")
            or arguments.get("content_sha256")
            else "workspace"
        )
        if kind not in {"workspace", "index"}:
            return self.result("未知源码类型。", error="bad_request")
        try:
            start = max(1, int(arguments.get("start_line") or 1))
            end = int(arguments.get("end_line") or start + MAX_READ_LINES - 1)
        except (ValueError, TypeError):
            return self.result("行号必须是整数。", error="bad_request")
        if end < start:
            return self.result("结束行不能早于起始行。", error="bad_request")
        try:
            if kind == "workspace":
                expected = arguments.get("content_sha256") or self.services.read_versions.get(path)
                source = read_workspace(
                    self.services.conn, self.services.project_id, path, expected
                )
                self.services.read_versions.setdefault(path, source.sha256)
            else:
                source = read_source(
                    self.services.conn,
                    self.services.project_id,
                    path,
                    expected_sha=arguments.get("content_sha256"),
                    index_epoch=arguments.get("index_epoch"),
                    head_commit=arguments.get("head_commit"),
                )
            body = source.raw.decode("utf-8", "replace")
        except SourceError as exc:
            return self.result(str(exc), error=exc.code)
        except Exception as exc:  # noqa: BLE001 —— 工具不能抛
            return self.result(f"读取失败：{exc}", error="read_failed")

        lines = body.splitlines()
        total = len(lines)
        if start > max(1, total):
            return self.result("起始行超出文件范围。", error="bad_request")
        end = min(end, start + MAX_READ_LINES - 1, max(total, start))
        selected = lines[start - 1 : end]
        numbered = "\n".join(f"{start + offset:>6}  {text}" for offset, text in enumerate(selected))
        header = f"{path}:{start}-{end}（共 {total} 行；{'当前工作区' if kind == 'workspace' else '索引快照'}；{source.sha256[:12]}）"
        if source.workspace_changed:
            header += "（正在读取已索引快照，磁盘文件已有修改；本回合不切换版本）"
        return self.result(
            f"{header}\n{numbered}",
            data={
                "path": path,
                "start_line": start,
                "end_line": end,
                "total_lines": total,
                "citations": [
                    {**citation, "snippet": "\n".join(selected[:3])}
                    for citation in self.citations(
                        [
                            Citation(
                                path,
                                start,
                                end,
                                source_kind=kind,
                                content_sha256=source.sha256,
                                index_epoch=source.index_epoch,
                                head_commit=source.head_commit,
                            )
                        ]
                    )
                ],
            },
        )


class _RelationTool(BaseTool):
    """调用者 / 被调者的公共实现：只差边的方向。"""

    outgoing = False
    kind = "call"

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        symbol = str(arguments.get("symbol") or "").strip()
        if not symbol:
            return self.result("缺少 symbol 参数。", error="bad_request")
        rows = resolve_symbols(self.services.conn, self.services.project_id, symbol, limit=1)
        if not rows:
            return self.result(
                f"没有找到符号「{symbol}」。先用 find_symbol 或 search_code 确认名字。",
                data={"items": [], "citations": []},
                error="not_found",
            )
        target = rows[0]
        column = "src_symbol_id" if self.outgoing else "dst_symbol_id"
        # 两边都连：调用点所在文件永远是**边的源符号**的文件，
        # 被调符号的路径单独取。混用会让引用指向错的文件。
        sql = (
            "SELECT src.qualname AS src_qualname, sf.path AS src_path,"
            " e.lineno AS edge_line, e.confidence, e.dst_name, e.dst_qualname,"
            " dst.qualname AS dst_qualname, dst.lineno AS dst_lineno, df.path AS dst_path"
            " FROM edge e"
            " JOIN symbol src ON src.id = e.src_symbol_id"
            " JOIN file sf ON sf.id = src.file_id"
            " LEFT JOIN symbol dst ON dst.id = e.dst_symbol_id"
            " LEFT JOIN file df ON df.id = dst.file_id"
            f" WHERE e.project_id = ? AND e.{column} = ? AND e.kind = ?"
            " ORDER BY sf.path, e.lineno LIMIT 40"
        )
        try:
            edges = self.services.conn.execute(
                sql, (self.services.project_id, target["id"], self.kind)
            ).fetchall()
        except sqlite3.Error as exc:  # pragma: no cover —— 表结构问题要显式暴露给模型
            return self.result(f"查询关系失败：{exc}", error="query_failed")

        direction = "调用" if self.outgoing else "被调用"
        if not edges:
            return self.result(
                f"没有找到 {target['qualname']} 的{direction}关系。"
                "可能是动态调用，静态分析看不到；也可能是入口函数。",
                data={"symbol": target["qualname"], "items": [], "citations": []},
            )

        lines = [f"{target['qualname']} 的{direction}关系（{len(edges)} 条）："]
        citations: list[Citation] = []
        items: list[dict[str, Any]] = []
        for edge in edges:
            uncertain = float(edge["confidence"]) < 1.0
            mark = "  ⚠ 可能" if uncertain else ""
            edge_line = int(edge["edge_line"] or 0)
            if self.outgoing:
                callee = edge["dst_qualname"] or edge["dst_name"]
                where = (
                    f" → {callee}（{edge['dst_path']}:{edge['dst_lineno']}）"
                    if edge["dst_path"]
                    else f" → {callee}"
                )
            else:
                where = f" ← {edge['src_qualname']}"
            lines.append(f"- {edge['src_path']}:{edge_line}  {where}{mark}")
            # 引用落在**调用点**（源文件的那一行）：这是读者要去看的地方。
            citations.append(
                Citation(edge["src_path"], edge_line, edge_line, edge["src_qualname"], "")
            )
            items.append(
                {
                    "src_qualname": edge["src_qualname"],
                    "src_path": edge["src_path"],
                    "lineno": edge_line,
                    "dst_qualname": edge["dst_qualname"] or edge["dst_name"],
                    "dst_path": edge["dst_path"],
                    "dst_lineno": int(edge["dst_lineno"] or 0),
                    "confidence": float(edge["confidence"]),
                    "uncertain": uncertain,
                }
            )
        return self.result(
            "\n".join(lines),
            data={
                "symbol": target["qualname"],
                "items": items,
                "citations": self.citations(citations),
            },
        )


class GetCallersTool(_RelationTool):
    name = "get_callers"
    description = "查找调用了某个符号的位置。改一个函数前，用它看谁会被影响。"
    parameters = {
        "type": "object",
        "properties": {"symbol": {"type": "string", "description": "符号名或全限定名"}},
        "required": ["symbol"],
    }
    outgoing = False


class GetCalleesTool(_RelationTool):
    name = "get_callees"
    description = "查找某个符号调用了哪些符号。想知道一段逻辑往下走到哪时用。"
    parameters = {
        "type": "object",
        "properties": {"symbol": {"type": "string", "description": "符号名或全限定名"}},
        "required": ["symbol"],
    }
    outgoing = True


class GetModuleOverviewTool(BaseTool):
    name = "get_module_overview"
    description = (
        "查看一个模块（文件）的职责、docstring 与主要符号。回答「这个模块是干什么的」时用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "模块文件路径（如 backend/api/pet.py）"}
        },
        "required": ["path"],
    }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = str(arguments.get("path") or "").strip().lstrip("/")
        if not path:
            return self.result("缺少 path 参数。", error="bad_request")
        row = self.services.conn.execute(
            """
            SELECT m.qualname, m.docstring, m.responsibility, m.is_core, f.path, f.line_count
            FROM module m JOIN file f ON f.id = m.file_id
            WHERE m.project_id = ? AND (f.path = ? OR m.qualname = ?)
            """,
            (self.services.project_id, path, path),
        ).fetchone()
        if row is None:
            return self.result(
                f"没有找到模块「{path}」。模块就是 Python 文件，路径要写全（含目录）。",
                data={"items": [], "citations": []},
                error="not_found",
            )

        symbols = self.services.conn.execute(
            """
            SELECT s.qualname, s.name, s.kind, s.lineno, s.end_lineno, s.header
            FROM symbol s JOIN file f ON f.id = s.file_id
            WHERE s.project_id = ? AND f.path = ? AND s.parent_symbol_id IS NULL
            ORDER BY s.lineno LIMIT 20
            """,
            (self.services.project_id, row["path"]),
        ).fetchall()

        lines = [
            f"模块 {row['qualname']}（{row['path']}，{row['line_count'] or '?'} 行）",
            f"职责：{row['responsibility'] or '未标注（可从 docstring 与符号推断）'}",
        ]
        doc = (row["docstring"] or "").strip()
        if doc:
            lines.append("docstring：" + doc.splitlines()[0])
        if symbols:
            lines.append("主要符号：")
            for symbol in symbols:
                lines.append(
                    f"- {symbol['qualname']}:{symbol['lineno']}  ({symbol['kind']})  "
                    f"{(symbol['header'] or '').strip()}"
                )
        citations = [
            Citation(row["path"], int(s["lineno"]), int(s["end_lineno"]), s["qualname"], "")
            for s in symbols
        ]
        return self.result(
            "\n".join(lines),
            data={
                "module": row["qualname"],
                "path": row["path"],
                "responsibility": row["responsibility"],
                "docstring": row["docstring"],
                "is_core": bool(row["is_core"]),
                "symbols": [
                    {
                        "qualname": s["qualname"],
                        "kind": s["kind"],
                        "lineno": int(s["lineno"]),
                        "end_lineno": int(s["end_lineno"]),
                    }
                    for s in symbols
                ],
                "citations": self.citations(citations),
            },
        )
