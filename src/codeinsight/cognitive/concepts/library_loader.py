"""按实际内容复用只读教材快照，不缓存项目实例、会话或模型结果。"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from threading import RLock

from codeinsight.cognitive.concepts.assets import knowledge_directory
from codeinsight.cognitive.concepts.learning_models import KnowledgeError
from codeinsight.cognitive.concepts.library import LearningLibrary

_lock = RLock()


def _fingerprint(directory: Path) -> str:
    paths = [directory / "index.json", directory / "sources.json"]
    paths.extend(sorted((directory / "articles").rglob("*.md")))
    paths.extend(sorted((directory / "licenses").rglob("*.txt")))
    if (directory / "assets.json").exists():
        paths.append(directory / "assets.json")
    paths.extend(sorted(p for p in (directory / "assets").rglob("*") if p.is_file()))
    digest = hashlib.sha256()
    try:
        for path in paths:
            digest.update(path.relative_to(directory).as_posix().encode())
            digest.update(b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    except OSError as exc:
        raise KnowledgeError(f"无法读取教材快照：{exc}") from exc
    return digest.hexdigest()


@lru_cache(maxsize=2)
def _snapshot(directory: Path, fingerprint: str) -> LearningLibrary:
    library = LearningLibrary(directory)
    if _fingerprint(directory) != fingerprint:
        raise KnowledgeError("教材在加载过程中发生更新，请重试。")
    return library


def get_learning_library(directory: Path | None = None) -> LearningLibrary:
    """相同资产内容共用校验和分词结果；文件变化立即重新校验，损坏时不退回旧版本。

    指纹读取实际内容而非 mtime，避免保留时间戳的更新漏失效。快照最多保留两个，
    锁仅保护加载及缓存；查询仍使用各自的 SQLite 连接，项目状态不进入缓存。
    """
    root = (directory if directory is not None else knowledge_directory("learning")).resolve()
    with _lock:
        return _snapshot(root, _fingerprint(root))
