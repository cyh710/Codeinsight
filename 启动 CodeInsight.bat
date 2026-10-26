@echo off
setlocal
chcp 65001 >nul
title CodeInsight
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto launch
where uv >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 uv。请先安装 Python 3.13+ 和 uv，再重新双击启动器。
  echo https://docs.astral.sh/uv/getting-started/installation/
  pause
  exit /b 1
)
echo 正在准备 Python 环境，首次运行可能需要几分钟……
uv sync --locked --extra dev
if errorlevel 1 (
  echo [错误] Python 依赖安装失败。请检查上方错误和网络连接。
  pause
  exit /b 1
)

:launch
".venv\Scripts\python.exe" -u scripts\launch.py %*
if errorlevel 1 (
  echo.
  echo 启动未完成，请查看上方提示。
  pause
  exit /b 1
)
endlocal
