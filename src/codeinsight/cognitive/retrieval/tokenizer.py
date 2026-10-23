"""代码分词器（规格 §1.3 A9）。

**入库与查询共用这一个函数**——这是整条检索链的前提。
入库用一套切法、查询用另一套切法，命中就是碰运气，评测结论也不可信。

切法：

- 标识符 → **全名 + 小写形式 + snake 分词 + camel 分词**。
  `get_user_name` → `get_user_name get user name`
  `HTTPServer` → `HTTPServer httpserver http server`
  （全名和小写形式相同时只出一个，不重复计数。）
- 英文单词 → 小写。
- 中文 → 分词（jieba）或 bigram 兜底。

**为什么要给中文专门做处理**（ADR 0003）：
FTS5 的 `unicode61` 把连续的汉字当成**一个** token。一段中文 docstring
会变成一个巨型 token，在 BM25 的长度归一化下天然得分极低——
中文重的内容被系统性压死，于是 BM25 臂的劣势是**假象**，
对照实验的结论被我们自己的分词方式污染了。
先把中文切成词再入库，这个偏置就没了。
"""

from __future__ import annotations

import re

# 标识符 / 汉字串 / 数字
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[一-鿿]+|\d+")

# camel / Pascal / 缩写 的切分
_PART_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+")

_CJK_RE = re.compile(r"[一-鿿]+")

_jieba_module = None
_jieba_tried = False


def _jieba():
    """lazily 拿 jieba。

    jieba 第一次切词要加载词典（约 1 秒），所以只在真的要切中文时才 import。
    没装 jieba 也不致命——退到 bigram，中文不再是巨型 token，
    ADR 0003 关心的那个偏置依然被消除（只是切词质量差一点）。
    """
    global _jieba_module, _jieba_tried
    if not _jieba_tried:
        _jieba_tried = True
        try:
            import jieba  # type: ignore[import-not-found]

            _jieba_module = jieba
        except ImportError:
            _jieba_module = None
    return _jieba_module


def split_identifier(name: str) -> list[str]:
    """一个标识符 → 它的检索 token 列表（去重、保序）。"""
    out: list[str] = []
    seen: set[str] = set()

    def _emit(token: str) -> None:
        if token and token not in seen:
            seen.add(token)
            out.append(token)

    _emit(name)
    lowered = name.lower()
    _emit(lowered)

    # snake 分词
    parts: list[str] = []
    for piece in name.split("_"):
        if not piece:
            continue
        # camel 分词
        parts.extend(_PART_RE.findall(piece))
    for part in parts:
        _emit(part.lower())

    return out


def _split_cjk(run: str) -> list[str]:
    """切一段汉字。

    有 jieba 用 jieba（词级）；没有就用 **bigram**——
    「用户认证」→ `用户 户认 认证`，而不是一个巨型 token。
    bigram 是中文检索里最经典的兜底：不需要词典就不会退化成一个词，
    而 ADR 0003 要消除的正是「一个词」这件事。
    """
    jieba = _jieba()
    if jieba is not None:
        return [w for w in (t.strip() for t in jieba.lcut(run)) if w]

    if len(run) == 1:
        return [run]
    return [run[i : i + 2] for i in range(len(run) - 1)]


def split_identifiers(text: str) -> list[str]:
    """把文本切成检索 token 列表。

    入库（chunk 正文）与查询（用户输入）都调这个函数。
    """
    if not text:
        return []

    out: list[str] = []
    seen: set[str] = set()

    def _emit(token: str) -> None:
        if token and token not in seen:
            seen.add(token)
            out.append(token)

    for match in _TOKEN_RE.finditer(text):
        piece = match.group(0)
        if _CJK_RE.fullmatch(piece):
            for word in _split_cjk(piece):
                _emit(word)
        elif piece[0].isdigit():
            # 纯数字当噪声丢掉：BM25 命中数字几乎不带来语义。
            continue
        else:
            for token in split_identifier(piece):
                _emit(token)

    return out


def token_text(text: str) -> str:
    """token 列表 → FTS5 正文（空格分隔的已分好词的串）。"""
    return " ".join(split_identifiers(text))
