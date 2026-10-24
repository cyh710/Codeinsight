"""从教材正文里去掉面向发布者的样板话。

两处：
1. 「以下是独立教学示例，不代表被分析项目的实际代码。」——每篇都有，
   是给审计看的免责，读者不需要。
2. 「## 来源与版本」里的声明段——那是面向发布者的许可说明，
   读者要的是下面那份来源清单（作者 / 许可 / 版本 / 哈希）。

来源清单本身保留：读者要知道这篇文章改编自哪里。

用法：python tools/clean_article_boilerplate.py [--check]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTICLES = ROOT / "knowledge" / "learning" / "articles"

# 章节开头的免责样板句（66 篇一字不差）
TEACHING_CAVEAT = "以下是独立教学示例，不代表被分析项目的实际代码。\n"

# 来源章节里面向发布者的声明段
SOURCE_NOTICE = (
    "本文为参考下列资料独立组织的中文教学讲解，示例为本项目编写。"
    "不把原文示例描述为用户项目事实。"
    "借鉴、翻译及改编部分保留相应来源许可；"
    "含 CC BY-SA 的文章文本按 CC BY-SA 4.0 分发，与应用代码许可分开。\n"
)


def clean(text: str) -> tuple[str, list[str]]:
    """返回 (清理后的正文, 被删掉的行)。"""
    removed: list[str] = []
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == TEACHING_CAVEAT.strip():
            removed.append(stripped)
            continue
        if stripped == SOURCE_NOTICE.strip():
            removed.append(stripped)
            continue
        out.append(line)
    return "".join(out), removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只报告，不改文件")
    args = parser.parse_args()

    files = sorted(ARTICLES.rglob("*.md"))
    changed = 0
    total_removed = 0
    for path in files:
        original = path.read_text(encoding="utf-8")
        cleaned, removed = clean(original)
        if not removed:
            continue
        changed += 1
        total_removed += len(removed)
        # 删掉样板句后可能留下连续空行，压成一个
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        if not args.check:
            path.write_text(cleaned, encoding="utf-8")
        print(f"{path.relative_to(ROOT)}: 删 {len(removed)} 处")

    print(f"\n合计 {changed}/{len(files)} 篇，删掉 {total_removed} 处样板话")
    if args.check and changed:
        print("（--check 模式，未写文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
