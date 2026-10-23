"""索引层：扫描 → 解析 → 符号/边落库 → 切块。

分层的原因（源文档 §2.1）：每一步都能单独验证——
扫描对不对、解析准不准、边抽全没抽全、切块合不合理，是四个不同的问题。

模块一览：

- `scanner`   —— 文件树与角色分类（ADR 0014 / ADR 0015）
- `python_parser` 在 `cognitive.parsing` —— AST → 符号与边
- `symbols`   —— 符号落库 + 全局符号表
- `edges`     —— 边落库 + 名字解析
- `entries`   —— 入口与依赖识别
- `chunker`   —— 按符号边界切块
- `indexer`   —— 把上面这些串成一次索引
"""

from codeinsight.cognitive.indexing.indexer import IndexResult, index_project

__all__ = ["IndexResult", "index_project"]
