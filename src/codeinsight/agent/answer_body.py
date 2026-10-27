"""将探索附加阶段的公开正文与最终补充合并；不授予任何事实资格。"""

from collections.abc import Sequence


def is_answer_attachment(names: Sequence[str]) -> bool:
    """只认可不增加项目事实的探索附加工具，不把检索过程误当正文。"""
    return bool(names) and all(name == "propose_exploration" for name in names)


def merge_answer_body(parts: Sequence[str], final: str) -> str:
    """按输出次序保留正文；仅在原文已包含时去重，不靠长度或语义猜测替换。"""
    body = ""
    for text in [*parts, final]:
        if not text.strip():
            continue
        if not body:
            body = text
        elif text.strip() in body.strip():
            continue
        elif body.strip() in text.strip():
            body = text
        else:
            body += "\n\n" + text
    return body
