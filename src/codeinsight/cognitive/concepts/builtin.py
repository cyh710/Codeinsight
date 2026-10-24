"""内置教材装配与概念深度解释共用的有界材料。"""

from codeinsight.cognitive.concepts.assets import knowledge_directory
from codeinsight.cognitive.concepts.learning_models import KnowledgeContext, KnowledgeError
from codeinsight.cognitive.concepts.library import LearningLibrary


def concept_context(concept_id: str, max_bytes: int = 8_000) -> KnowledgeContext:
    """同名工程章节优先；资料不可用时返回空材料，解释服务仍能显示本体。"""
    try:
        library = LearningLibrary(knowledge_directory("learning"))
    except KnowledgeError:
        return KnowledgeContext("", (), True)
    target = library.target(concept_id)
    if target is None:
        topics = library.topics_for_concept(concept_id)
        target = library.target(topics[0].id) if topics else None
    return library.reading_context(target, max_bytes) if target else KnowledgeContext("", ())
