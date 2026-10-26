"""固定提交离线验收：临时索引、真实源码工具、脚本化回答；不接触用户索引。"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import subprocess
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from codeinsight.agent.discovery import discover
from codeinsight.agent.service import open_agent
from codeinsight.cognitive.indexing.indexer import index_project
from codeinsight.cognitive.indexing.scanner import read_blobs
from codeinsight.llm.provider import StreamChunk, ToolCall
from codeinsight.storage.sqlite import open_sqlite

SCANNER = "src/codeinsight/cognitive/indexing/scanner.py"
MODULE = "src.codeinsight.cognitive.indexing.scanner"


class OfflineProvider:
    """答案写死用于工程验收，不能作为真实模型的理解效果证明。"""

    model_id = "offline-fixed-snapshot"

    def __init__(self, lines: dict[str, int]):
        self.lines = lines

    async def stream_with_tools(self, system, messages, tools, **kwargs):
        current = messages[
            next(i for i in range(len(messages) - 1, -1, -1) if messages[i]["role"] == "user") :
        ]
        if not any(m["role"] == "tool" for m in current):
            calls = [
                ToolCall(
                    f"read-{name}",
                    "read_file",
                    {"path": SCANNER, "start_line": line, "end_line": line + 55},
                )
                for name, line in self.lines.items()
            ]
            calls.append(
                ToolCall(
                    "explore",
                    "propose_exploration",
                    {
                        "takeaways": ["Git 项目读取提交快照，未提交修改不会立即进入索引。"],
                        "actions": [
                            {
                                "kind": "follow_up",
                                "label": "比较支持工作区需要处理的版本问题",
                                "reason": "理解引用稳定性与更新及时性的取舍",
                                "question": "假设要支持未提交工作区，应如何处理版本与过期引用？",
                            },
                            {
                                "kind": "code",
                                "label": "查看扫描分支",
                                "reason": "核对 Git 与本地目录的区别",
                                "target": {
                                    "path": SCANNER,
                                    "lineno": self.lines["list_repo_files"],
                                },
                            },
                        ],
                        "flow": {
                            "title": "扫描入口与 Git 文件树读取的静态调用",
                            "nodes": [
                                {
                                    "id": name,
                                    "label": name,
                                    "role": role,
                                    "target": {"qualname": f"{MODULE}.{name}"},
                                }
                                for name, role in [
                                    ("list_repo_files", "选择 Git 或本地目录路径"),
                                    ("_git_ls_tree", "读取指定提交的文件树"),
                                ]
                            ],
                            "edges": [{"source": "list_repo_files", "target": "_git_ls_tree"}],
                        },
                    },
                )
            )
            yield StreamChunk(tool_calls=calls)
        else:
            yield StreamChunk(
                text=(
                    "Git 项目读取提交快照，未提交修改不会立即进入索引。"
                    f" [{SCANNER}:{self.lines['list_repo_files']}]\n\n"
                    "扫描器把 ref（缺省 HEAD）传给 git ls-tree，因此读取的是确定的文件树。"
                    f" [{SCANNER}:{self.lines['_git_ls_tree']}]\n\n"
                    "这让引用可以绑定版本，代价是未提交修改不能立刻参与解释。"
                    "没有 .git 的本地目录则走文件系统退路，不能笼统宣称所有项目只读 Git。"
                    f" [{SCANNER}:{self.lines['list_repo_files']}]"
                ),
                finish_reason="stop",
            )


def main() -> None:
    """临时数据库连接全部释放后清理；--output 保留可审查的原始结果。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="9b927e8")
    parser.add_argument(
        "--output", type=Path, default=Path(".ci/project-exploration-fixed-review.json")
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    ref = subprocess.run(
        ["git", "rev-parse", args.ref], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    source = read_blobs(root, ref, [SCANNER])[SCANNER].decode("utf-8")
    lines = {
        name: next(
            i for i, line in enumerate(source.splitlines(), 1) if line.startswith(f"def {name}(")
        )
        for name in ("list_repo_files", "_git_ls_tree")
    }
    with TemporaryDirectory(prefix="ci-exploration-review-") as temporary:
        database = Path(temporary) / "review.sqlite"
        try:
            index_project(
                database,
                root=root,
                name="CodeInsight-fixed",
                ref=ref,
                embed=False,
                concepts_dir=root / "knowledge" / "concepts",
            )
            with closing(open_sqlite(database, row_factory=True)) as conn:
                overview = discover(conn, 1)
                counts = {
                    table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in ("file", "symbol", "edge")
                }
            assert overview["head_commit"] == ref and overview["project_intro"]
            assert 1 <= len(overview["exploration_entries"]) <= 4
            session = open_agent(
                database,
                1,
                provider=OfflineProvider(lines),
                lanes=frozenset({"bm25", "symbol", "concept"}),
            )
            try:
                answer = asyncio.run(
                    session.runtime.run(
                        project_id=1,
                        question="为什么 Git 项目刚修改的代码还没有进入索引？请区分非 Git 目录。",
                    )
                )
            finally:
                session.close()
            assert not answer.error and not answer.abstained
            assert answer.exploration["flow"]["edges"]
            assert len(answer.exploration["actions"]) == 2
            assert any(c.path == SCANNER for c in answer.citations)
            result = {
                "ref": ref,
                "counts": counts,
                "intro_source": overview["project_intro"]["source"],
                "entries": overview["exploration_entries"],
                "answer": asdict(answer),
                "real_model_calls": 0,
                "validation": "scripted_provider",
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(
                json.dumps(
                    {
                        "ref": ref,
                        "counts": counts,
                        "entries": len(overview["exploration_entries"]),
                        "real_model_calls": 0,
                        "output": str(args.output),
                    },
                    ensure_ascii=False,
                )
            )
        finally:
            # sqlite 连接可能被内部事务/游标引用成环，Windows 删除前先释放这些已失去引用的对象。
            gc.collect()


if __name__ == "__main__":
    main()
