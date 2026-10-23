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

from codeinsight import __version__
from codeinsight.config import settings
from codeinsight.storage.sqlite import apply_schema, db_path, open_sqlite


def _cmd_init_db(args: argparse.Namespace) -> int:
    path = db_path(settings.data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open_sqlite(path) as conn:
        apply_schema(conn)
    print(f"schema applied → {path}")
    return 0


def _cmd_where(args: argparse.Namespace) -> int:
    print(f"db_path = {db_path(settings.data_dir)}")
    print(f"data_dir = {settings.data_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ci", description="CodeInsight CLI")
    parser.add_argument("--version", action="version", version=f"CodeInsight {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init-db", help="建库建表")
    p.set_defaults(func=_cmd_init_db)

    p = sub.add_parser("where", help="显示本地路径")
    p.set_defaults(func=_cmd_where)

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
