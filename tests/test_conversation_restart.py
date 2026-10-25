"""真实启动两个独立后端进程，验证恢复不是全局内存产生的假象。"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from codeinsight.storage.sqlite import db_path, open_sqlite


def test_real_process_restart_keeps_history_and_interrupts_partial_turn(data_dir):
    with open_sqlite(db_path(data_dir)) as conn:
        conn.execute(
            "INSERT INTO project(id,name,root_path) VALUES(1,'restart-fixture','unavailable')"
        )
        conn.commit()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    def request(path, body=None):
        req = urllib.request.Request(
            base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        return urllib.request.urlopen(req, timeout=35)

    def start():
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).with_name("restart_server.py")),
                str(data_dir),
                str(port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError("离线重启测试服务未能启动")
            try:
                with request("/health"):
                    return process
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.1)
        process.kill()
        process.wait()
        raise AssertionError("离线测试服务启动超时")

    process = start()
    try:
        with request("/projects/1/conversations", {}) as response:
            cid = json.load(response)["id"]
        common = {"project_id": 1, "conversation_id": cid}
        with request(
            "/query", {**common, "request_id": "first", "question": "SQL 是什么"}
        ) as response:
            assert json.load(response)["knowledge_sources"]
        with request(
            "/query/stream",
            {**common, "request_id": "partial", "question": "SQL __wait_for_restart__"},
        ) as stream:
            for _ in range(30):
                if stream.readline().startswith(b"event: delta"):
                    break
            else:
                raise AssertionError("没有收到离线增量")
            process.kill()
            process.wait(timeout=10)
        process = start()
        with request(f"/projects/1/conversations/{cid}/turns") as response:
            turns = json.load(response)["items"]
        assert turns[0]["status"] == "completed"
        assert turns[1]["status"] == "interrupted"
        assert turns[1]["answer"]["text"] == "SQL 是查询数据库的语言。"
        with request(
            "/query", {**common, "request_id": "after", "question": "SQL 再解释一下"}
        ) as response:
            assert json.load(response)["text"]
        messages = json.loads((data_dir / "provider-messages.json").read_text(encoding="utf-8"))
        assert any(m["role"] == "assistant" and "SQL" in m["content"] for m in messages)
        assert not any("__wait_for_restart__" in str(m.get("content")) for m in messages)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
