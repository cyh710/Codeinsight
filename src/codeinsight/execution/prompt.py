"""执行 prompt 组装：需求 + 计划 + 项目认知上下文 + 边界指令。

给执行 agent 的上下文来自 CodeInsight 的索引（检索命中的符号/文件），
这是"编排外部 agent"相对用户直接开 Claude Code 的差异化：它带着
项目认知干活，而不是盲 grep。边界指令是硬约束，放 prompt 末尾
（长上下文里首尾权重最高）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBundle:
    """计划阶段从索引取出的认知上下文（文本块，供 LLM 与执行 agent 共用）。"""

    requirement: str
    plan_json: dict
    symbols_block: str = ""
    conventions: str = ""


def build_task_prompt(bundle: ContextBundle, *, commit_message: str) -> str:
    plan = bundle.plan_json
    files = "\n".join(f"- {f}" for f in plan.get("files", [])) or "-（由你判断）"
    risks = "\n".join(f"- {r}" for r in plan.get("risks", [])) or "-（无）"

    parts = [
        "## 任务",
        bundle.requirement.strip(),
        "",
        "## 执行计划（已经用户批准，按此执行；发现计划有误时停下来在结果里说明，不要自行改需求）",
        f"意图：{plan.get('intent', '')}",
        f"思路：{plan.get('approach', '')}",
        f"预计要动的文件：\n{files}",
        f"风险：\n{risks}",
    ]
    if bundle.symbols_block.strip():
        parts += ["", "## 相关代码认知（来自项目索引，可信的 file:line）", bundle.symbols_block.strip()]
    if bundle.conventions.strip():
        parts += ["", "## 仓库作业约定", bundle.conventions.strip()]
    parts += [
        "",
        "## 硬性边界",
        "1. 只在当前目录（这是一份隔离检出）里工作；不要 push，不要切分支。",
        "2. 完成后用 `git add -A && git commit -m '" + commit_message + "'` 提交全部改动。",
        "3. 只做本任务；顺手重构、格式化无关文件一律不做。",
        "4. 最后输出一段中文总结：改了什么、为什么这样改、还有什么没做。",
    ]
    return "\n".join(parts)
