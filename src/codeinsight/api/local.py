"""本机桌面操作：只选择仓库路径，不读取或上传目录内容。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

from fastapi import APIRouter, Request

from codeinsight.api.errors import ApiFailure

router = APIRouter(tags=["local"])
_picker_lock = Lock()
_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}

_TK_PICKER = """
import json
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
try:
    root.attributes('-topmost', True)
    path = filedialog.askdirectory(title='选择要导入的 Git 项目文件夹', mustexist=True)
    print(json.dumps({'root_path': path or None}))
finally:
    root.destroy()
"""


def choose_folder() -> str | None:
    """在独立进程运行桌面选择框；取消为 None，失败交给端点转成可读错误。"""
    if sys.platform == "win32":
        # Windows venv 的 python.exe 是重定向器；超时只杀它会遗留真正的窗口进程。
        # helper 仅用标准库，直接以基础解释器运行，确保 timeout 能关闭实际窗口。
        command = [
            getattr(sys, "_base_executable", sys.executable),
            str(Path(__file__).with_name("folder_picker.py")),
        ]
    else:
        command = [sys.executable, "-c", _TK_PICKER]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    selected = json.loads(result.stdout)["root_path"]
    if selected is None:
        return None
    if not isinstance(selected, str) or not selected or not Path(selected).is_dir():
        raise ValueError("选择的文件夹已不存在，请重新选择")
    return str(Path(selected).resolve())


@router.post("/local/select-folder")
def select_folder(request: Request) -> dict[str, str | None]:
    """只允许本机页面打开一个原生选择框；选中后仍由原导入端点校验 Git 仓库。"""
    origin = request.headers.get("origin")
    if (
        request.client is None
        or request.client.host not in _LOCAL_HOSTS
        or (origin and urlsplit(origin).hostname not in _LOCAL_HOSTS)
    ):
        raise ApiFailure(
            status_code=403,
            code="bad_request",
            title="文件夹选择仅限本机使用",
            hint="请在运行 CodeInsight 的电脑上打开本地工作台。",
        )
    if not _picker_lock.acquire(blocking=False):
        raise ApiFailure(
            status_code=409,
            code="bad_request",
            title="文件夹选择框已打开",
            hint="请先完成或取消当前选择，再重试。",
        )
    try:
        return {"root_path": choose_folder()}
    except subprocess.TimeoutExpired as exc:
        raise ApiFailure(
            status_code=504,
            code="timeout",
            title="选择文件夹已超时",
            hint="请重新点击“选择文件夹”。",
        ) from exc
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        raise ApiFailure(
            status_code=503,
            code="internal_error",
            title="无法打开系统文件夹选择框",
            hint="请确认后端运行在本机桌面环境，然后重试。",
            detail=str(exc),
        ) from exc
    finally:
        _picker_lock.release()
