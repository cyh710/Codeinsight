"""不调用模型的 A/C 接入演示：目录、章节注入、术语链接与阅读上下文。"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from codeinsight.cognitive.concepts.integration import LearningBridge
from codeinsight.cognitive.concepts.library import LearningLibrary
from codeinsight.cognitive.concepts.service import KnowledgeService


def main() -> None:
    """把可审阅结果写入指定文件；示例回答来自静态摘要，不冒充模型运行。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=Path("knowledge/learning"))
    parser.add_argument("--question", default="SQL 是什么")
    parser.add_argument("--reading-topic", default=None)
    parser.add_argument("--reading-section", default="overview")
    parser.add_argument("--out", type=Path, default=Path(".ci/learning-demo.json"))
    args = parser.parse_args()
    library = LearningLibrary(args.assets)
    service = KnowledgeService(library)
    bridge = LearningBridge(service)
    reading = (
        library.target(args.reading_topic, args.reading_section) if args.reading_topic else None
    )
    prepared = bridge.prepare_turn(
        args.question, reading_context=asdict(reading) if reading else None
    )
    context = prepared.context
    if context.references:
        topic = library.get(context.references[0].target.topic_id)
        answer = bridge.finalize_answer(topic.summary, prepared)
    else:
        answer = bridge.finalize_answer(
            "内置知识库未找到匹配章节，请尝试更明确的术语或目录。", prepared
        )
    result = {
        "question": args.question,
        "library_version": library.version,
        "tree": library.tree(),
        "reading_context": asdict(reading) if reading else None,
        "context": asdict(context),
        "example_answer": answer,
        "agent_tool_result": asdict(prepared.as_tool_result()),
        "project_instances": service.find_instances(1, topic_id="sql-database"),
        "provider_calls": 0,
        "limitations": "本文件只演示 B 服务数据，不代表模型质量或界面验收；HTTP/SSE 与导航另有集成及浏览器测试。",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "out": str(args.out),
                "answer": answer["text"],
                "entries": [entry["href"] for entry in answer["learning_entries"]],
                "provider_calls": 0,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
