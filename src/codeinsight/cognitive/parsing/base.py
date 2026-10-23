"""解析层接口。

源文档 §3.2 末尾：「第一阶段优先支持 Python 项目，后续通过**可扩展的语言解析模块**
增加其他语言。」——这个 Protocol 就是那个"可扩展的模块"边界。

新增语言 = 新增一个实现类 + 在 `registry` 里注册，不改任何上层代码。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from codeinsight.models import ParsedFile


@dataclass(frozen=True)
class ParseContext:
    """解析时需要的仓库级上下文。"""

    project_id: int
    repo_root: str
    module_map: dict[str, str] = field(default_factory=dict)
    """`模块路径 -> 符号所属模块` 的已知映射，用于把调用解析到具体符号。"""


@runtime_checkable
class LanguageParser(Protocol):
    """把一个源文件解析成结构化符号与关系。"""

    language: str
    """语言标识，例如 `"python"`。"""

    def supports(self, path: str) -> bool:
        """该解析器是否处理这个路径。"""
        ...

    def parse(self, path: str, source: str, ctx: ParseContext) -> ParsedFile:
        """解析一个文件。

        必须**不抛异常**——语法错误、编码错误等应降级为「该文件产出空符号集」，
        并由调用方记录为 skipped，而不是让整次索引失败。
        """
        ...
