"""分词器（规格 §1.3 A9）。

两个验收点：
1. 标识符切法符合规格写死的例子。
2. **中文不能是一个巨型 token**（ADR 0003）——
   FTS5 的 unicode61 会把连续汉字当一个 token，长度归一化会系统性压低中文重的内容。
"""

from __future__ import annotations

from codeinsight.cognitive.retrieval.tokenizer import (
    split_identifier,
    split_identifiers,
    token_text,
)


def test_snake_case_identifier() -> None:
    assert split_identifier("get_user_name") == ["get_user_name", "get", "user", "name"]


def test_camel_and_abbreviation_identifier() -> None:
    assert split_identifier("HTTPServer") == ["HTTPServer", "httpserver", "http", "server"]


def test_camel_case_identifier() -> None:
    assert split_identifier("getUserName") == ["getUserName", "getusername", "get", "user", "name"]


def test_plain_word_is_lowercased_once() -> None:
    assert split_identifier("helper") == ["helper"]


def test_repeated_identifier_keeps_its_frequency() -> None:
    """同一个标识符出现多次，token 也要出现多次。

    BM25 的 tf 分量靠的就是词频——跨出现去重等于把 tf 恒定成 1，
    BM25 会退化成纯 IDF 排序。
    """
    tokens = split_identifiers("foo foo")
    assert tokens == ["foo", "foo"]


def test_one_identifier_does_not_repeat_its_own_forms() -> None:
    """一次出现里，全名与小写形式相同就不该出两遍。"""
    assert split_identifiers("helper") == ["helper"]


def test_chinese_is_not_one_giant_token() -> None:
    """一段中文必须切成多个 token。"""
    tokens = split_identifiers("用户认证流程")
    assert len(tokens) > 1
    assert "用户认证流程" not in tokens


def test_chinese_and_code_mix() -> None:
    tokens = split_identifiers("使用FastAPI框架")
    assert "FastAPI" in tokens
    assert "fastapi" in tokens
    assert len(tokens) > 2


def test_numbers_are_dropped() -> None:
    """纯数字是噪声：BM25 命中数字几乎不带来语义。"""
    assert "42" not in split_identifiers("timeout=42")


def test_token_text_is_space_separated() -> None:
    text = token_text("def get_user_name(): pass")
    assert "get_user_name" in text.split()
    assert "get" in text.split()


def test_empty_text() -> None:
    assert split_identifiers("") == []
    assert token_text("") == ""


def test_query_uses_the_same_function_as_indexing() -> None:
    """入库与查询共用一个函数——这是整条检索链的前提。

    这里用同一个函数处理「代码」和「自然语言提问」，
    断言提问里的词能在代码的 token 里找到。
    """
    code = split_identifiers("def authenticate_user(token): ...")
    query = split_identifiers("How is authenticate_user used?")
    assert "authenticate_user" in code
    assert "authenticate_user" in query
    assert "authenticate" in code
    assert "authenticate" in query
