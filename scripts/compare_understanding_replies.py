"""冻结实际索引和两版代码后，各运行固定五题；不重试、不修改用户资料。

先 --prepare，再分别 --variant baseline/candidate。产物含项目源码，仅保存在
gitignore 的 .ci 中；报告可引用摘要，不能将原始项目材料自动加入提交。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
from dataclasses import asdict
from pathlib import Path

QUESTIONS = [
    "我想了解一下现在已有的策略和成绩。",
    "doc_diverse 与 doc_grouped 的取舍是什么？",
    "一次查询从输入到检索结果怎样流动？",
    "什么是检索召回，结合上述过程解释。",
    "还是听不懂，doc_grouped 改变的是哪一步？",
]
PRIOR = (
    "这里先把证据组织理解成：检索之后，把候选片段整理成给生成模型阅读的上下文。"
    "接下来要核对 doc_grouped 如何完成这一步。"
)
QUERY_PROCESS = "一次查询先交给检索器取得候选片段，再选择和组织证据，最后交给生成模型。接下来区分检索召回与证据选择的作用。"


def digest(content: bytes) -> str:
    """哈希只标识实际输入，不用估算文本相似度。"""
    return hashlib.sha256(content).hexdigest()


def save(path: Path, value: object) -> None:
    """原始评估材料只写入调用方明确指定的本地目录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_target(root: Path, relative: str) -> Path:
    """拒绝离开快照根目录的源码或归档路径。"""
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("快照路径超出指定目录")
    return target


def prepare(repo: Path, directory: Path, project: int) -> None:
    """SQLite backup 与文件哈希共同冻结非 Git 项目，不重新索引。"""
    if directory.exists():
        raise ValueError("评估目录已存在，不覆盖已有记录")
    directory.mkdir(parents=True)
    # 配置只在内存读取，不输出密钥或完整 settings。
    sys.path.insert(0, str(repo / "src"))
    from codeinsight.config import settings

    db = settings.data_dir / "codeinsight.db"
    frozen = sqlite3.connect(directory / "snapshot.db")
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as source:
        source.backup(frozen)
    row = frozen.execute(
        "SELECT p.name,p.root_path,r.head_commit,r.index_epoch FROM project p "
        "JOIN repo_state r ON r.project_id=p.id WHERE p.id=?",
        (project,),
    ).fetchone()
    if not row or row[2]:
        raise ValueError("本脚本的实测案例要求现有的非 Git 项目快照")
    manifest = []
    for relative, expected in frozen.execute(
        "SELECT path,content_sha256 FROM file WHERE project_id=? ORDER BY path",
        (project,),
    ).fetchall():
        original = safe_target(Path(row[1]), relative)
        content = original.read_bytes()
        actual = digest(content)
        origin = "working_file"
        if actual != expected:
            # 只从内层仓库的现有对象恢复完全匹配的字节，不猜测性修复换行。
            parts = Path(relative).parts
            for boundary in range(len(parts) - 1, 0, -1):
                nested = Path(row[1]).joinpath(*parts[:boundary])
                if not (nested / ".git").exists():
                    continue
                blob = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(nested),
                        "show",
                        "HEAD:" + Path(*parts[boundary:]).as_posix(),
                    ],
                    capture_output=True,
                    check=False,
                )
                if blob.returncode == 0 and digest(blob.stdout) == expected:
                    content = blob.stdout
                    origin = "hash_matched_git_object"
                    break
            if digest(content) != expected:
                origin = "stale_source_preserved"
        target = safe_target(directory / "source", relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        manifest.append(
            {
                "path": relative,
                "indexed_sha256": expected,
                "disk_sha256": actual,
                "snapshot_sha256": digest(content),
                "origin": origin,
            }
        )
    frozen.execute(
        "UPDATE project SET root_path=? WHERE id=?", (str(directory / "source"), project)
    )
    frozen.commit()
    frozen.close()
    baseline = subprocess.check_output(
        ["git", "archive", "4355a3e", "src", "knowledge"],
        cwd=repo,
    )
    with tarfile.open(fileobj=io.BytesIO(baseline)) as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            target = safe_target(directory / "baseline", member.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
    files = (
        subprocess.check_output(["git", "ls-files", "src", "knowledge"], cwd=repo)
        .decode()
        .splitlines()
    )
    candidate_files = []
    for relative in files:
        content = (repo / relative).read_bytes()
        target = safe_target(directory / "candidate", relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        candidate_files.append({"path": relative, "sha256": digest(content)})
    save(
        directory / "manifest.json",
        {
            "project_id": project,
            "project_name": row[0],
            "head_commit": row[2],
            "index_epoch": row[3],
            "baseline_commit": "4355a3e",
            "source_files": manifest,
            "candidate_files": candidate_files,
            "questions": QUESTIONS,
            "fixed_prior": PRIOR,
            "executor": "off",
            "retries": 0,
            "retrieval": "bm25/symbol/concept; dense disabled equally to avoid embedding calls",
            "model": settings.llm_model,
            "temperature": 0.0,
            "max_tokens": 2000,
            "usage": "production streaming provider does not expose usage; no estimated cost",
        },
    )
    print(
        json.dumps(
            {
                "prepared": str(directory),
                "source_files": len(manifest),
                "stale_sources": [
                    f["path"] for f in manifest if f["origin"] == "stale_source_preserved"
                ],
                "recovered_objects": sum(
                    f["origin"] == "hash_matched_git_object" for f in manifest
                ),
            },
            ensure_ascii=False,
        )
    )


def seed_history(conn, project: int, cid: str, number: int, prior: str) -> None:
    """固定前文必须进入实际 SQLite 历史，避免与续讲目标解析互相矛盾。"""
    from codeinsight.agent.exploration import version
    from codeinsight.storage.conversations import ConversationRepository

    repo = ConversationRepository(conn)
    repo.create(project, cid)
    if number not in (4, 5):
        return
    question = QUESTIONS[2] if number == 4 else QUESTIONS[1]
    text = QUERY_PROCESS if number == 4 else prior
    repo.reserve(project, cid, "fixed-prior", question, None)
    repo.event(
        project,
        cid,
        "fixed-prior",
        "answer",
        {
            "text": text,
            "citations": [],
            "knowledge_sources": [],
            "evidence_review": {"source_version": version(conn, project)},
        },
    )
    repo.event(project, cid, "fixed-prior", "done", {})


async def run(directory: Path, variant: str, corrected_context: bool = False) -> None:
    """每题只执行一次真实运行；记录全部工具与流，不额外评分或润色。"""
    code = directory / variant
    sys.path.insert(0, str(code / "src"))
    from codeinsight.agent.service import build_provider, open_agent
    from codeinsight.config import settings
    from codeinsight.llm import transport
    from codeinsight.llm.openai_compat import OpenAICompatProvider
    from codeinsight.storage.conversations import PersistentConversationStore

    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if settings.llm_model != manifest["model"]:
        raise ValueError("模型配置已变化，未启动评估")
    settings.executor = "off"
    transport._MAX_ATTEMPTS = 1
    output = directory / (
        f"{variant}-corrected-context" if corrected_context else f"{variant}-results"
    )
    if output.exists():
        raise ValueError("该版本已有评估记录，不自动重跑")
    output.mkdir()
    shutil.copyfile(directory / "snapshot.db", output / "index.db")
    provider_config = build_provider()

    class RecordedProvider(OpenAICompatProvider):
        def __init__(self, folder: Path):
            super().__init__(
                base_url=provider_config.base_url,
                api_key=provider_config.api_key,
                model=provider_config.model,
                timeout_s=provider_config.timeout_s,
            )
            self.folder = folder
            self.requests = 0
            self.systems: list[str] = []

        def _payload(self, system, messages, **kwargs):
            payload = super()._payload(system, messages, **kwargs)
            self.requests += 1
            self.systems.append(digest(system.encode()))
            save(self.folder / f"request-{self.requests:03d}.json", payload)
            return payload

        async def stream_with_tools(self, *args, **kwargs):
            number = self.requests + 1
            async for chunk in super().stream_with_tools(*args, **kwargs):
                with (self.folder / f"response-{number:03d}.jsonl").open(
                    "a", encoding="utf-8"
                ) as stream:
                    stream.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")
                yield chunk

        async def complete(self, *args, **kwargs):
            number = self.requests + 1
            text = await super().complete(*args, **kwargs)
            save(self.folder / f"response-{number:03d}.json", {"text": text})
            return text

    class NoEmbedding:
        enabled = False

    summaries = []
    for number, question in enumerate(manifest["questions"], 1):
        if corrected_context and number not in (4, 5):
            continue
        folder = output / f"q{number}"
        folder.mkdir()
        provider = RecordedProvider(folder)
        session = open_agent(
            output / "index.db",
            manifest["project_id"],
            provider=provider,
            embedder=NoEmbedding(),
            concepts_dir=code / "knowledge/concepts",
        )
        cid = f"evaluation-q{number}"
        seed_history(session.conn, manifest["project_id"], cid, number, manifest["fixed_prior"])
        session.runtime.store = PersistentConversationStore(session.conn)
        save(
            folder / "fixed-history.json",
            session.runtime.store.history(f"{manifest['project_id']}:{cid}"),
        )
        started = time.monotonic()
        try:

            async def emit(event, event_file=folder / "events.jsonl"):
                with event_file.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

            answer = await session.runtime.run(
                project_id=manifest["project_id"],
                question=question,
                conversation_id=cid,
                emit=emit,
            )
            save(folder / "answer.json", asdict(answer))
            (folder / "answer.md").write_text(answer.text, encoding="utf-8")
            save(
                folder / "tools.json",
                [
                    dict(row)
                    for row in session.conn.execute(
                        "SELECT type,payload_json FROM agent_event WHERE task_id=? ORDER BY id",
                        (answer.task_id,),
                    )
                ],
            )
            result = {
                "question": question,
                "requests": provider.requests,
                "seconds": round(time.monotonic() - started, 2),
                "incomplete": answer.incomplete,
                "error": answer.error,
                "characters": len(answer.text),
                "system_prompt_sha256": provider.systems,
            }
            summaries.append(result)
            save(output / "summary.json", summaries)
            print(
                json.dumps({"variant": variant, "number": number, **result}, ensure_ascii=False),
                flush=True,
            )
        finally:
            session.close()
    await transport.close_http_client()


def main() -> None:
    """命令行明确区分快照准备和有真实模型调用的执行。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--project", type=int, default=6)
    parser.add_argument(
        "--corrected-context",
        action="store_true",
        help="仅在用户明确批准补跑后使用；只运行第4/5题，保留原始十条",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--variant", choices=["baseline", "candidate"])
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    directory = args.directory.resolve()
    if not directory.is_relative_to((repo / ".ci").resolve()):
        raise ValueError("评估必须保存在本仓 .ci 内的独立目录")
    if args.prepare:
        prepare(repo, directory, args.project)
    else:
        asyncio.run(run(directory, args.variant, args.corrected_context))


if __name__ == "__main__":
    main()
