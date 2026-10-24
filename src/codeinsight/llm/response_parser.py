"""从模型回复里抠出 JSON。

移植自织忆 `ai-companion-agent` `backend/llm/response_parser.py`（Apache-2.0，
见 `docs/ported-from-tapestry.md`）。处理的都是**真实出现过**的坏格式：

- ` ```json … ``` ` 围栏；
- MiniMax 的 `<think>…</think>` 思考泄漏进正文；
- JSON 后面跟一句「希望对您有帮助」；
- 字符串值里没转义的双引号（模型转述用户原话时最常见）；
- 多包一层的 `{{…}}`。

这些都不是我们模型的问题，是**所有** OpenAI 兼容模型都会犯的错。
每次换个 provider 就重写一遍解析器，是把同一个 bug 修第 N 次。
"""

from __future__ import annotations

import json
import re

__all__ = ["extract_json"]


def _find_json_span(text: str) -> str | None:
    """找到第一个括号配平的 `{…}` / `[…]`，忽略后面的闲话。

    跳过字符串字面量里的括号——否则 `{"a": "}"}` 会被判成提前闭合。
    """
    open_chars = {"{": "}", "[": "]"}
    for i, ch in enumerate(text):
        if ch not in open_chars:
            continue
        close = open_chars[ch]
        depth = 0
        in_str = False
        escape = False
        for j in range(i, len(text)):
            c = text[j]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if c == ch:
                depth += 1
            elif c == close:
                depth -= 1
                if depth == 0:
                    return text[i : j + 1]
        return None
    return None


def _repair_unescaped_inner_quotes(text: str) -> str:
    """把字符串值里漏转义的双引号补上反斜杠。

    判据：一个在字符串内的 `"` 只有在后面（跳过空白）紧跟 `: , } ]` 或结束时
    才算合法闭合；否则它是正文里的引号，要转义。
    已经合法的 JSON 原样返回——每个闭合引号都满足这条规则。
    """
    out: list[str] = []
    in_str = False
    escape = False
    i = 0
    n = len(text)
    legitimate_terminators = {",", ":", "}", "]"}
    while i < n:
        c = text[i]
        if escape:
            out.append(c)
            escape = False
            i += 1
            continue
        if c == "\\":
            out.append(c)
            escape = True
            i += 1
            continue
        if c == '"':
            if not in_str:
                in_str = True
                out.append(c)
                i += 1
                continue
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j >= n or text[j] in legitimate_terminators:
                in_str = False
                out.append(c)
            else:
                out.append('\\"')
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _loads_json_or_double_wrapped_object(text: str) -> dict | list:
    """解析 JSON，兼容常见的 `{{…}}` 双层包裹。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError as original_error:
        stripped = text.strip()
        if stripped.startswith("{{") and stripped.endswith("}}"):
            inner = stripped[1:-1].strip()
            if inner.startswith("{") and inner.endswith("}"):
                try:
                    return json.loads(inner)
                except json.JSONDecodeError:
                    pass
        raise original_error


def extract_json(raw: str) -> dict | list:
    """剥掉围栏 / 思考标签 / 尾部闲话，返回解析后的 JSON。

    找不到任何合法 JSON 时抛 `json.JSONDecodeError`——调用方要能区分
    「模型没按格式回答」和「模型给了空答案」，不能用 None 糊过去。
    """
    clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    clean = re.sub(r"<think>.*", "", clean, flags=re.DOTALL).strip()

    if clean.startswith("```"):
        newline = clean.find("\n")
        clean = clean[newline + 1 :] if newline != -1 else clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3].strip()

    try:
        return _loads_json_or_double_wrapped_object(clean)
    except json.JSONDecodeError:
        pass

    repaired = _repair_unescaped_inner_quotes(clean)
    if repaired != clean:
        try:
            return _loads_json_or_double_wrapped_object(repaired)
        except json.JSONDecodeError:
            pass

    span = _find_json_span(clean)
    if span is None:
        # 原样再抛一次，让上层看到真实的解析错误位置。
        return _loads_json_or_double_wrapped_object(clean)
    try:
        return _loads_json_or_double_wrapped_object(span)
    except json.JSONDecodeError:
        repaired_span = _repair_unescaped_inner_quotes(span)
        if repaired_span != span:
            return _loads_json_or_double_wrapped_object(repaired_span)
        raise
