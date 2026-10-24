"""事实 / 推断拆分（ADR 0007）。

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
    result = split_answer(
        "删除任务的入口是 delete_job [backend/api/pet.py:1209]。", _grounding()
    )
    assert len(result.facts) == 1
    assert result.facts[0]["citation"]["path"] == "backend/api/pet.py"
    assert result.facts[0]["citation"]["lineno"] == 1209
    assert "backend/api/pet.py:1209" not in result.facts[0]["text"]
    assert result.inferences == []


def test_uncited_sentence_becomes_inference() -> None:
    result = split_answer("这个项目可能用了队列来解耦。", _grounding())
    assert result.facts == []
    assert len(result.inferences) == 1
    assert result.inferences[0]["confidence"] < 1


def test_fabricated_citation_is_removed_and_demoted() -> None:
    """编造的 file:line 必须从正文里消失，那句话降级为推断。"""
    result = split_answer("入口在 [backend/api/pet.py:9999]。", _grounding())
    assert result.facts == []
    assert result.inferences
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
    assert len(result.inferences) == 1
    assert "流式输出" in result.inferences[0]["text"]


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


def test_markdown_headings_do_not_become_inferences() -> None:
    """`**核心实现**` 是排版，不是主张——不该出现在推断栏。"""
    text = "**核心实现**\n入口是 stream [backend/core/chat.py:42]。\n1. **底层模型流**\n"
    result = split_answer(text, _grounding())
    assert len(result.facts) == 1
    assert result.inferences == []


def test_cited_locations_extracts_claims() -> None:
    assert cited_locations("看 [a.py:1] 和 [b/c.ts:20-30]") == [("a.py", 1), ("b/c.ts", 20)]
