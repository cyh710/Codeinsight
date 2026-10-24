"""对审核文件计分：只读取人工标签，不调用模型，也不回填标签。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from codeinsight.cognitive.concepts.review import score_review


def main() -> None:
    """默认审核随库的 30 条待标注样本；原始文件始终保持不变。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--review", type=Path, default=Path("knowledge/learning/reviews/tapestry-agent-v1.json")
    )
    parser.add_argument("--out", type=Path, default=Path(".ci/concept-review-score.json"))
    args = parser.parse_args()
    try:
        raw = json.loads(args.review.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("审核文件顶层必须为映射")
        result = score_review(raw)
    except (OSError, ValueError) as exc:
        result = {"status": "invalid", "errors": [str(exc)]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] == "invalid":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
