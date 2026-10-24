"""重生成前端的 mock 数据（C 线自用工具，产物只写 frontend/public/mock/）。

背景：A 线的 `ci dump-fixture` 快照导出器还不带概念检测（`concepts`/`flows`
写死为空），但 B 线检测器与 A5 流程检测都已合入。mock 模式想要真实的概念 /
流程数据，又不能去改 `fixtures/`（A 线车道）——所以本工具用真引擎对目标仓库
建一次索引（临时库），把三样东西并进前端自己的快照副本：

1. `concepts`   —— concept_instance 表 → 快照既定形状（fixtures/README）
2. `flows`      —— flow / flow_step 表 → 快照既定形状
3. `ontology.json`（新文件）—— knowledge/concepts/*.yaml 拍平成 JSON，
   mock 的概念卡（quick/project 级解释）从本体读 summary/tradeoffs。

用法（仓库根目录）：

    uv run python frontend/tools/regen_mock.py \
        --repo "D:/path/to/some-repo" --ref agent-v1

写完后 `npm run test` 里读真实快照的用例会自动拿到新数据。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MOCK_DIR = REPO_ROOT / "frontend" / "public" / "mock"


def build_index_snapshot(repo: Path, ref: str | None) -> tuple[dict, Path]:
    """对目标仓库跑一次真索引（临时库），返回 concept/flow 原材料。"""
    import sys

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from codeinsight.cognitive.indexing import index_project

    tmp = Path(tempfile.mkdtemp(prefix="ci-mock-"))
    db = tmp / "index.db"
    index_project(
        db,
        root=repo,
        name="tapestry",
        ref=ref,
        concepts_dir=REPO_ROOT / "knowledge" / "concepts",
    )
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn, tmp


def extract_concepts(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT concept_id, path, lineno, qualname, evidence, confidence"
        " FROM concept_instance ORDER BY path, lineno"
    ).fetchall()
    return [dict(r) for r in rows]


def extract_flows(conn: sqlite3.Connection) -> list[dict]:
    flows: list[dict] = []
    for f in conn.execute(
        "SELECT fl.id, fl.name, fl.description, s.qualname AS entry"
        " FROM flow fl LEFT JOIN symbol s ON s.id = fl.entry_symbol_id"
        " WHERE fl.project_id = (SELECT MIN(id) FROM project) ORDER BY fl.id"
    ).fetchall():
        steps = [
            {"ordinal": s["ordinal"], "qualname": s["qualname"], "path": s["path"], "lineno": s["lineno"], "note": s["note"]}
            for s in conn.execute(
                "SELECT ordinal, qualname, path, lineno, note FROM flow_step"
                " WHERE flow_id = ? ORDER BY ordinal",
                (f["id"],),
            ).fetchall()
        ]
        flows.append(
            {
                "name": f["name"],
                "description": f["description"] or "",
                "entry_qualname": f["entry"] or (steps[0]["qualname"] if steps else None),
                "steps": steps,
            }
        )
    return flows


def extract_ontology() -> dict:
    """把 B 线本体 YAML 拍平成 JSON（浏览器端不引 yaml 依赖）。"""
    out: dict[str, dict] = {}
    for path in sorted((REPO_ROOT / "knowledge" / "concepts").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "id" not in data:
            continue
        out[data["id"]] = {
            "concept_id": data["id"],
            "name": data.get("name", data["id"]),
            "category": data.get("category", "other"),
            "summary": data.get("summary", ""),
            "principles": data.get("principles") or "",
            "tradeoffs": data.get("tradeoffs") or "",
            "alternatives": data.get("alternatives") or "",
            "references": data.get("references") or [],
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--ref", default=None)
    args = parser.parse_args()

    conn, tmp = build_index_snapshot(Path(args.repo), args.ref)
    try:
        concepts = extract_concepts(conn)
        flows = extract_flows(conn)
    finally:
        conn.close()

    snapshot_path = MOCK_DIR / "sample-index.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    # 只动 concepts/flows 两个此前为空的槽位，其余（文件/符号/边）保持
    # 与 A 线快照一致——来源仍是真实解析，不手写。
    # 快照的文件列表是全量、符号与边是分层取样；实例挂在符号上，样本外
    # 的 qualname 在 mock 里点过去就是 404——引用完整性比数量重要，
    # 只保留 qualname 命中样本符号的实例（文件级实例没有 qualname，保留）。
    sampled_qualnames = {s["qualname"] for s in snapshot["symbols"]}
    concepts = [c for c in concepts if not c.get("qualname") or c["qualname"] in sampled_qualnames]
    # flows 不按符号过滤：流程天然跨模块，按 qualname 过滤会把所有流程
    # 整条砍掉；步骤的 path 都在（文件列表是全量），前端目前也没有
    # 从流程步骤跳符号的交互，真实数据留给未来的流程视图。
    snapshot["concepts"] = concepts
    snapshot["flows"] = flows
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (MOCK_DIR / "ontology.json").write_text(
        json.dumps(extract_ontology(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"→ {snapshot_path}（concepts×{len(concepts)}，flows×{len(flows)}）")
    print(f"→ {MOCK_DIR / 'ontology.json'}")
    import shutil

    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
