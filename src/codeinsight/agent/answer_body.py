"""合并所有模型回合的公开正文；工具名称不决定正文是否保留。"""

from collections.abc import Sequence


def is_answer_attachment(names: Sequence[str]) -> bool:
    """只认可不增加项目事实的探索附加工具，不把检索过程误当正文。"""
    return bool(names) and all(name == "propose_exploration" for name in names)


def merge_answer_body(parts: Sequence[str], final: str) -> str:
    """按输出次序保留正文；仅去重完全相同的完整片段，不猜测替换。"""
    kept: list[str] = []
    for text in [*parts, final]:
        if not text.strip() or text in kept:
            continue
        kept.append(text)
    return "\n\n".join(kept)
