"""运行版本只包含 CodeInsight 后端源码，不读取密钥或被分析项目。"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parent


@lru_cache(maxsize=2)
def _revision(stamp: tuple[tuple[str, int, int], ...]) -> str:
    digest = hashlib.sha256()
    for path, _, _ in stamp:
        digest.update(Path(path).relative_to(_PACKAGE).as_posix().encode())
        digest.update(Path(path).read_bytes())
    return digest.hexdigest()


def current_revision() -> str:
    """内容变化才重算指纹；Git 提交不会因未提交修改而误报为同一版本。"""
    files = sorted([*_PACKAGE.rglob("*.py"), _PACKAGE / "storage/schema.sql"])
    return _revision(tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files))


LOADED_REVISION = current_revision()


def runtime_status() -> dict[str, str | bool]:
    """进程加载的版本固定，磁盘代码更新仅提示重启，不在请求中自动重载。"""
    return {
        "runtime_revision": LOADED_REVISION,
        "restart_required": current_revision() != LOADED_REVISION,
    }
