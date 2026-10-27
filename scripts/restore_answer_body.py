"""单回合恢复工具；默认只读预览，--apply 才备份并更新指定回合。"""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from codeinsight.agent.answer_recovery import apply_answer_restoration, prepare_answer_restoration


def main() -> None:
    """调用方必须明确给出数据库及项目、会话、请求身份，不自动查找其他历史。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--project", type=int, required=True)
    parser.add_argument("--conversation", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    path = args.db.resolve()
    uri = path.as_uri() + ("?mode=rw" if args.apply else "?mode=ro")
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=5)) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            plan = prepare_answer_restoration(conn, args.project, args.conversation, args.request)
            result = {**plan.summary(), "applied": False}
            if args.apply:
                backup = apply_answer_restoration(conn, plan, path.parent / "backups")
                result.update(applied=backup is not None, backup=str(backup) if backup else None)
            print(json.dumps(result, ensure_ascii=False))
    except (ValueError, sqlite3.Error, OSError) as exc:
        parser.exit(1, f"恢复未执行：{exc}\n")


if __name__ == "__main__":
    main()
