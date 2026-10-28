"""从现有索引生成项目导览；不调用模型、不扫描工作区推测职责。"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from codeinsight.agent.exploration import code_target, normalize, version
from codeinsight.cognitive.indexing.scanner import read_blobs


def discover(conn: sqlite3.Connection, pid: int) -> dict:
    """入口只对应真实对象；缺少某类资料时省略，不填满固定四张卡。"""
    intro = None
    rows = conn.execute(
        "SELECT f.path,c.lineno,c.body FROM chunk c JOIN file f ON f.id=c.file_id "
        "WHERE c.project_id=? AND f.role='doc' ORDER BY "
        "(lower(f.path) IN ('readme.md','readme.rst','readme.txt')) DESC, f.path,c.ordinal LIMIT 12",
        (pid,),
    ).fetchall()
    if not rows:
        # Markdown 未必有符号块；从索引绑定的 Git blob 读取，非 Git 必须核对文件哈希。
        files = conn.execute(
            "SELECT f.path,f.content_sha256,p.root_path FROM file f JOIN project p ON p.id=f.project_id WHERE f.project_id=? AND f.role='doc' ORDER BY (lower(f.path) IN ('readme.md','readme.rst','readme.txt')) DESC,f.path LIMIT 5",
            (pid,),
        ).fetchall()
        rows = []
        for item in files:
            try:
                content = read_blobs(
                    Path(item[2]), version(conn, pid)["head_commit"], [item[0]]
                ).get(item[0])
                if content and hashlib.sha256(content).hexdigest() == item[1]:
                    rows.append((item[0], 1, content.decode("utf-8", "replace")))
            except (OSError, RuntimeError, ValueError):
                # 源码不可用时不让 README 缺失阻断其他索引入口。
                continue
    for row in rows:
        paragraphs = row[2].split("\n\n")
        paragraph = next(
            (
                p.strip()
                for p in paragraphs
                if len(p.strip()) > 35
                and not p.lstrip().startswith(("#", "```", "[![", "![", "|", ".."))
            ),
            None,
        )
        if paragraph:
            before = row[2][: row[2].find(paragraph)]
            line = row[1] + before.count("\n")
            source = code_target(conn, pid, {"path": row[0], "lineno": line})
            if source:
                intro = {
                    "text": paragraph[:650],
                    "source": source,
                    "kind": "indexed_document_excerpt",
                }
                break
    actions = []
    for row in conn.execute(
        "SELECT source_path,target,kind FROM entry_point WHERE project_id=? ORDER BY id LIMIT 8",
        (pid,),
    ):
        path, name, _ = row
        if path and code_target(conn, pid, {"path": path}):
            actions.append(
                {
                    "kind": "follow_up",
                    "label": "从程序入口看它怎样启动",
                    "reason": f"从已识别入口 {name} 了解启动过程",
                    "question": f"请从项目入口 {name}（{path}）解释程序怎样启动，先建立直觉，再定位实现。",
                    "target": {"kind": "code", "path": path, "lineno": 1},
                }
            )
            break
    change = conn.execute(
        "SELECT base_commit,head_commit FROM index_run WHERE project_id=? AND ok=1 "
        "AND base_commit IS NOT NULL AND (base_commit<>head_commit OR "
        "(head_commit='' AND mode='incremental' AND files_changed>0)) ORDER BY id DESC LIMIT 1",
        (pid,),
    ).fetchone()
    if change:
        actions.append(
            {
                "kind": "follow_up",
                "label": "最近这次变更影响了什么",
                "reason": "沿已记录的索引变更核对影响",
                "question": "请解释这个项目最近一次索引变更解决了什么、哪些位置受影响，说明实现依据和仍需确认的部分。",
            }
        )
    row = conn.execute(
        "SELECT c.name,i.path,i.lineno,i.evidence FROM concept_instance i JOIN concept c ON c.id=i.concept_id WHERE i.project_id=? AND i.confidence>=0.8 AND i.evidence<>'' ORDER BY i.confidence DESC,i.path,i.lineno LIMIT 1",
        (pid,),
    ).fetchone()
    if row:
        actions.append(
            {
                "kind": "follow_up",
                "label": f"{row[0]}在这里解决什么问题",
                "reason": f"从 {row[1]} 的实际检测证据出发",
                "question": f"请结合 {row[1]} 第 {row[2]} 行解释 {row[0]} 在这里的作用，先核对实现，再讨论取舍。",
                "target": {"kind": "code", "path": row[1], "lineno": row[2]},
            }
        )
    row = conn.execute(
        "SELECT d.title,e.path,e.lineno FROM design_decision d JOIN design_decision_evidence e ON e.decision_id=d.id WHERE d.project_id=? ORDER BY d.id LIMIT 1",
        (pid,),
    ).fetchone()
    if row:
        actions.append(
            {
                "kind": "follow_up",
                "label": f"研究设计选择：{row[0]}",
                "reason": "对照设计说明与相应代码，核对是否一致",
                "question": f"设计说明“{row[0]}”记录了什么取舍？请对照 {row[1]} 的实际代码解释，若不一致请指出。",
                "target": {"kind": "code", "path": row[1], "lineno": row[2]},
            }
        )
    if not actions:
        row = conn.execute(
            "SELECT path FROM file WHERE project_id=? AND role='source' ORDER BY path LIMIT 1",
            (pid,),
        ).fetchone()
        if row:
            actions.append(
                {
                    "kind": "follow_up",
                    "label": "先读懂一份源码的职责",
                    "reason": f"从已索引文件 {row[0]} 建立起点，不预判重要性",
                    "question": f"请解释 {row[0]} 的职责、输入输出，以及它与其他代码的关系。",
                    "target": {"kind": "code", "path": row[0], "lineno": 1},
                }
            )
    # 首页最多四个，回答动作的三项上限不限制首页。
    entries = []
    for action in actions[:4]:
        entries.extend(normalize(conn, pid, {"actions": [action]})["actions"])
    return {**version(conn, pid), "project_intro": intro, "exploration_entries": entries}
