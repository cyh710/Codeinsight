"""从 CodeInsight 自身定位知识资产，不搜索被分析仓库或进程工作目录。"""

from __future__ import annotations

from pathlib import Path

from codeinsight.cognitive.concepts.learning_models import KnowledgeError


def knowledge_directory(kind: str) -> Path:
    """优先使用安装包内资产，其次为源码树资产；不存在时报告安装缺口。

    wheel 的 force-include 目标约定是 codeinsight/knowledge/{kind}，由请求 0001
    的 A 线打包配置落实。显式资产路径仍可直接传给 LearningLibrary/load_ontology。
    """
    if kind not in {"learning", "concepts"}:
        raise KnowledgeError("知识目录类型只允许 learning 或 concepts")
    package = Path(__file__).resolve().parents[2]
    candidates = (package / "knowledge" / kind, package.parents[1] / "knowledge" / kind)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise KnowledgeError(f"CodeInsight 安装缺少 {kind} 知识资产，请检查构建配置。")
