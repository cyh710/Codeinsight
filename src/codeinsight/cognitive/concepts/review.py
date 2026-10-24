"""M5 样本审核统计；没有人工标签时不输出虚构的精确率或召回率。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any


def score_review(
    report: Mapping[str, Any], *, minimum_samples: int = 30, threshold: float = 0.8
) -> dict[str, Any]:
    """统计调用方记录的人工标签，不自动推断标签或审核者身份。

    label 只接受 bool 或 None；已标注样本须有 reviewed_by。未标注、重复位置、
    不同冻结版本不能静默混算。这里只有检测命中样本，没有完整真值全集，
    因而 recall/F1 永远为 None，precision 也仅指被审核的这个样本集。
    """
    errors = []
    samples = report.get("review_samples")
    if not isinstance(samples, list):
        samples = []
        errors.append("review_samples 必须为列表")
    for field in ("head_commit", "detection_version"):
        if not isinstance(report.get(field), str) or not report[field]:
            errors.append(f"缺少冻结版本 {field}")
    if minimum_samples < 1 or not 0 <= threshold <= 1:
        errors.append("最小样本数应为正整数，阈值应位于 [0, 1]")
    reviewed = []
    keys = set()
    for position, sample in enumerate(samples):
        if not isinstance(sample, dict):
            errors.append(f"样本 {position} 必须为映射")
            continue
        concept, path, line = sample.get("concept_id"), sample.get("path"), sample.get("lineno")
        if (
            not isinstance(concept, str)
            or not concept
            or not isinstance(path, str)
            or not path
            or isinstance(line, bool)
            or not isinstance(line, int)
            or line < 1
        ):
            errors.append(f"样本 {position} 缺少有效概念/位置")
            continue
        key = (concept, path, line)
        if key in keys:
            errors.append(f"重复样本：{concept} {path}:{line}")
            continue
        keys.add(key)
        if any(
            sample.get(field, report[field]) != report[field]
            for field in ("head_commit", "detection_version")
            if field in report
        ):
            errors.append(f"样本 {position} 与报告冻结版本不一致")
            continue
        label = sample.get("label")
        if label is None:
            continue
        if not isinstance(label, bool):
            errors.append(f"样本 {position} 的 label 必须为 true/false/null")
            continue
        reviewer = sample.get("reviewed_by")
        if not isinstance(reviewer, str) or not reviewer.strip():
            errors.append(f"样本 {position} 已标注但缺少 reviewed_by")
            continue
        reviewed.append(sample)
    correct = sum(s["label"] for s in reviewed)
    precision = correct / len(reviewed) if reviewed else None
    complete = len(reviewed) == len(samples) and len(reviewed) >= minimum_samples
    status = (
        "invalid"
        if errors
        else (
            ("sample_threshold_met" if precision >= threshold else "sample_threshold_not_met")
            if complete
            else "pending_human_review"
        )
    )
    return {
        "status": status,
        "head_commit": report.get("head_commit"),
        "detection_version": report.get("detection_version"),
        "sample_count": len(samples),
        "reviewed_count": len(reviewed),
        "pending_count": len(samples) - len(reviewed),
        "true_positives": correct,
        "false_positives": len(reviewed) - correct,
        "precision": precision if not errors else None,
        "recall": None,
        "f1": None,
        "minimum_samples": minimum_samples,
        "threshold": threshold,
        "reviewed_by": sorted({s["reviewed_by"] for s in reviewed}),
        "reviewed_concepts": dict(Counter(s["concept_id"] for s in reviewed)),
        "false_positive_samples": [
            {k: s[k] for k in ("concept_id", "path", "lineno", "reviewed_by")}
            for s in reviewed
            if not s["label"]
        ],
        "errors": errors,
        "limitations": "仅统计提供的人工审核样本，不认证审核者身份；没有全量真值，不能计算完整召回率。",
    }
