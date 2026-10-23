"""人工标签统计的边界；这里的标签是合成夹具，不能计入真实验收。"""

import json
from pathlib import Path

from codeinsight.cognitive.concepts.review import score_review


def fixture(labels):
    return {
        "head_commit": "frozen-commit",
        "detection_version": "frozen-rules",
        "review_samples": [
            {
                "concept_id": "async",
                "path": "example.py",
                "lineno": i + 1,
                "label": label,
                "reviewed_by": "synthetic-test-fixture",
            }
            for i, label in enumerate(labels)
        ],
    }


def test_unlabelled_real_samples_have_no_fabricated_metrics():
    path = Path(__file__).resolve().parents[2] / "knowledge/learning/reviews/tapestry-agent-v1.json"
    result = score_review(json.loads(path.read_text(encoding="utf-8")))
    assert result["sample_count"] == 30
    assert result["status"] == "pending_human_review"
    assert result["reviewed_count"] == 0
    assert result["precision"] is result["recall"] is result["f1"] is None


def test_partial_sample_precision_is_not_acceptance():
    result = score_review(fixture([True, False, None]))
    assert result["status"] == "pending_human_review"
    assert result["precision"] == 0.5
    assert result["pending_count"] == 1


def test_eighty_percent_is_only_a_sample_threshold():
    result = score_review(fixture([True] * 24 + [False] * 6))
    assert result["status"] == "sample_threshold_met"
    assert result["precision"] == 0.8
    assert result["false_positives"] == 6
    assert len(result["false_positive_samples"]) == 6
    assert result["recall"] is result["f1"] is None
    assert score_review(fixture([True] * 23 + [False] * 7))["status"] == "sample_threshold_not_met"


def test_duplicates_and_mixed_versions_do_not_inflate_sample_count():
    raw = fixture([True] * 30)
    raw["review_samples"][1] = dict(raw["review_samples"][0])
    result = score_review(raw)
    assert result["status"] == "invalid" and result["precision"] is None
    raw = fixture([True] * 30)
    raw["review_samples"][0]["head_commit"] = "different-commit"
    assert score_review(raw)["status"] == "invalid"


def test_missing_reviewer_or_invalid_label_cannot_pass_acceptance():
    raw = fixture([True] * 30)
    del raw["review_samples"][0]["reviewed_by"]
    assert score_review(raw)["status"] == "invalid"
    raw["review_samples"][0]["label"] = 1
    assert score_review(raw)["status"] == "invalid"
    assert score_review({})["status"] == "invalid"
