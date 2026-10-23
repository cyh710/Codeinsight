"""固定参考资料及许可的源快照；不导入第三方可执行代码。

从仓库根运行 python -m codeinsight.cognitive.concepts.examples.import_sources。
原始资料进入 gitignore 的 .ci/source-snapshots；分发清单和许可进入学习资产。
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

SOURCES = (
    (
        "byte-python",
        "A Byte of Python",
        "Swaroop C H",
        "https://python.swaroopch.com/",
        "CC-BY-SA-4.0",
        "https://creativecommons.org/licenses/by-sa/4.0/",
        "Python 3；网页快照",
    ),
    (
        "python",
        "Python 3.13 教程与标准库",
        "Python Software Foundation",
        "https://docs.python.org/3.13/tutorial/",
        "PSF-2.0",
        "https://docs.python.org/3.13/license.html",
        "Python 3.13",
    ),
    (
        "mdn",
        "MDN Web Docs：学习 Web 开发",
        "Mozilla Contributors",
        "https://developer.mozilla.org/zh-CN/docs/Learn_web_development",
        "CC-BY-SA-4.0",
        "https://developer.mozilla.org/en-US/docs/MDN/Writing_guidelines/Attrib_copyright_license",
        "MDN；导入日网页快照（按 2.5 或以后版本许可选用 4.0）",
    ),
    (
        "typescript",
        "TypeScript Handbook",
        "Microsoft Corporation and contributors",
        "https://www.typescriptlang.org/docs/handbook/intro.html",
        "CC-BY-4.0",
        "https://raw.githubusercontent.com/microsoft/TypeScript-Website/v2/LICENSE",
        "Handbook；导入日网页快照",
    ),
    (
        "react",
        "React 中文文档",
        "React contributors and Chinese translators",
        "https://zh-hans.react.dev/learn",
        "CC-BY-4.0",
        "https://raw.githubusercontent.com/reactjs/zh-hans.react.dev/main/LICENSE-DOCS.md",
        "React 19；导入日网页快照",
    ),
    (
        "postgres",
        "PostgreSQL Tutorial",
        "PostgreSQL Global Development Group",
        "https://www.postgresql.org/docs/18/tutorial.html",
        "PostgreSQL",
        "https://www.postgresql.org/docs/18/legalnotice.html",
        "PostgreSQL 18",
    ),
    (
        "fastapi",
        "FastAPI：依赖注入与安全",
        "Sebastián Ramírez and contributors",
        "https://fastapi.tiangolo.com/tutorial/dependencies/",
        "MIT",
        "https://raw.githubusercontent.com/fastapi/fastapi/master/LICENSE",
        "导入日网页快照",
    ),
    (
        "redis",
        "Redis Python client documentation",
        "Redis contributors",
        "https://redis.readthedocs.io/en/stable/examples.html",
        "MIT",
        "https://raw.githubusercontent.com/redis/redis-py/master/LICENSE",
        "导入日网页快照",
    ),
    (
        "sqlalchemy",
        "SQLAlchemy ORM and Core",
        "SQLAlchemy authors and contributors",
        "https://docs.sqlalchemy.org/en/20/intro.html",
        "MIT",
        "https://raw.githubusercontent.com/sqlalchemy/sqlalchemy/main/LICENSE",
        "SQLAlchemy 2.0",
    ),
    (
        "pyjwt",
        "PyJWT usage",
        "José Padilla and contributors",
        "https://pyjwt.readthedocs.io/en/stable/usage.html",
        "MIT",
        "https://raw.githubusercontent.com/jpadilla/pyjwt/master/LICENSE",
        "导入日网页快照",
    ),
    (
        "filelock",
        "filelock tutorial",
        "filelock contributors",
        "https://py-filelock.readthedocs.io/en/latest/",
        "Unlicense",
        "https://raw.githubusercontent.com/tox-dev/filelock/main/LICENSE",
        "导入日网页快照",
    ),
    (
        "tenacity",
        "Tenacity documentation",
        "Julien Danjou and contributors",
        "https://tenacity.readthedocs.io/en/latest/",
        "Apache-2.0",
        "https://raw.githubusercontent.com/jd/tenacity/main/LICENSE",
        "导入日网页快照",
    ),
    (
        "blinker",
        "Blinker documentation",
        "Jason Kirtland and contributors",
        "https://blinker.readthedocs.io/en/stable/",
        "MIT",
        "https://raw.githubusercontent.com/pallets-eco/blinker/main/LICENSE.txt",
        "导入日网页快照",
    ),
)


def fetch(url: str) -> bytes:
    """下载公开来源；网络失败明确退出，绝不写入伪造的哈希。"""
    request = urllib.request.Request(
        url, headers={"User-Agent": "CodeInsight-learning-source-audit/0.1"}
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def main() -> None:
    """只由维护者显式运行；普通加载、检索和测试均不访问网络。"""
    root = Path.cwd()
    cache = root / ".ci" / "source-snapshots"
    destination = root / "knowledge" / "learning"
    licenses = destination / "licenses"
    cache.mkdir(parents=True, exist_ok=True)
    licenses.mkdir(parents=True, exist_ok=True)
    manifest = []
    for sid, title, author, url, license_name, license_url, version in SOURCES:
        cached = sorted(cache.glob(f"{sid}-*.html"))
        snapshot = cached[0].read_bytes() if len(cached) == 1 else fetch(url)
        digest = hashlib.sha256(snapshot).hexdigest()
        (cache / f"{sid}-{digest}.html").write_bytes(snapshot)
        license_path = licenses / f"{sid}.txt"
        if not license_path.exists():
            license_path.write_bytes(fetch(license_url))
        manifest.append(
            {
                "id": sid,
                "title": title,
                "author": author,
                "url": url,
                "version": f"{version}; sha256:{digest}",
                "license": license_name,
                "license_url": license_url,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "sha256": digest,
                "modifications": "中文重新组织、教学示例与工程关联；不是原站全文镜像。各篇正文保留对应许可与来源。",
            }
        )
        (destination / "sources.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{sid}: {digest[:12]}", flush=True)
    (destination / "sources.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, urllib.error.URLError) as exc:
        raise SystemExit(f"来源导入未完成（已保存成功部分，重跑可续接）：{exc}") from exc
