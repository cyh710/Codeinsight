"""本地工作台启动器：只管理本次创建的进程，不接管已有服务。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from typing import BinaryIO
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
HTTP = build_opener(ProxyHandler({}))


def read_url(url: str) -> bytes:
    """只访问调用方提供的本地 URL，避免系统代理截走回环请求。"""
    with HTTP.open(url, timeout=2) as response:
        return response.read()


def read_json(url: str) -> dict:
    """HTTP 错误、非 JSON 和非对象响应统一作为未就绪处理。"""
    try:
        value = json.loads(read_url(url))
        return value if isinstance(value, dict) else {}
    except (OSError, URLError, ValueError):
        return {}


def port_busy(port: int) -> bool:
    """探测实际回环地址；不依赖 PID 或进程名推断服务身份。"""
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def backend_ready(url: str, data_dir: Path) -> bool:
    """只有产品名、健康状态和数据目录一致才允许复用后端。"""
    root = read_json(url + "/")
    directory = root.get("data_dir")
    return (
        root.get("name") == "CodeInsight"
        and isinstance(directory, str)
        and Path(directory).is_absolute()
        and Path(directory).resolve() == data_dir
        and read_json(url + "/health").get("status") == "ok"
    )


def require_current_backend(url: str) -> None:
    """同数据目录不代表代码一致；不静默复用旧进程，也不代用户杀进程。"""
    from codeinsight.runtime_version import current_revision

    info = read_json(url + "/")
    if info.get("runtime_revision") != current_revision() or info.get("restart_required"):
        raise RuntimeError(
            "后端代码已更新或已有服务版本无法确认。请在原启动窗口按 Ctrl+C 停止旧服务，再重新运行启动器；旧服务不会被自动结束。"
        )


def select_backend_port(
    preferred: int, data_dir: Path, *, automatic: bool, excluded_port: int | None = None
) -> tuple[int, bool]:
    """默认端口冲突时寻找空闲端口；显式指定端口保持严格，不接管其他程序。"""
    candidates = range(preferred, min(preferred + 40, 65536)) if automatic else [preferred]
    for port in candidates:
        if port == excluded_port:
            continue
        if not port_busy(port):
            return port, False
        if backend_ready(f"http://127.0.0.1:{port}", data_dir):
            require_current_backend(f"http://127.0.0.1:{port}")
            return port, True
        if not automatic:
            raise RuntimeError(
                f"端口 {port} 已被占用，无法确认是当前数据目录的 CodeInsight。"
                "请去掉 --backend-port 让启动器自动选择端口，或指定其他空闲端口。"
            )
    raise RuntimeError("未找到可用的后端端口，请通过 --backend-port 指定空闲端口。")


def frontend_ready(url: str, data_dir: Path) -> bool:
    """前端必须是 CodeInsight 的 Vite 页面，且代理指向本次数据目录。"""
    try:
        html = read_url(url).decode("utf-8")
        read_url(url + "/@vite/client")
        info = read_json(url + "/api/")
        directory = info.get("data_dir")
        return (
            "<title>CodeInsight - 代码理解工作台</title>" in html
            and info.get("name") == "CodeInsight"
            and isinstance(directory, str)
            and Path(directory).is_absolute()
            and Path(directory).resolve() == data_dir
        )
    except (OSError, URLError, UnicodeError):
        return False


def stop_owned(process: subprocess.Popen) -> None:
    """只清理仍存活的直接子进程及其子树，绝不按端口或进程名结束程序。"""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        # POSIX 子进程独立会话，清理 Vite 的 esbuild 子进程而不影响当前终端。
        import signal

        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def spawn(
    stack: ExitStack, command: list[str], cwd: Path, env: dict[str, str], log_path: Path
) -> subprocess.Popen:
    """日志和进程绑定同一个退出栈；失败时先结束子进程再关闭日志。"""
    log = stack.enter_context(log_path.open("wb"))
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )
    stack.callback(stop_owned, process)
    return process


def wait_ready(check: Callable[[], bool], process: subprocess.Popen, label: str, log: Path) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{label}提前退出。请查看日志：{log}")
        if check():
            return
        time.sleep(0.3)
    raise RuntimeError(f"{label}在 60 秒内未就绪。请查看日志：{log}")


def lock_launcher(stack: ExitStack, path: Path) -> bool:
    """用操作系统锁阻止双击竞争；进程退出后锁自动释放。"""
    handle: BinaryIO = stack.enter_context(path.open("a+b"))
    if path.stat().st_size == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def main() -> int:
    """启动真实本地服务，不发起模型请求；Ctrl+C 仅停止本次启动的服务。"""
    parser = argparse.ArgumentParser(description="启动 CodeInsight 本地工作台")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--check", action="store_true", help="仅检查依赖，不启动服务")
    parser.add_argument(
        "--backend-port", type=int, help="固定后端端口；默认从 8020 自动寻找可用端口"
    )
    parser.add_argument("--frontend-port", type=int, default=5173)
    parser.add_argument("--run-seconds", type=float, help="就绪后运行指定秒数，用于离线冒烟")
    args = parser.parse_args()
    preferred_backend = args.backend_port if args.backend_port is not None else 8020
    if not (1 <= preferred_backend <= 65535 and 1 <= args.frontend_port <= 65535):
        parser.error("端口必须位于 1–65535")
    if preferred_backend == args.frontend_port:
        parser.error("前后端端口不能相同")
    if args.run_seconds is not None and args.run_seconds <= 0:
        parser.error("运行时间必须大于 0")

    os.chdir(ROOT)
    try:
        from codeinsight.config import settings
        from codeinsight.storage.sqlite import db_path, ensure_schema
    except ImportError as error:
        raise RuntimeError(
            "Python 依赖不完整，请先在根目录运行 uv sync --locked --extra dev"
        ) from error
    node = shutil.which("node")
    if not node:
        raise RuntimeError("未找到 Node.js，请安装 Node.js 24 LTS 后重试。")
    vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
    print(f"CodeInsight · {ROOT}")
    if args.check:
        print(
            f"Python：{sys.version.split()[0]}\nNode：{subprocess.check_output([node, '--version'], text=True).strip()}"
        )
        print("前端依赖：" + ("已安装" if vite.exists() else "缺少，启动时将执行 npm ci"))
        print(f"数据目录：{settings.data_dir.resolve()}")
        return 0

    frontend_url = f"http://127.0.0.1:{args.frontend_port}"
    data_dir = settings.data_dir.resolve()
    log_dir = ROOT / ".ci/launcher"
    log_dir.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        if not lock_launcher(stack, log_dir / f"{preferred_backend}-{args.frontend_port}.lock"):
            if frontend_ready(frontend_url, data_dir):
                require_current_backend(frontend_url + "/api")
            print(f"启动器已在另一个窗口运行。工作台：{frontend_url}")
            if not args.no_browser and frontend_ready(frontend_url, data_dir):
                webbrowser.open(frontend_url)
            return 0

        # 先检查两个端口，避免在发现冲突前修改数据库或安装依赖。
        backend_port, reuse_backend = select_backend_port(
            preferred_backend,
            data_dir,
            automatic=args.backend_port is None,
            excluded_port=args.frontend_port,
        )
        backend_url = f"http://127.0.0.1:{backend_port}"
        if backend_port != preferred_backend:
            print(f"后端端口 {preferred_backend} 已被占用，自动改用 {backend_port}。")
        reuse_frontend = port_busy(args.frontend_port)
        if reuse_frontend and not frontend_ready(frontend_url, data_dir):
            raise RuntimeError(f"端口 {args.frontend_port} 已被其他服务占用，或其后端代理不匹配。")

        if not vite.exists():
            npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
            if not npm:
                raise RuntimeError("未找到 npm，请重新安装 Node.js 24 LTS。")
            print("正在安装前端依赖（首次运行需要网络）……")
            subprocess.run([npm, "ci"], cwd=ROOT / "frontend", check=True)

        env = os.environ.copy()
        env.update(
            CI_DATA_DIR=str(data_dir),
            CI_API_TARGET=backend_url,
            VITE_CI_MOCK="0",
            PYTHONUNBUFFERED="1",
            PYTHONUTF8="1",
        )
        session = time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
        processes: list[subprocess.Popen] = []
        if reuse_backend:
            print("后端：复用已有服务（退出启动器不会关闭它）")
        else:
            print("正在启动后端……")
            ensure_schema(db_path(data_dir))
            log = log_dir / f"{session}-backend.log"
            process = spawn(
                stack,
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "codeinsight.api.app:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(backend_port),
                ],
                ROOT,
                env,
                log,
            )
            processes.append(process)
            wait_ready(lambda: backend_ready(backend_url, data_dir), process, "后端", log)
        if reuse_frontend:
            print("前端：复用已有服务（退出启动器不会关闭它）")
        else:
            print("正在启动前端……")
            log = log_dir / f"{session}-frontend.log"
            process = spawn(
                stack,
                [
                    node,
                    str(vite),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(args.frontend_port),
                    "--strictPort",
                ],
                ROOT / "frontend",
                env,
                log,
            )
            processes.append(process)
            wait_ready(lambda: frontend_ready(frontend_url, data_dir), process, "前端", log)

        print(f"\n工作台已就绪：{frontend_url}\n日志：{log_dir}")
        print("请保留此窗口。按 Ctrl+C 停止本次启动的服务；已有服务会保留。")
        if not args.no_browser:
            if not webbrowser.open(frontend_url):
                print("未能自动打开浏览器，请手动打开上方地址。")
        deadline = time.monotonic() + args.run_seconds if args.run_seconds else None
        from codeinsight.runtime_version import current_revision

        started_revision = current_revision()
        warned_restart = False
        next_check = time.monotonic() + 5
        while processes and (deadline is None or time.monotonic() < deadline):
            for process in processes:
                if process.poll() is not None:
                    raise RuntimeError(f"服务意外退出，请查看日志：{log_dir}")
            if not warned_restart and time.monotonic() >= next_check:
                next_check = time.monotonic() + 5
                if current_revision() != started_revision:
                    print(
                        "\n后端代码已更新。当前回答不会自动中断；完成后请按 Ctrl+C，再重新运行启动器加载新版。"
                    )
                    warned_restart = True
            time.sleep(0.3)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n本次启动的服务已停止。")
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(f"\n[错误] {error}", file=sys.stderr)
        raise SystemExit(1) from None
