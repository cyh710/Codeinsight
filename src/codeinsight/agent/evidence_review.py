"""结构化证据状态描述核查结果，不代替语义正确性判断，也不删除正文。"""

from __future__ import annotations

from typing import Any

from codeinsight.models import Answer


def assess(answer: Answer, *, knowledge_only: bool, source_version: dict | None) -> dict[str, Any]:
    """检索失败、未检索、真实无命中分别呈现；事实资格仍仅来自有效引用。"""
    review = answer.evidence_review or {"checks": []}
    checks = review.get("checks", [])
    if answer.citations:
        status = "partial" if answer.dropped_citations or answer.inferences else "verified"
        message = (
            "部分说明尚未核实；已核实的代码位置可在来源中查看。"
            if status == "partial"
            else "代码引用已核对；解释和设计推断仍需结合上下文判断。"
        )
    elif knowledge_only:
        status, message = "knowledge", "依据本轮读取的教材解释，不代表项目采用了同样实现。"
    elif any(c["status"] == "unavailable" for c in checks):
        status, message = (
            "unavailable",
            "部分检索或源码读取未完成，下面的说明尚未获得项目证据支持。",
        )
    elif checks and all(c["status"] == "no_match" for c in checks):
        status, message = "no_match", "本轮查询未命中可引用位置；下面的解释或建议尚未核实。"
    else:
        status, message = (
            "unverified",
            "本轮尚未取得有效代码引用，下面的说明不能作为已核实的项目结论。",
        )
    return {
        **review,
        "status": status,
        "message": message,
        "unverified_citations": list(dict.fromkeys(answer.dropped_citations)),
        "source_version": source_version,
    }


def record_check(answer: Answer, name: str, arguments: dict, data: dict, error: str | None) -> None:
    """只登记真实定位/读取操作；结构建议工具不构成取证。"""
    if name not in {
        "search_code",
        "find_symbol",
        "read_file",
        "get_module_overview",
        "get_callers",
        "get_callees",
        "find_concept_instances",
    }:
        return
    matched = bool(data.get("citations"))
    missing = error == "not_found"
    status = "matched" if matched else "unavailable" if error and not missing else "no_match"
    review = answer.evidence_review or {"checks": []}
    review["checks"].append(
        {
            "tool": name,
            "status": status,
            "target": str(
                arguments.get("query") or arguments.get("path") or arguments.get("name") or ""
            )[:160],
        }
    )
    answer.evidence_review = review
