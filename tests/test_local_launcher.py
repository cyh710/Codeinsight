"""真实子进程离线验证：端口冲突、重复双击及服务退出边界。"""

from __future__ import annotations

import json
import os
import runpy
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts/launch.py"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="需要本机 Node.js")


def test_default_backend_skips_foreign_service_and_frontend_port(tmp_path: Path, monkeypatch):
    select = runpy.run_path(str(LAUNCHER))["select_backend_port"]
    monkeypatch.setitem(select.__globals__, "port_busy", lambda port: port == 8020)
    monkeypatch.setitem(select.__globals__, "backend_ready", lambda *_: False)
    assert select(8020, tmp_path, automatic=True) == (8021, False)
    assert select(8020, tmp_path, automatic=True, excluded_port=8021) == (8022, False)
    with pytest.raises(RuntimeError, match="占用"):
        select(8020, tmp_path, automatic=False)


def test_default_backend_reuses_matching_service_without_starting_another(
    tmp_path: Path, monkeypatch
):
    select = runpy.run_path(str(LAUNCHER))["select_backend_port"]
    monkeypatch.setitem(select.__globals__, "port_busy", lambda port: port in (8020, 8021))
    monkeypatch.setitem(select.__globals__, "backend_ready", lambda url, _: url.endswith(":8021"))
    assert select(8020, tmp_path, automatic=True) == (8021, True)


def test_backend_fallback_stops_after_bounded_range(tmp_path: Path, monkeypatch):
    select = runpy.run_path(str(LAUNCHER))["select_backend_port"]
    monkeypatch.setitem(select.__globals__, "port_busy", lambda _: True)
    monkeypatch.setitem(select.__globals__, "backend_ready", lambda *_: False)
    with pytest.raises(RuntimeError, match="未找到"):
        select(8020, tmp_path, automatic=True)


@contextmanager
def reserved_ports():
    """同时预留两个不同端口；调用方在启动服务前释放。"""
    with socket.socket() as backend, socket.socket() as frontend:
        backend.bind(("127.0.0.1", 0))
        frontend.bind(("127.0.0.1", 0))
        yield backend, frontend


def command(backend: int, frontend: int, *extra: str) -> list[str]:
    return [
        sys.executable,
        "-u",
        str(LAUNCHER),
        "--no-browser",
        "--backend-port",
        str(backend),
        "--frontend-port",
        str(frontend),
        *extra,
    ]


def environment(tmp_path: Path) -> dict[str, str]:
    return {
        **os.environ,
        "CI_DATA_DIR": str(tmp_path / "data"),
        "PYTHONUTF8": "1",
        "CI_LLM_API_KEY": "",
        "CI_EMBEDDING_API_KEY": "",
    }


def test_launcher_dependency_check_does_not_create_database(tmp_path: Path):
    result = subprocess.run(
        command(8020, 5173, "--check"),
        env=environment(tmp_path),
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Python：" in result.stdout
    assert not (tmp_path / "data").exists()


def test_launcher_rejects_occupied_port_without_modifying_data(tmp_path: Path):
    with reserved_ports() as (backend, frontend):
        backend.listen()
        result = subprocess.run(
            command(backend.getsockname()[1], frontend.getsockname()[1]),
            env=environment(tmp_path),
            capture_output=True,
            encoding="utf-8",
            timeout=30,
        )
        assert result.returncode == 1
        assert "占用" in result.stderr
        assert backend.fileno() != -1
        assert not (tmp_path / "data").exists()


@pytest.mark.skipif(
    not (ROOT / "frontend/node_modules/vite/bin/vite.js").exists(),
    reason="离线冒烟需要已安装的前端依赖；测试不下载依赖",
)
def test_launcher_real_services_duplicate_and_cleanup(tmp_path: Path):
    with reserved_ports() as (backend, frontend):
        backend_port, frontend_port = backend.getsockname()[1], frontend.getsockname()[1]
    env = environment(tmp_path)
    output = tmp_path / "launcher.log"
    with output.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command(backend_port, frontend_port, "--run-seconds", "12"),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 70
            while "工作台已就绪" not in output.read_text(encoding="utf-8"):
                assert process.poll() is None, output.read_text(encoding="utf-8")
                assert time.monotonic() < deadline, output.read_text(encoding="utf-8")
                time.sleep(0.1)
            http = build_opener(ProxyHandler({}))
            with http.open(f"http://127.0.0.1:{frontend_port}/api/health", timeout=3) as response:
                health = json.load(response)
            assert health["schema_applied"] is True
            assert Path(health["db_path"]).parent == tmp_path / "data"

            duplicate = subprocess.run(
                command(backend_port, frontend_port),
                env=env,
                capture_output=True,
                encoding="utf-8",
                timeout=10,
            )
            assert duplicate.returncode == 0, duplicate.stderr
            assert "另一个窗口" in duplicate.stdout
            assert process.poll() is None

            with socket.socket() as extra_frontend:
                extra_frontend.bind(("127.0.0.1", 0))
                extra_port = extra_frontend.getsockname()[1]
            reused = subprocess.run(
                command(backend_port, extra_port, "--run-seconds", "0.5"),
                env=env,
                capture_output=True,
                encoding="utf-8",
                timeout=15,
            )
            assert reused.returncode == 0, reused.stdout + reused.stderr
            assert "后端：复用已有服务" in reused.stdout
            with http.open(f"http://127.0.0.1:{backend_port}/health", timeout=3) as response:
                assert json.load(response)["status"] == "ok"
            assert process.wait(timeout=20) == 0, output.read_text(encoding="utf-8")
        finally:
            if process.poll() is None:
                # 仅在验收失败时清理测试自建的进程树，不触及实际工作台。
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )
                else:
                    process.terminate()
                process.wait(timeout=10)
    for port in (backend_port, frontend_port):
        with socket.socket() as connection:
            connection.settimeout(1)
            assert connection.connect_ex(("127.0.0.1", port)) != 0


@pytest.mark.skipif(os.name != "nt", reason="Windows BAT 入口")
def test_windows_double_click_entry_from_other_directory(tmp_path: Path):
    result = subprocess.run(
        f'cmd.exe /d /s /c ""{ROOT / "启动 CodeInsight.bat"}" --check"',
        cwd=tmp_path,
        env=environment(tmp_path),
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        input="\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Python：" in result.stdout
    assert "not recognized" not in result.stderr
    assert not (tmp_path / "data").exists()
