"""学习导航与代码实例隔离。"""

from codeinsight.cognitive.concepts.links import link_answer, validate_answer_links
from codeinsight.cognitive.concepts.service import KnowledgeService, ProjectConcepts
from codeinsight.models import ConceptInstance


def test_inline_terms_link_once_and_code_is_untouched(library):
    text = "SQL 操作数据库。再次说 SQL。\n\n```sql\nSELECT name FROM t; -- SQL\n```\n\n`SQL` 与 [SQL官网](https://example.org)。"
    result = link_answer(text, library)
    assert result.text.startswith("[SQL](/learn/sql-database)")
    assert "再次说 SQL" in result.text
    assert "```sql\nSELECT name FROM t; -- SQL\n```" in result.text
    assert "`SQL` 与 [SQL官网](https://example.org)" in result.text


def test_inline_links_are_not_limited_by_footer_count(library):
    text = "SQL、React、TypeScript、Promise 和 Python。"
    targets = [library.target(t) for t in list(library.topics)[:6]]
    result = link_answer(text, library, recommendations=targets)
    assert len(result.targets) >= 5
    assert len(result.learning_entries) == 3


def test_invalid_targets_fall_back_to_text(library):
    assert validate_answer_links("[不存在](/learn/none)", library) == "不存在"
    assert validate_answer_links("[SQL](/learn/sql-database#overview)", library).startswith("[SQL]")


def test_unindexed_does_not_claim_project_lacks_technology(library):
    result = KnowledgeService(library).find_instances(1, topic_id="sql-database")
    assert result["status"] == "not_indexed"


def test_project_switch_cannot_reuse_other_project_evidence(library):
    instance = ConceptInstance(
        "db-transaction", "a.py", 7, evidence="BEGIN 与 commit", confidence=0.95
    )
    service = KnowledgeService(
        library,
        {
            1: ProjectConcepts(1, "commit-1", 3, (instance,)),
            2: ProjectConcepts(2, "commit-2", 1, ()),
        },
    )
    assert service.find_instances(1, topic_id="sql-transactions")["total"] == 1
    assert service.find_instances(2, topic_id="sql-transactions")["total"] == 0
    assert service.concepts_at(2, "a.py")["items"] == []


def test_absent_design_claim_is_not_automatically_stale(library):
    service = KnowledgeService(library, {1: ProjectConcepts(1, "c", 1, ())})
    result = service.compare_claims(1, [{"concept_id": "redis-cache", "pattern": "cache"}])
    assert result[0]["status"] == "not_observed"


def test_single_character_technical_term_does_not_change_normal_words(library):
    result = link_answer("SQL 操作“表”，这些数据表示商品。", library)
    assert "“[表](/learn/sql-database)”" in result.text
    assert "表示商品" in result.text


def test_streaming_unclosed_code_block_is_not_annotated(library):
    text = "SQL\n\n```sql\nSELECT name -- SQL"
    result = link_answer(text, library)
    assert result.text.endswith("```sql\nSELECT name -- SQL")


def test_invalid_link_examples_inside_code_are_not_rewritten(library):
    text = "```md\n[不存在](/learn/none)\n```"
    assert validate_answer_links(text, library) == text


def test_reading_target_is_used_for_anaphoric_follow_up(library):
    service = KnowledgeService(library)
    target = library.target("python-functions", "example")
    context, entries = service.prepare_turn("这里是什么意思", reading=target)
    assert context.references[0].target == target
    assert "calculate_total" in context.content
    assert len(entries) <= 3 and all(library.resolve_href(t.href) for t in entries)
