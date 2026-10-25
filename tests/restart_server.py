"""进程重启验收专用服务；仅使用临时数据和脚本 Provider。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uvicorn

from codeinsight.api import query
from codeinsight.api.app import create_app
from codeinsight.config import settings
from codeinsight.llm.provider import StreamChunk


class RestartProvider:
    model_id = "offline-restart-fixture"

    async def stream_with_tools(self, system, messages, tools, **kwargs):
        (settings.data_dir / "provider-messages.json").write_text(
            json.dumps(messages, ensure_ascii=False), encoding="utf-8"
        )
        yield StreamChunk(text="SQL 是查询数据库的语言。")
        if any(
            "__wait_for_restart__" in str(m.get("content", ""))
            for m in messages
            if m["role"] == "user"
        ):
            await asyncio.sleep(120)
        yield StreamChunk(finish_reason="stop")


if __name__ == "__main__":
    settings.data_dir = Path(sys.argv[1])
    settings.llm_api_key = ""
    settings.embedding_api_key = ""
    query.set_provider_factory(RestartProvider)
    uvicorn.run(create_app(), host="127.0.0.1", port=int(sys.argv[2]), log_level="error")
