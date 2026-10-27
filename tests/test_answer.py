"""定位核对与完整解释（ADR 0040）。

验收口径：**没有校验通过的位置，就不能算事实**。
模型编行号是最贵的错误——用户没法一眼看出来，而这套系统的全部信任
建立在「你给的 file:line 是真的」上。
"""

from __future__ import annotations

from codeinsight.agent.answer import GroundedFile, Grounding, cited_locations, split_answer


def _grounding() -> Grounding:
    grounding = Grounding()
    grounding.add(GroundedFile("backend/api/pet.py", 1209, 1230, "backend.api.pet.delete_job"))
    grounding.add(GroundedFile("backend/core/chat.py", 42, 60, "backend.core.chat.stream"))
    return grounding


def test_cited_sentence_becomes_fact() -> None:
    result = split_answer("删除任务的入口是 delete_job [backend/api/pet.py:1209]。", _grounding())
    assert len(result.facts) == 1
    assert result.facts[0]["citation"]["path"] == "backend/api/pet.py"
    assert result.facts[0]["citation"]["lineno"] == 1209
    assert "backend/api/pet.py:1209" not in result.facts[0]["text"]
    assert result.inferences == []


def test_uncited_sentence_stays_explanation() -> None:
    result = split_answer("这个项目可能用了队列来解耦。", _grounding())
    assert result.facts == []
    assert result.inferences == []
    assert result.text == "这个项目可能用了队列来解耦。"


def test_invalid_citation_moves_to_details_without_classifying_sentence() -> None:
    """编造的 file:line 必须从正文里消失，那句话降级为推断。"""
    result = split_answer("入口在 [backend/api/pet.py:9999]。", _grounding())
    assert result.facts == []
    assert result.inferences == []
    assert "入口在" in result.text
    assert "9999" not in result.text
    assert result.dropped_citations == ["backend/api/pet.py:9999"]


def test_citation_inside_grounded_range_keeps_the_exact_line() -> None:
    """行号落在工具给出的窗口内也算通过，但引用要精确到那一行。

    校验用「窗口包含」判断真伪，展示不能用窗口起点——否则读过 1-200 行之后，
    每条事实都会指向第 1 行，用户点过去看到的是文件头。
    """
    result = split_answer("这里组装上下文 [backend/core/chat.py:55]。", _grounding())
    assert len(result.facts) == 1
    assert result.facts[0]["citation"]["lineno"] == 55
    assert result.citations[0].lineno == 55


def test_citations_are_deduplicated() -> None:
    result = split_answer(
        "A 在 [backend/core/chat.py:42]。B 也在 [backend/core/chat.py:42]。", _grounding()
    )
    assert len(result.citations) == 1


def test_fact_and_inference_are_separated_in_one_answer() -> None:
    text = "入口是 stream [backend/core/chat.py:42]。这样设计可能是为了流式输出。"
    result = split_answer(text, _grounding())
    assert len(result.facts) == 1
    assert result.inferences == []
    assert "这样设计可能是为了流式输出" in result.text


def test_no_grounding_means_no_facts() -> None:
    result = split_answer("没有证据也能说的话 [a.py:1]。", Grounding())
    assert result.facts == []
    assert result.citations == []


def test_fact_text_is_plain_not_markdown() -> None:
    """卡片不是 Markdown 渲染区：加粗与行内代码标记要去掉。"""
    result = split_answer("1. **入口**是 `stream` [backend/core/chat.py:42]。", _grounding())
    fact = result.facts[0]["text"]
    assert "**" not in fact
    assert "`" not in fact
    assert fact.startswith("入口是 stream")


def test_split_bold_markers_leave_no_artifacts() -> None:
    """跨句的加粗标记切开后会剩孤零零的 `**`，不能变成空推断。"""
    text = "**结论：主流程没变。**\n**\n**细节见下。"
    result = split_answer(text, Grounding())
    assert all(item["text"].strip() not in {"", "**"} for item in result.inferences)
    assert "**" not in "".join(item["text"] for item in result.inferences)


def test_markdown_headings_do_not_become_inferences() -> None:
    """`**核心实现**` 是排版，不是主张——不该出现在推断栏。"""
    text = "**核心实现**\n入口是 stream [backend/core/chat.py:42]。\n1. **底层模型流**\n"
    result = split_answer(text, _grounding())
    assert len(result.facts) == 1
    assert result.inferences == []


def test_cited_locations_extracts_claims() -> None:
    assert cited_locations("看 [a.py:1] 和 [b/c.ts:20-30]") == [("a.py", 1), ("b/c.ts", 20)]


def test_markdown_structure_survives_the_split() -> None:
    """markdown 块结构必须原样保留。

    早先的实现按句子切分并丢掉分隔符，正文的换行全没了——
    1419 字的回答只剩 2 个换行，代码块和列表糊成一段，
    界面看起来像一坨。前端是 markdown 渲染器，结构就是长相。
    """
    md = (
        "**核心概念**\n"
        "\n"
        "- **表**：由列定义结构。\n"
        "- **约束**：如 `PRIMARY KEY`。\n"
        "\n"
        "```sql\n"
        "CREATE TABLE products (\n"
        "  id integer PRIMARY KEY\n"
        ");\n"
        "```\n"
        "\n"
        "入口是 stream [backend/core/chat.py:42]。\n"
    )
    result = split_answer(md, _grounding())

    # 段落之间的空行
    assert "**核心概念**\n\n- **表**" in result.text
    # 列表项各占一行
    assert "- **表**：由列定义结构。\n- **约束**" in result.text
    # 代码块完整
    assert "```sql\nCREATE TABLE products (\n  id integer PRIMARY KEY\n);\n```" in result.text
    # 事实/推断判定仍然生效
    assert len(result.facts) == 1
    assert result.facts[0]["citation"]["path"] == "backend/core/chat.py"


def test_code_block_is_not_treated_as_a_claim() -> None:
    """代码块里的文字不是主张——不该进推断栏。"""
    md = "```python\n# 这条注释不是主张\nx = 1\n```\n"
    result = split_answer(md, _grounding())
    assert result.inferences == []
    assert "x = 1" in result.text


def test_table_and_soft_line_breaks_survive_citation_verification() -> None:
    text = (
        "说明第一行\n说明第二行\n\n"
        "| 核对对象 | 位置 |\n|---|---|\n"
        "| 入口 | [backend/core/chat.py:42] |\n| 未知 | [ghost.py:99] |"
    )
    result = split_answer(text, _grounding(), preserve_invalid=True)
    assert "说明第一行\n说明第二行" in result.text
    assert "| 核对对象 | 位置 |\n|---|---|\n| 入口 |" in result.text
    assert "ghost.py:99" not in result.text
    assert result.dropped_citations == ["ghost.py:99"]
    assert all(citation.path != "ghost.py" for citation in result.citations)


def test_examples_are_not_citations_and_invalid_ranges_only_remove_markers():
    example = "`[ghost.py:99]` 和 [文档](https://example.org/a.py:2)\n\n```py\n[ghost.py:99]\n```"
    result = split_answer(example, _grounding())
    assert result.text == example
    assert not result.citations and not result.inferences and not result.dropped_citations
    ranges = split_answer(
        "实现 [backend/core/chat.py:42-60]。缺口 [backend/core/chat.py:55-999999999]。",
        _grounding(),
    )
    assert "42-60" in ranges.text and "55-999999999" not in ranges.text
    assert "缺口" in ranges.text and len(ranges.citations) == 1
    assert ranges.dropped_citations == ["backend/core/chat.py:55-999999999"]
