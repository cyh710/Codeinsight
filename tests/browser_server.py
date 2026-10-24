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
from codeinsight.llm.provider import StreamChunk
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
        if not question.startswith("SQL 是什么") and any(
            m["role"] == "tool" and "store.py" in m.get("content", "") for m in messages
        ):
            text = "这个位置开启事务，随后提交修改 [store.py:4]。"
        else:
            text = "[SQL](/learn/sql-database) 是查询和管理数据的语言。“表”组织数据，SELECT 读取需要的记录。以下为教学说明，项目实现需要另外核对代码。"
        yield StreamChunk(text=text[:17])
        await asyncio.sleep(0.35)
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
            (root / "store.py").write_text(
                'import sqlite3\n\ndef save(conn):\n    conn.execute("BEGIN")\n    conn.execute("INSERT INTO items VALUES (1)")\n    conn.commit()\n',
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
