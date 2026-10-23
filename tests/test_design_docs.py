"""设计说明索引（规格 §1.2 A6）。

验收口径：标题/编号/状态能抽出来；「声称」能落成**可验证**的 claim
（路径或符号）；没法验证的话不进 claim。
"""

from __future__ import annotations

from codeinsight.cognitive.indexing.design_docs import (
    is_design_doc,
    parse_design_doc,
    parse_design_docs,
)

ADR = """\
---
id: ADR-0005
status: accepted
date: 2026-09-07
---

# 0005 — 切块按符号边界

- **状态**：已接受

切块以符号为原子，实现在 `cognitive/indexing/chunker.py`，
核心函数是 `chunk_symbol` 与 `split_identifiers`。

超过 120 行就二次切分，写 `ordinal` 与 `part_count`。
"""


def test_design_doc_paths_are_recognized() -> None:
    assert is_design_doc("docs/decisions/0005-chunking.md")
    assert is_design_doc("docs/adr/0012-x.md")
    assert is_design_doc("ADR-0003-something.md")
    assert not is_design_doc("README.md")
    assert not is_design_doc("backend/core/chunker.py")


def test_frontmatter_and_heading_are_parsed() -> None:
    doc = parse_design_doc("docs/decisions/0005-chunking.md", ADR)
    assert doc.doc_id == "ADR-0005"
    assert doc.title == "0005 — 切块按符号边界"
    assert doc.status == "accepted"
    assert doc.decided_at == "2026-09-07"


def test_status_from_chinese_bullet() -> None:
    doc = parse_design_doc("docs/decisions/x.md", "# 标题\n\n- **状态**：已接受\n")
    assert doc.status == "accepted"


def test_status_with_explanation_is_normalized() -> None:
    """「已接受（截至 2026-09-07 已生效）」要归一成 `accepted`。"""
    doc = parse_design_doc(
        "docs/decisions/x.md",
        "# 标题\n\n- **状态**：已接受（截至 2026-09-07 文档刷新时已生效）\n",
    )
    assert doc.status == "accepted"


def test_claims_include_paths_and_symbols() -> None:
    doc = parse_design_doc("docs/decisions/0005-chunking.md", ADR)
    paths = {c["value"] for c in doc.claims if c["kind"] == "path"}
    symbols = {c["value"] for c in doc.claims if c["kind"] == "symbol"}
    assert "cognitive/indexing/chunker.py" in paths
    assert "chunk_symbol" in symbols
    assert "split_identifiers" in symbols


def test_only_verifiable_claims_are_kept() -> None:
    """没法落到代码里的说法不进 claim——过期检测只检查能检查的东西。"""
    doc = parse_design_doc(
        "docs/decisions/x.md",
        "# 标题\n\n这个设计很好，`某个词组不算标识符`，还有 `def`。\n",
    )
    values = {c["value"] for c in doc.claims}
    assert "某个词组不算标识符" not in values
    assert "def" not in values


def test_parse_many_docs_ignores_other_markdown() -> None:
    files = ["docs/decisions/a.md", "README.md", "backend/x.py"]
    sources = {
        "docs/decisions/a.md": "# A\n",
        "README.md": "# 项目\n",
        "backend/x.py": "x = 1\n",
    }
    docs = parse_design_docs(files, sources)
    assert len(docs) == 1
    assert docs[0].doc_id == "a"
