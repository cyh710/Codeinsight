"""本机桌面操作：只选择仓库路径，不读取或上传目录内容。"""

from __future__ import annotations

import base64
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

_WINDOWS_PICKER = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()
$owner = [System.Windows.Forms.Form]::new()
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.Opacity = 0
$dialog = [System.Windows.Forms.FolderBrowserDialog]::new()
$dialog.Description = '选择要导入的 Git 项目文件夹'
$dialog.ShowNewFolderButton = $false
if ($dialog.PSObject.Properties['AutoUpgradeEnabled']) { $dialog.AutoUpgradeEnabled = $true }
try {
    $owner.Show()
    $owner.Activate()
    $selected = $null
    if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
        $selected = $dialog.SelectedPath
    }
    ConvertTo-Json -Compress -InputObject @{root_path = $selected}
} finally {
    $dialog.Dispose()
    $owner.Dispose()
}
"""

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
        encoded = base64.b64encode(_WINDOWS_PICKER.encode("utf-16-le")).decode("ascii")
        command = ["powershell.exe", "-NoProfile", "-STA", "-EncodedCommand", encoded]
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
