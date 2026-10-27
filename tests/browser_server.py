"""浏览器测试专用后端：临时 Git/SQLite、真实 API、假 Provider，固定本机端口。"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uvicorn

from codeinsight.api import knowledge, query
from codeinsight.api.app import create_app
from codeinsight.cognitive.concepts.assets import knowledge_directory
from codeinsight.cognitive.indexing.indexer import index_project
from codeinsight.config import settings
from codeinsight.llm.provider import StreamChunk, ToolCall
from codeinsight.storage.sqlite import db_path


class BrowserProvider:
    model_id = "offline-browser-fixture"

    async def stream_with_tools(self, system, messages, tools, **kwargs):
        if any(
            "__fixture_fail_provider__" in str(m.get("content", ""))
            for m in messages
            if m["role"] == "user"
        ):
            raise RuntimeError("浏览器测试中的 Provider 故障")
        question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        original_question = question.splitlines()[0]
        recent = messages[
            next(i for i in range(len(messages) - 1, -1, -1) if messages[i]["role"] == "user") :
        ]
        if "__fixture_workspace__" in original_question:
            if not any(message["role"] == "tool" for message in recent):
                yield StreamChunk(
                    tool_calls=[
                        ToolCall(
                            "workspace-search",
                            "search_files",
                            {"query": "MRR", "path": "experiments"},
                        )
                    ]
                )
            else:
                yield StreamChunk(
                    text="新增实验记录的MRR为0.75 [experiments/score_output.txt:1]。这次直接阅读当前文件，无需更新索引。",
                    finish_reason="stop",
                )
            return
        if "__fixture_understanding_sparse__" in original_question:
            if not any(message["role"] == "tool" for message in recent):
                yield StreamChunk(
                    tool_calls=[
                        ToolCall(
                            "sparse",
                            "read_file",
                            {"path": "store.py", "start_line": 1, "end_line": 6},
                        )
                    ]
                )
            else:
                yield StreamChunk(
                    text="保存操作接收一个值，再交给数据库写入。\n\n先理解这个值怎样流动，再比较实现的取舍。当前材料没有可比较的实验成绩，暂时不能排高低。",
                    finish_reason="stop",
                )
            return
        if "__fixture_reply_rendering__" in original_question:
            path = "wattbot-nlp/src/dense/hybrid.py"
            if not any(message["role"] == "tool" for message in recent):
                yield StreamChunk(
                    tool_calls=[
                        ToolCall(
                            "render-read",
                            "read_file",
                            {
                                "path": path,
                                "start_line": 19,
                                "end_line": 23,
                            },
                        )
                    ]
                )
            else:
                yield StreamChunk(
                    text=(
                        "## 先看一次查询怎样流动\n\n"
                        "这个演示函数先拆分问题，再按分数排序。"
                        f" [{path}:19-23]\n\n"
                        "它把一次查询拆成三个动作：\n\n"
                        "1. 读取输入，把文本分成词。\n2. 组装两组演示分数。\n3. 按分数排序并返回名称。\n\n"
                        "### 输入和输出放在一起看\n\n"
                        "| 步骤 | 输入 | 输出 |\n|---|---|---|\n"
                        "| 拆分 | 保存 结果 | 两个词 |\n| 排序 | 演示分数 | 名称列表 |\n\n"
                        "下面这段代码可以逐行阅读：\n\n"
                        '```python\nquery = "保存 结果"\nterms = query.split()\nprint(terms)\n```\n\n'
                        "> 这些分数只用来演示数据流动，不是检索性能成绩。"
                    ),
                    finish_reason="stop",
                )
            return
        if "__fixture_preserve_body__" in original_question:
            if not any(message["role"] == "tool" for message in recent):
                yield StreamChunk(
                    text="我先查资料。",
                    tool_calls=[
                        ToolCall(
                            "body-read",
                            "read_file",
                            {"path": "store.py", "start_line": 1, "end_line": 6},
                        )
                    ],
                )
            elif not any(
                call.get("function", {}).get("name") == "propose_exploration"
                for message in recent
                for call in message.get("tool_calls", [])
            ):
                yield StreamChunk(
                    text="## 已有策略\n\n保存操作从 save 进入。 [store.py:3]\n\n"
                    "| 核对对象 | 位置 |\n|---|---|\n| 保存 | save |\n\n"
                    "```py\nvalue = 1\n```",
                    tool_calls=[
                        ToolCall(
                            "body-action",
                            "propose_exploration",
                            {
                                "takeaways": ["保存操作从 save 进入。"],
                                "actions": [
                                    {
                                        "kind": "follow_up",
                                        "label": "继续比较保存方式",
                                        "question": "怎样比较保存方式？",
                                        "reason": "核对不同实现",
                                        "target": {"kind": "code", "path": "store.py", "lineno": 3},
                                    }
                                ],
                            },
                        )
                    ],
                )
            else:
                yield StreamChunk(text="补充：还可以对比另一种实现。", finish_reason="stop")
            return
        if "__fixture_long_analysis__" in original_question:
            count = sum(message["role"] == "tool" for message in recent)
            if count < 12:
                yield StreamChunk(
                    tool_calls=[
                        ToolCall(
                            f"long-read-{count}",
                            "read_file",
                            {"path": "store.py", "start_line": 1, "end_line": 6}
                            if count == 0
                            else {"path": "large.py", "start_line": count, "end_line": count},
                        )
                    ]
                )
            else:
                yield StreamChunk(
                    text="核对已完成：保存操作从 save 进入。 [store.py:3]", finish_reason="stop"
                )
            return
        if "__fixture_review_unchecked__" in original_question:
            yield StreamChunk(text="先把它想成一个收件窗口，具体实现还需要核对。")
            await asyncio.sleep(0.3)
            yield StreamChunk(text=" 我猜入口在 [ghost.py:99]。", finish_reason="stop")
            return
        if "__fixture_review_code__" in original_question or original_question == "听不懂":
            read = any(m["role"] == "tool" for m in recent)
            if not read and "__fixture_review_code__" in original_question:
                yield StreamChunk(
                    tool_calls=[
                        ToolCall(
                            "review-read",
                            "read_file",
                            {"path": "store.py", "start_line": 1, "end_line": 6},
                        )
                    ]
                )
                return
            text = (
                "把提交想成按下保存键：修改在提交后完成。 [store.py:6]"
                if read
                else "你希望我重新解释哪一段？"
            )
            yield StreamChunk(text=text, finish_reason="stop")
            return
        exploring = "核对实现，再讨论取舍" in question or question.startswith("SQL 如果没有提交")
        if exploring:
            recent = messages[
                next(i for i in range(len(messages) - 1, -1, -1) if messages[i]["role"] == "user") :
            ]
            proposed = any(
                call.get("function", {}).get("name") == "propose_exploration"
                for m in recent
                for call in m.get("tool_calls", [])
            )
            if not proposed:
                yield StreamChunk(
                    tool_calls=[
                        ToolCall(
                            "explore-read",
                            "read_file",
                            {"path": "store.py", "start_line": 1, "end_line": 6},
                        ),
                        ToolCall(
                            "explore-plan",
                            "propose_exploration",
                            {
                                "takeaways": ["写入先开启事务，提交后修改才完成。"],
                                "actions": [
                                    {
                                        "kind": "follow_up",
                                        "label": "如果不提交会怎样",
                                        "reason": "比较写入与持久化的边界",
                                        "question": "SQL 如果没有提交事务，刷新后还能读到吗？",
                                        "target": {"kind": "code", "path": "store.py", "lineno": 3},
                                    },
                                    {
                                        "kind": "knowledge",
                                        "label": "理解事务的提交与回滚",
                                        "reason": "只阅读与当前问题相关的章节",
                                        "target": {
                                            "kind": "knowledge",
                                            "topic_id": "sql-transactions",
                                            "section_id": "two-writes",
                                        },
                                    },
                                    {
                                        "kind": "graph",
                                        "label": "谁会调用这段保存逻辑",
                                        "reason": "回到局部关系核对调用者",
                                        "target": {
                                            "kind": "code",
                                            "path": "store.py",
                                            "qualname": "store.save",
                                        },
                                    },
                                ],
                                "flow": {
                                    "title": "保存逻辑所在的代码结构",
                                    "nodes": [
                                        {
                                            "id": "module",
                                            "label": "存储模块",
                                            "role": "组织数据库写入",
                                            "target": {"qualname": "store"},
                                        },
                                        {
                                            "id": "save",
                                            "label": "保存函数",
                                            "role": "开启事务、写入并提交",
                                            "target": {"qualname": "store.save"},
                                        },
                                    ],
                                    "edges": [{"source": "module", "target": "save"}],
                                },
                            },
                        ),
                    ]
                )
                return
            yield StreamChunk(
                text="写入先开启事务，提交后修改才完成。[store.py:4] 这里的关键是把多步修改放在同一事务边界内，而不是每写一句就当作已经持久化。[store.py:6] 可以对照[事务](/learn/sql-transactions#two-writes)继续理解提交与回滚。",
                finish_reason="stop",
            )
            return
        if not question.startswith("SQL 是什么") and any(
            m["role"] == "tool" and "store.py" in m.get("content", "") for m in messages
        ):
            text = "这个位置开启事务，随后提交修改 [store.py:4]。"
        else:
            text = "[SQL](/learn/sql-database) 是查询和管理数据的语言。“表”组织数据，SELECT 读取需要的记录。以下为教学说明，项目实现需要另外核对代码。"
        if "__fixture_long__" in question:
            text = "\n\n".join(
                [
                    f"第 {number} 段：SQL 是查询数据库的语言。这段教学说明用于验证长回答的阅读位置，"
                    + "读懂数据库需要逐步理解表、记录与查询。" * 6
                    for number in range(24)
                ]
            )
        yield StreamChunk(text=text[:17])
        await asyncio.sleep(
            20
            if "__fixture_cancel__" in question
            else 4
            if "__fixture_slow__" in question
            else 0.35
        )
        yield StreamChunk(text=text[17:], finish_reason="stop")

    async def complete(self, *args, **kwargs):
        raise RuntimeError("测试深度解释降级")


def main() -> None:
    """临时数据不接触现有索引库；不读取任何密钥用于模型调用。"""
    with tempfile.TemporaryDirectory(prefix="codeinsight-browser-") as directory:
        base = Path(directory)
        settings.data_dir = base / "data"
        settings.embedding_api_key = ""
        settings.llm_api_key = ""
        for name in ("example-main", "example-other"):
            root = base / name
            root.mkdir()
            (root / "README.md").write_text(
                f"# {name}\n\n这是一个用于探索数据库保存过程的离线示例项目。它通过 SQLite 事务保存数据，帮助核对写入、提交与页面所见之间的区别。\n",
                encoding="utf-8",
            )
            (root / "store.py").write_text(
                'import sqlite3\n\ndef save(conn):\n    conn.execute("BEGIN")\n    conn.execute("INSERT INTO items VALUES (1)")\n    conn.commit()\n',
                encoding="utf-8",
            )
            (root / "large.py").write_text(
                "# 分页阅读夹具\n" * 450 + 'message = "中文😀"\n', encoding="utf-8"
            )
            nested = root / "wattbot-nlp/src/dense/hybrid.py"
            nested.parent.mkdir(parents=True)
            nested.write_text(
                "# 引用跳转夹具\n" * 18
                + (
                    "def hybrid_search(query):\n"
                    "    terms = query.split()\n"
                    "    scores = {'bm25': len(terms), 'dense': 0.8}\n"
                    "    ranking = sorted(scores, key=scores.get, reverse=True)\n"
                    "    return ranking\n"
                ),
                encoding="utf-8",
            )
            subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "-c",
                    "user.name=fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "commit",
                    "-m",
                    "fixture",
                ],
                check=True,
                capture_output=True,
            )
            index_project(
                db_path(settings.data_dir),
                root=root,
                name=name,
                ref="HEAD",
                concepts_dir=knowledge_directory("concepts"),
            )
        query.set_provider_factory(BrowserProvider)
        knowledge._PROVIDER_FACTORY = BrowserProvider
        uvicorn.run(create_app(), host="127.0.0.1", port=18021, log_level="warning")


if __name__ == "__main__":
    main()
