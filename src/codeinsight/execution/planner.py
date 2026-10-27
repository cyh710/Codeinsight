"""计划器：对话内识别开发任务 + 生成执行计划（请求 0018）。

成本纪律：识别不是每个问题都付一次模型调用——先用廉价的词法闸门
（开发动词/祈使句式），只有闸门放行的才做一次小 LLM 确认。
任何失败都降级为"普通问答"（返回 False / 最小计划），识别宁可漏判
不可误判：误判会把用户的一句话变成一个待批准的执行任务。
"""

from __future__ import annotations

import re
from typing import Any

from codeinsight.llm.provider import LLMProvider
from codeinsight.llm.response_parser import extract_json

# 词法闸门：开发/修补意图的强信号（中英）。命中才进入 LLM 确认。
_DEV_SIGNAL = re.compile(
    r"(帮我|请|给我|麻烦).{0,12}(改|修|加|删|实现|重构|优化|修复|写|抽|补|迁移|升级)"
    r"|(修复|修正|实现|重构|优化|抽离|补上|加上|删掉|去掉|迁移|升级)"
    r"|(\bfix\b|\badd\b|\bimplement\b|\brefactor\b|\bchange\b|\bupdate\b"
    r"|\bcreate\b|\bremove\b|\bdelete\b|\bmigrate\b)",
    re.IGNORECASE,
)

# 明确的问答信号：即使带"改"字也是想理解，不是想动手。
_ASK_SIGNAL = re.compile(r"(在哪|在哪里|是什么|是什么意思|为什么|怎么(实现|工作|走|处理)的"
                         r"|区别|原理|解释|讲讲|介绍|what|why|how does|where is)", re.IGNORECASE)


def gate_is_dev_task(question: str) -> bool:
    """廉价预判：开发信号命中且无压倒性问答信号。"""
    if _ASK_SIGNAL.search(question) and not re.search(r"(帮我|请|给我)改", question):
        return False
    return bool(_DEV_SIGNAL.search(question))


async def classify(question: str, provider: LLMProvider) -> bool:
    """LLM 确认是否开发任务。任何异常/坏输出都返回 False（安全降级）。"""
    system = (
        "你是意图分类器。判断用户这句话是想【让你动手改代码】（dev_task），"
        "还是【问关于代码的问题】（answer）。只输出 JSON：{\"dev_task\": true} 或 {\"dev_task\": false}。"
        "拿不准时输出 false。"
    )
    try:
        raw = await provider.complete(system, [{"role": "user", "content": question}], max_tokens=16)
        obj = extract_json(raw)
        return bool(obj.get("dev_task")) if isinstance(obj, dict) else False
    except Exception:  # 分类失败不该挡住问答（ADR 0012 同理）
        return False


def normalize_plan(obj: Any, question: str) -> dict:
    """模型输出的计划 → 规范形状；缺字段给可用的最小值。"""
    if not isinstance(obj, dict):
        obj = {}
    files = [str(f) for f in obj.get("files", []) if isinstance(f, str)][:12]
    risks = [str(r) for r in obj.get("risks", []) if isinstance(r, str)][:6]
    return {
        "intent": str(obj.get("intent") or question)[:300],
        "files": files,
        "approach": str(obj.get("approach") or "")[:1200],
        "risks": risks,
    }


async def build_plan(
    question: str, provider: LLMProvider, context_block: str
) -> dict:
    """生成执行计划。失败时返回最小计划（只有意图），由用户决定批不批。"""
    system = (
        "你是开发任务规划器。基于给定的项目上下文，为用户需求生成执行计划。"
        '只输出 JSON：{"intent": "一句话意图", "files": ["要动的文件"], '
        '"approach": "实现思路，几句话", "risks": ["风险点"]}。'
        "files 来自上下文里的真实路径；不确定就给空数组，不要编。"
    )
    prompt = f"## 需求\n{question}\n\n## 项目上下文（索引检索结果，可信）\n{context_block or '（无）'}"
    try:
        raw = await provider.complete(system, [{"role": "user", "content": prompt}], max_tokens=800)
        return normalize_plan(extract_json(raw), question)
    except Exception:
        return normalize_plan({}, question)
