"""CodeInsight 命令行入口。

子命令按里程碑接入：

    ci init-db                 建库建表
    ci import --repo <path>    导入仓库并建索引      (M1)
    ci search "<query>"        检索并返回 file:line   (M2)
    ci ask "<question>"        对项目提问            (M3)
    ci concepts                列出识别到的技术概念   (M1.5)
    ci explain <concept>       三级深度解释一个概念   (M3)
    ci changes                 变更说明              (M6)
    ci eval ...                跑对照评测            (M5)
    ci report --run <dir>      生成评测报告          (M5)
    ci mcp                     启动 MCP Server        (M7)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from codeinsight import __version__
from codeinsight.config import settings
from codeinsight.storage.sqlite import db_path, ensure_schema


def _cmd_init_db(args: argparse.Namespace) -> int:
    path = db_path(settings.data_dir)
    action = ensure_schema(path)
    print(f"schema {action} → {path}")
    return 0


def _cmd_where(args: argparse.Namespace) -> int:
    print(f"db_path = {db_path(settings.data_dir)}")
    print(f"data_dir = {settings.data_dir}")
    return 0


def _cmd_dump_fixture(args: argparse.Namespace) -> int:
    """导出索引快照（B/C 两条线的开发期数据源）。

    产出的是**真实仓库的真实解析结果**，不是手写 mock——
    手写 mock 会骗人，形状对不上是常有的事。
    """
    import json

    from codeinsight.cognitive.indexing.snapshot import build_snapshot

    snapshot = build_snapshot(
        Path(args.repo), ref=args.ref, project_name=args.name, max_modules=args.max_modules
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    project = snapshot["project"]
    print(f"→ {out}")
    print(f"   project={project['name']} @ {project['head_commit'][:8]} ({project['head_branch']})")
    print(
        f"   files={len(snapshot['files'])} modules={len(snapshot['modules'])} "
        f"symbols={len(snapshot['symbols'])} edges={len(snapshot['edges'])}"
    )
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    """检索（M2）：问一句「X 在哪」，返回带 file:line 的证据。"""
    from codeinsight.cognitive.embedding.siliconflow import SiliconFlowEmbedder
    from codeinsight.cognitive.retrieval.retriever import (
        ALL_LANES,
        LANE_BM25,
        LANE_DENSE,
        RetrievalConfig,
        Retriever,
    )
    from codeinsight.storage.sqlite import open_sqlite

    path = db_path(settings.data_dir)
    if not path.exists():
        print(f"索引库不存在：{path}（先跑 ci index）")
        return 1

    lanes = {name.strip() for name in args.lanes.split(",") if name.strip()} or {LANE_BM25}
    unknown = lanes - ALL_LANES
    if unknown:
        print(f"未知通道：{', '.join(sorted(unknown))}（可用：{', '.join(sorted(ALL_LANES))}）")
        return 2

    embedder = SiliconFlowEmbedder()
    if LANE_DENSE in lanes and not embedder.enabled:
        print("（没有 CI_EMBEDDING_API_KEY，稠密通道跳过）")
        lanes.discard(LANE_DENSE)

    conn = open_sqlite(path, row_factory=True)
    try:
        row = conn.execute("SELECT id FROM project WHERE name = ?", (args.project,)).fetchone()
        if row is None:
            print(f"没有名为 {args.project} 的项目")
            return 1
        project_id = int(row[0])

        retriever = Retriever(
            conn,
            embedder=embedder,
            db_path=path,
            config=RetrievalConfig(
                lanes=frozenset(lanes),
                top_k=args.k,
                rrf_k=settings.retrieval_rrf_k,
                neighbor_depth=settings.retrieval_neighbor_depth,
            ),
        )
        results = retriever.retrieve(args.query, k=args.k, project_id=project_id)
    finally:
        conn.close()

    if not results:
        print("没有命中。")
        return 0

    print(f"「{args.query}」→ {len(results)} 条证据")
    for item in results:
        lanes_str = ",".join(item.lanes)
        print(f"  {item.path}:{item.lineno}  {item.qualname or ''}  [{lanes_str}]")
        snippet = " ".join(item.snippet.splitlines())[:120]
        print(f"      {snippet}")
    return 0


def _cmd_eval_locate(args: argparse.Namespace) -> int:
    """M2 验收：「在哪里实现」的定位评测，题目从索引自动生成。"""
    from codeinsight.cognitive.embedding.siliconflow import SiliconFlowEmbedder
    from codeinsight.cognitive.retrieval.retriever import (
        ALL_LANES,
        RetrievalConfig,
        Retriever,
    )
    from codeinsight.eval.locator import format_report, generate_tasks, run_tasks
    from codeinsight.storage.sqlite import open_sqlite

    path = db_path(settings.data_dir)
    conn = open_sqlite(path, row_factory=True)
    try:
        row = conn.execute("SELECT id FROM project WHERE name = ?", (args.project,)).fetchone()
        if row is None:
            print(f"没有名为 {args.project} 的项目")
            return 1
        project_id = int(row[0])

        embedder = SiliconFlowEmbedder()
        lanes = frozenset(args.lanes.split(",")) & ALL_LANES
        retriever = Retriever(
            conn,
            embedder=embedder,
            db_path=path,
            config=RetrievalConfig(
                lanes=lanes,
                top_k=args.k,
                rrf_k=settings.retrieval_rrf_k,
                neighbor_depth=settings.retrieval_neighbor_depth,
            ),
        )

        for kind in args.kinds.split(","):
            tasks = generate_tasks(conn, project_id=project_id, n=args.n, kind=kind.strip())
            if not tasks:
                print(f"[{kind}] 没有可用的题目")
                continue
            results = run_tasks(
                conn, project_id=project_id, tasks=tasks, retriever=retriever, k=args.k
            )
            print()
            print(f"=== {kind} 题型（{len(tasks)} 题）===")
            print(format_report(results))
    finally:
        conn.close()
    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    """对项目提问（M3）：Agent 自己决定检索几次、要不要看调用关系。"""
    import asyncio

    from codeinsight.agent.service import ProjectNotFound, open_agent

    path = db_path(settings.data_dir)
    if not path.exists():
        print(f"索引库不存在：{path}（先跑 ci index）")
        return 1

    conversation_id = args.conversation or ""
    if not conversation_id:
        # 一次进程内的提问不共享会话；给个稳定的默认值方便看提示。
        conversation_id = "cli"

    try:
        session = open_agent(path, args.project)
    except (FileNotFoundError, ProjectNotFound) as exc:
        print(f"打不开项目：{exc}")
        return 1

    async def ask() -> int:
        streamed = False

        async def emit(event) -> None:
            nonlocal streamed
            if event.type == "delta":
                sys.stdout.write(event.data.get("text", ""))
                sys.stdout.flush()
                streamed = True
            elif event.type == "tool":
                if event.data.get("status") == "running":
                    print(f"\n  ⚙ {event.data.get('summary', '')}", flush=True)
            elif event.type == "error":
                print(
                    f"\n  ✗ {event.data.get('title', '出错')}"
                    f"（{event.data.get('hint', '')}）",
                    flush=True,
                )

        answer = await session.runtime.run(
            project_id=session.project_id,
            question=args.question,
            conversation_id=conversation_id,
            emit=emit,
        )
        if answer.error:
            return 1
        if streamed:
            print()
        if answer.abstained:
            print(f"\n[弃答] {answer.abstention_reason}")
        if answer.facts:
            print(f"\n事实（{len(answer.facts)} 条，均已校验位置）：")
            for fact in answer.facts:
                citation = fact.get("citation") or {}
                print(f"  · {fact['text']}  [{citation.get('path')}:{citation.get('lineno')}]")
        if answer.inferences:
            print(f"\n推断（{len(answer.inferences)} 条，未验证）：")
            for item in answer.inferences:
                print(f"  · {item['text']}")
        if answer.incomplete:
            print("\n[未完成] 达到轮次上限，没有收尾。")
        if answer.tools_used:
            print(f"\n调用工具：{', '.join(answer.tools_used)}")
        return 0

    try:
        return asyncio.run(ask())
    finally:
        session.close()


def _cmd_index(args: argparse.Namespace) -> int:
    """对一个仓库建索引（M1）。"""
    from codeinsight.cognitive.indexing.indexer import index_project

    path = db_path(settings.data_dir)
    result = index_project(
        path,
        root=Path(args.repo),
        name=args.name or Path(args.repo).name,
        ref=args.ref,
        max_chunk_lines=settings.max_chunk_lines,
        embed=args.embed,
        concepts_dir=Path(args.concepts) if args.concepts else None,
    )
    print(f"→ {path}")
    print(f"   project={result.project_name} @ {result.head_commit[:8]}")
    print(
        f"   files={result.files} modules={result.modules} symbols={result.symbols} "
        f"edges={result.edges}（解析到符号 {result.resolved_edges}）"
    )
    print(
        f"   chunks={result.chunks} entry_points={result.entry_points} "
        f"flows={result.flows} dependencies={result.dependencies} skipped={result.skipped}"
    )
    if args.embed:
        print(f"   向量 {result.embedded} 条")
    if args.concepts:
        print(f"   概念 {result.concepts} 个，实例 {result.concept_instances} 处")
    print(f"   用时 {result.elapsed_s:.2f}s")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ci", description="CodeInsight CLI")
    parser.add_argument("--version", action="version", version=f"CodeInsight {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init-db", help="建库建表")
    p.set_defaults(func=_cmd_init_db)

    p = sub.add_parser("where", help="显示本地路径")
    p.set_defaults(func=_cmd_where)

    p = sub.add_parser("dump-fixture", help="导出索引快照（B/C 线的开发数据源）")
    p.add_argument("--repo", required=True, help="仓库根目录")
    p.add_argument("--ref", default=None, help="git ref（缺省 HEAD）")
    p.add_argument("--name", default=None, help="项目显示名")
    p.add_argument("--out", default="fixtures/sample-index.json", help="输出文件")
    p.add_argument(
        "--max-modules",
        type=int,
        default=40,
        help="符号与边覆盖多少个模块（分层取样；0 = 全量）",
    )
    p.set_defaults(func=_cmd_dump_fixture)

    p = sub.add_parser("index", help="对仓库建索引")
    p.add_argument("--repo", required=True, help="仓库根目录")
    p.add_argument("--ref", default=None, help="git ref（缺省 HEAD）")
    p.add_argument("--name", default=None, help="项目显示名（缺省用目录名）")
    p.add_argument(
        "--embed",
        action="store_true",
        help="顺便算向量（要 CI_EMBEDDING_API_KEY；默认不跑，嵌入是唯一重的一步）",
    )
    p.add_argument(
        "--concepts",
        default=None,
        help="概念本体目录（如 knowledge/concepts）；给了就同步概念与实例",
    )
    p.set_defaults(func=_cmd_index)

    p = sub.add_parser("eval-locate", help="M2 验收：「在哪里实现」的定位评测")
    p.add_argument("--project", required=True, help="项目名")
    p.add_argument("-n", type=int, default=10, help="出多少题")
    p.add_argument("-k", type=int, default=settings.retrieval_top_k, help="看前多少条")
    p.add_argument(
        "--kinds",
        default="name,docstring",
        help="题型：name（知道名字）/ docstring（只知道描述）",
    )
    p.add_argument(
        "--lanes",
        default="bm25,symbol",
        help="开哪些通道，逗号分隔：bm25,dense,symbol,concept",
    )
    p.set_defaults(func=_cmd_eval_locate)

    p = sub.add_parser("ask", help="对项目提问（Agent 自己决定检索与追踪方式）")
    p.add_argument("question", help="问题")
    p.add_argument("--project", required=True, help="项目名")
    p.add_argument(
        "--conversation",
        default="",
        help="会话 id：同一个 id = 连续追问（源文档 §2.3-5）",
    )
    p.set_defaults(func=_cmd_ask)

    p = sub.add_parser("search", help="检索：问一句「X 在哪」")
    p.add_argument("query", help="查询")
    p.add_argument("--project", required=True, help="项目名")
    p.add_argument(
        "--lanes",
        default="bm25,symbol",
        help="开哪些通道，逗号分隔：bm25,dense,symbol,concept",
    )
    p.add_argument("-k", type=int, default=settings.retrieval_top_k, help="返回多少条")
    p.set_defaults(func=_cmd_search)

    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK——中文和 ✓ 都会直接抛 UnicodeEncodeError。
    # 统一在入口把输出流改成 UTF-8：编码问题不该由每个子命令各自处理。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover —— 非 TextIOWrapper
            pass

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
