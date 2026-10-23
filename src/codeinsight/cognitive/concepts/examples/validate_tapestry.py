"""固定 git ref 的离线检测审核；不读取目标工作区，不调用任何模型。

用 A 线的实际解析器文件验证全量 Python blob，解析器不复制进 B 分支。
产出命中、源码审核样本与缺失输入，不冒充人工精确率/完整召回率结论。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

from codeinsight.cognitive.concepts.base import EdgeView, SymbolView
from codeinsight.cognitive.concepts.detector import RuleBasedDetector
from codeinsight.cognitive.concepts.ontology import detection_version, load_ontology
from codeinsight.cognitive.parsing.base import ParseContext


def _git(root: Path, *args: str, data: bytes | None = None) -> bytes:
    proc = subprocess.run(["git", "-C", str(root), *args], input=data, capture_output=True)
    if proc.returncode:
        raise ValueError(proc.stderr.decode("utf-8", "replace"))
    return proc.stdout


def validate(repo: Path, ref: str, parser_file: Path, knowledge_root: Path, output: Path) -> dict:
    """检查固定 ref 的所有 Python 文件；审核样本不是独立人工 gold set。"""
    commit = _git(repo, "rev-parse", f"{ref}^{{commit}}").decode().strip()
    spec = importlib.util.spec_from_file_location("_audit_python_parser", parser_file)
    if spec is None or spec.loader is None:
        raise ValueError("无法加载 A 线实际解析器")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    parser = module.PythonParser()
    paths = [
        p.decode("utf-8")
        for p in _git(
            repo, "-c", "core.quotepath=false", "ls-tree", "-r", "-z", "--name-only", commit
        ).split(b"\0")
        if p.endswith((b".py", b".pyi"))
    ]
    requests = "".join(f"{commit}:{path}\n" for path in paths).encode()
    stream = _git(repo, "cat-file", "--batch", data=requests)
    position = 0
    sources: dict[str, str] = {}
    for path in paths:
        end = stream.index(b"\n", position)
        header = stream[position:end].split()
        size = int(header[-1])
        position = end + 1
        sources[path] = stream[position : position + size].decode("utf-8", "replace")
        position += size + 1
    symbol_count = 0
    edge_count = 0
    concepts = load_ontology(knowledge_root / "concepts")
    detector = RuleBasedDetector(concepts)
    instances = []
    errors = []
    skipped = []
    ctx = ParseContext(project_id=1, repo_root=str(repo))
    for number, (path, source) in enumerate(sources.items(), 1):
        symbols = []
        edges = []
        confidence = {}
        parsed = parser.parse(path, source, ctx)
        if not parsed.symbols:
            skipped.append(path)
        for s in parsed.symbols:
            symbols.append(
                SymbolView(
                    s.qualname, s.name, s.kind, path, s.lineno, s.end_lineno, s.header, s.docstring
                )
            )
        for e in parsed.edges:
            edges.append(
                EdgeView(e.src_qualname, e.dst_name, e.kind, path, e.lineno, e.dst_qualname)
            )
            confidence[(path, e.lineno, str(e.kind), e.dst_name)] = e.confidence
        symbol_count += len(symbols)
        edge_count += len(edges)
        instances.extend(
            detector.detect(symbols, edges, sources={path: source}, edge_confidences=confidence)
        )
        errors.extend(detector.errors)
        if number % 50 == 0:
            print(f"已解析/检测 {number}/{len(paths)} 个冻结文件", flush=True)
    groups = defaultdict(list)
    for instance in instances:
        if instance.confidence >= 0.8:
            groups[instance.concept_id].append(instance)
    samples = []
    queues = {key: iter(value) for key, value in sorted(groups.items())}
    while queues and len(samples) < 30:
        for key in list(queues):
            instance = next(queues[key], None)
            if instance is None:
                del queues[key]
                continue
            lines = sources[instance.path].splitlines()
            start = max(1, instance.lineno - 2)
            end = min(len(lines), instance.lineno + 3)
            samples.append(
                {
                    **asdict(instance),
                    "source_excerpt": "\n".join(
                        f"{line}: {lines[line - 1]}" for line in range(start, end + 1)
                    ),
                    "review_status": "pending_human_review",
                    "label": None,
                }
            )
            if len(samples) == 30:
                break
    report = {
        "head_commit": commit,
        "ref": ref,
        "parser_file": str(parser_file),
        "parser_sha256": hashlib.sha256(parser_file.read_bytes()).hexdigest(),
        "models_sha256": hashlib.sha256(
            Path(sys.modules["codeinsight.models"].__file__).read_bytes()
        ).hexdigest(),
        "codeinsight_commit": _git(Path.cwd(), "rev-parse", "HEAD").decode().strip(),
        "scope": "全量 Python；包含测试与第三方，按文件角色供审核过滤；不是索引器的排除规则验收",
        "python_files": len(paths),
        "symbols": symbol_count,
        "edges": edge_count,
        "skipped": skipped,
        "detection_version": detection_version(concepts),
        "concept_counts": dict(Counter(i.concept_id for i in instances)),
        "confident_counts": {key: len(value) for key, value in groups.items()},
        "instances": [asdict(i) for i in instances],
        "review_samples": samples,
        "errors": errors,
        "provider_calls": 0,
        "human_precision": None,
        "recall": None,
        "limitations": "30 条样本待人工标注；未建立完整负例集，不能报告召回率或准确率达标。",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    """只读目标仓库并写出明确指定的本地审核文件。"""
    arg = argparse.ArgumentParser(description=__doc__)
    arg.add_argument("--repo", type=Path, required=True)
    arg.add_argument("--ref", default="agent-v1")
    arg.add_argument("--parser-file", type=Path, required=True)
    arg.add_argument("--knowledge-root", type=Path, default=Path("knowledge"))
    arg.add_argument("--out", type=Path, default=Path(".ci/tapestry-concept-review.json"))
    args = arg.parse_args()
    result = validate(args.repo, args.ref, args.parser_file, args.knowledge_root, args.out)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "head_commit",
                    "python_files",
                    "symbols",
                    "edges",
                    "concept_counts",
                    "confident_counts",
                    "provider_calls",
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
