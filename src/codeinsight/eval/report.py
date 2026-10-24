"""评测报告（源文档 §6）。

报告的第一职责是**不骗人**，所以它必须写清四件事：

1. 样本量 n 与 95% 置信区间——没有区间的点估计不是结论。
2. 哪些臂不可用、为什么——退化的臂不能静默变成别的臂。
3. ground truth 从哪来——自动生成，不是人工标注。
4. 哪些指标**没测**——结构正确率、问答正确率、人工探索效率都不在这份报告里。

宁可报告短，也不要报告好看。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codeinsight.eval.metrics import Estimate
from codeinsight.eval.runner import ArmRun


@dataclass(frozen=True)
class ReportMeta:
    run_id: str
    project: str
    head_commit: str | None
    seed: int
    k: int
    kinds: tuple[str, ...]
    n_per_kind: int
    embedding_model: str
    llm_model: str = ""
    generated_at: str = ""


def build_report(meta: ReportMeta, runs: list[ArmRun]) -> dict[str, Any]:
    """把各臂结果折成可序列化、可渲染的结构。"""
    kinds = list(meta.kinds)
    arms: list[dict[str, Any]] = []
    for run in runs:
        entry: dict[str, Any] = {
            "arm": run.arm.name,
            "description": run.arm.description,
            "control": run.arm.control,
            "available": run.available,
            "reason": run.reason,
            "n": len(run.outcomes),
        }
        if run.available:
            summary = run.summarize(k=meta.k, kinds=meta.kinds, seed=meta.seed)
            entry["overall"] = _estimate_payload(summary["overall"])
            entry["by_kind"] = {
                kind: _estimate_payload(values) for kind, values in summary["by_kind"].items()
            }
        arms.append(entry)

    baseline = next((item for item in arms if item["arm"] == "bm25" and item["available"]), None)
    for entry in arms:
        if not entry["available"] or baseline is None or entry is baseline:
            continue
        entry["delta_mrr_vs_bm25"] = (
            entry["overall"]["mrr"]["value"] - baseline["overall"]["mrr"]["value"]
        )

    return {
        "meta": {
            "run_id": meta.run_id,
            "project": meta.project,
            "head_commit": meta.head_commit,
            "seed": meta.seed,
            "k": meta.k,
            "kinds": kinds,
            "n_per_kind": meta.n_per_kind,
            "embedding_model": meta.embedding_model,
            "llm_model": meta.llm_model,
            "generated_at": meta.generated_at or datetime.now(UTC).isoformat(timespec="seconds"),
        },
        "arms": arms,
        "caveats": [
            "题目由索引自动生成，ground truth 是符号的 file:line——不是人工标注，也没有人工复核。",
            "`concept` 题的 ground truth 是该概念的**任意一处**实例（含测试文件里的用法）——"
            "问的是「哪里用了 X」，答到另一处不算错；定位题则只认唯一那个符号。",
            "只测了定位（检索）；结构正确率、问答正确率、人工探索效率不在本报告内。",
            "n 较小时区间很宽，臂间差值小于区间重叠范围时**不能**当作结论。",
            "所有臂共用同一份索引、同一个 seed、同一批题；差别只有通道开关。",
        ],
    }


def _estimate_payload(values: dict[str, Estimate]) -> dict[str, dict[str, float | int]]:
    return {
        key: {"value": est.value, "low": est.low, "high": est.high, "n": est.n}
        for key, est in values.items()
    }


def format_markdown(report: dict[str, Any]) -> str:
    meta = report["meta"]
    lines: list[str] = []
    lines.append(f"# 检索对照报告 · {meta['project']}@{str(meta['head_commit'])[:8]}")
    lines.append("")
    lines.append(
        f"- run_id `{meta['run_id']}` · seed `{meta['seed']}` · k=`{meta['k']}`"
        f" · 每题型 n=`{meta['n_per_kind']}`"
    )
    lines.append(f"- 嵌入模型 `{meta['embedding_model']}` · 生成于 {meta['generated_at']}")
    lines.append("")
    lines.append("## 总览（全部题型合并）")
    lines.append("")
    lines.append("| 臂 | 说明 | 命中@k | MRR | Top-1 | ΔMRR vs bm25 |")
    lines.append("|---|---|---|---|---|---|")
    for entry in report["arms"]:
        if not entry["available"]:
            lines.append(
                f"| `{entry['arm']}` | {entry['description']} | — | — | — | 不可用：{entry['reason']} |"
            )
            continue
        overall = entry["overall"]
        delta = entry.get("delta_mrr_vs_bm25")
        delta_text = f"{delta:+.3f}" if isinstance(delta, float) else "基线"
        lines.append(
            f"| `{entry['arm']}` | {entry['description']} | "
            f"{_fmt(overall['hit_rate'], percent=True)} | "
            f"{_fmt(overall['mrr'])} | "
            f"{_fmt(overall['top1_rate'], percent=True)} | {delta_text} |"
        )
    lines.append("")

    for kind in meta["kinds"]:
        lines.append(f"## 分题型：`{kind}`")
        lines.append("")
        lines.append("| 臂 | 命中@k | MRR | Top-1 |")
        lines.append("|---|---|---|---|")
        for entry in report["arms"]:
            if not entry["available"]:
                lines.append(f"| `{entry['arm']}` | — | — | — |")
                continue
            stats_by_kind = entry["by_kind"].get(kind)
            if not stats_by_kind:
                lines.append(f"| `{entry['arm']}` | — | — | — |")
                continue
            lines.append(
                f"| `{entry['arm']}` | {_fmt(stats_by_kind['hit_rate'], percent=True)} | "
                f"{_fmt(stats_by_kind['mrr'])} | {_fmt(stats_by_kind['top1_rate'], percent=True)} |"
            )
        lines.append("")

    lines.append("## 读这份报告时要注意")
    lines.append("")
    for caveat in report["caveats"]:
        lines.append(f"- {caveat}")
    lines.append("")
    lines.append("> 括号内是 95% bootstrap 置信区间；`n` 是参与统计的题数。")
    return "\n".join(lines) + "\n"


def _fmt(estimate: dict[str, Any], *, percent: bool = False) -> str:
    if percent:
        return f"{estimate['value']:.0%} [{estimate['low']:.0%}, {estimate['high']:.0%}]"
    return f"{estimate['value']:.3f} [{estimate['low']:.3f}, {estimate['high']:.3f}]"


def write_report(report: dict[str, Any], *, out_root: str | Path = "eval/reports") -> Path:
    """写到 `eval/reports/<run_id>/`：`report.md` 给人看，`results.json` 给机器看。"""
    directory = Path(out_root) / report["meta"]["run_id"]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "report.md").write_text(format_markdown(report), encoding="utf-8")
    (directory / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return directory
