"""CodeInsight 命令行入口。

子命令按里程碑接入：

    ci init-db                 建库建表
    ci import --repo <path>    导入仓库并建索引      (M1)
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
