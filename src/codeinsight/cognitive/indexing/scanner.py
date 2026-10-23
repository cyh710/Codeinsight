"""仓库扫描器。

用 `git ls-tree` 取文件树，**不扫工作区**（规格 §1.2 A1）——原因有三：

1. 索引必须绑定一个确定的 commit（`repo_state.head_commit`），
   扫工作区的话，索引内容会随用户未提交的改动漂移，"过期信息比例"这个指标就没法算了。
2. `git ls-tree` 一次调用拿到路径 + blob sha + 体积，696 个文件只要 31 ms。
3. 工作区里可能有 `.env`、构建产物、本地数据，扫它们会把密钥和噪声写进索引库。

路径解析必须带 `-c core.quotepath=false`：默认 git 会把非 ASCII 路径用
八进制转义加引号输出（织忆里 `docs/internal/tasks/色库扩展.md` 会被输出成
`"docs/internal/tasks/\\351...\\266.md"`），解析出来的是乱码。

范围规则见 ADR 0015：分三档，且**只用客观分类，不用打分系数**。
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

# ── 第一档：整目录排除 ────────────────────────────────────────
# 不是代码，或不是这个项目的代码（ADR 0015 第一档）。
EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".tox",
        ".nox",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        "build_cache",
        ".next",
        ".cache",
        "site-packages",
        ".idea",
        ".vscode",
        ".github",
        ".claude",
    }
)

# ── 第二档：第三方代码，符号入库但不生成 chunk ────────────────
# 这些目录里的代码不是本项目写的，不该出现在"这个项目怎么做的"的答案里。
# 但项目 `import` 了它们 → 那条 import 边是"项目用了 X"这条设计事实的载体，
# 所以符号要入库、import 边要留，只是不生成可检索的 chunk。
VENDORED_DIRS: frozenset[str] = frozenset(
    {
        "mobile_sam",
        "third_party",
        "thirdparty",
        "vendor",
        "vendored",
        "external",
        "third-party",
    }
)

# ── 生成代码的路径特征 ────────────────────────────────────────
GENERATED_PATTERNS: tuple[str, ...] = (
    "_pb2.py",
    "_pb.py",
    "_pb2_grpc.py",
    ".pb.go",
    "_generated.py",
    ".generated.ts",
    ".gen.go",
    "generated_design.py",
)

# ── 后缀分类 ──────────────────────────────────────────────────
LANGUAGE_BY_SUFFIX: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".vue": "vue",
    ".md": "markdown",
    ".rst": "markdown",
    ".toml": "config",
    ".yaml": "config",
    ".yml": "config",
    ".json": "config",
    ".ini": "config",
    ".cfg": "config",
    ".txt": "text",
    ".sh": "shell",
    ".bat": "shell",
    ".ps1": "shell",
    ".css": "css",
    ".html": "html",
    ".sql": "sql",
}

# 明确的二进制后缀——直接排除，不读内容。
BINARY_SUFFIXES: frozenset[str] = frozenset(
    {
        ".pyc",
        ".pyo",
        ".so",
        ".dll",
        ".dylib",
        ".exe",
        ".pyd",
        ".a",
        ".o",
        ".bin",
        ".onnx",
        ".pt",
        ".pth",
        ".safetensors",
        ".gguf",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".webp",
        ".svg",
        ".mp3",
        ".wav",
        ".flac",
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".pdf",
        ".docx",
        ".xlsx",
        ".pptx",
        ".ttf",
        ".otf",
        ".woff",
        ".woff2",
        ".db",
        ".sqlite",
        ".sqlite3",
    }
)

# 后缀不在上面任何一类的，默认按文本处理（未知后缀可能是自制的配置文件）。
# 但没有一个已知后缀的、且体积很大的文件，多半是数据文件——按魔数再判一次。

TEXT_LIKE_SUFFIXES = frozenset(LANGUAGE_BY_SUFFIX) | {".lock", ".txt", ".csv", ".in", ".cfg"}

MAX_TEXT_SIZE_BYTES = 2_000_000
"""超过这个体积的、按后缀判定为文本的文件也不入库——多半是数据不是代码。"""


@dataclass(frozen=True)
class RepoFile:
    """仓库里的一个文件（相对仓库根，posix 风格路径）。

    `role` 是 ADR 0014 定义的互斥分类；`in_index` 表示它是否参与符号/块索引
    （第二档 vendored 文件符号入库但 chunk 不入库，用 `in_chunk_index` 区分）。
    """

    path: str
    blob_sha: str | None
    size_bytes: int
    language: str
    role: str
    in_index: bool = True
    """进不进符号索引。第三档 = True，第二档 = True（为了 import 边），第一档 = 不存在。"""

    in_chunk_index: bool = True
    """进不进 chunk 索引（= 能不能被检索到）。第二档 vendored = False。"""


def _classify_role(path: str) -> str:
    """按路径判定文件角色。优先级：vendored > generated > test > config > doc > source。"""
    parts = path.split("/")
    dir_parts = parts[:-1]
    name = parts[-1]

    if any(p in VENDORED_DIRS for p in dir_parts):
        return "vendored"
    if any(name.endswith(pat) for pat in GENERATED_PATTERNS):
        return "generated"
    if (
        "tests" in dir_parts
        or "test" in dir_parts
        or name.startswith("test_")
        or name.endswith("_test.py")
    ):
        return "test"
    if name in {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"} or name.endswith(
        (".toml", ".yaml", ".yml", ".ini", ".cfg")
    ):
        return "config"
    if name.endswith((".md", ".rst")):
        return "doc"
    return "source"


def _classify_language(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return LANGUAGE_BY_SUFFIX.get(suffix, "text")


def _is_excluded(path: str) -> bool:
    """第一档排除规则：目录名单 + 二进制后缀 + 锁文件。"""
    parts = path.split("/")
    if any(p in EXCLUDED_DIRS for p in parts[:-1]):
        return True
    name = parts[-1]
    suffix = Path(name).suffix.lower()
    if suffix in BINARY_SUFFIXES:
        return True
    if name.endswith(".lock"):
        return True
    if name.startswith(".env"):
        # `.env` / `.env.example`：`.env.example` 是模板，可以留；真 `.env` 绝不能进索引
        return name == ".env" or (name.startswith(".env.") and not name.endswith(".example"))
    return False


def _git_ls_tree(root: Path, ref: str | None) -> list[tuple[str, str | None, int]]:
    """跑 `git ls-tree`，返回 [(path, blob_sha, size_bytes)]。

    失败（非 git 目录、ref 不存在）时抛 `RuntimeError`，由调用方决定是降级还是报错。
    """
    cmd = ["git", "-c", "core.quotepath=false", "ls-tree", "-r", "-z", "--long"]
    # git ls-tree 必须给 tree-ish；缺省用 HEAD（索引要绑定确定的 commit）
    cmd.append(ref or "HEAD")
    proc = subprocess.run(cmd, cwd=root, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"git ls-tree 失败（ref={ref!r}）：{proc.stderr.decode('utf-8', 'replace').strip()}"
        )

    out: list[tuple[str, str | None, int]] = []
    for record in proc.stdout.split(b"\0"):
        if not record:
            continue
        # 格式：<mode> SP <type> SP <sha> SP* <size> TAB <path>
        head, _, raw_path = record.partition(b"\t")
        if not raw_path:
            continue
        fields = head.split()
        if len(fields) < 4:
            continue
        obj_type = fields[1].decode("ascii", "replace")
        sha = fields[2].decode("ascii", "replace")
        size = int(fields[3])
        path = raw_path.decode("utf-8", "replace")
        if obj_type != "blob":
            # tree / commit（submodule）——不是文件，跳过
            continue
        out.append((path, sha, size))
    return out


def _walk_fallback(root: Path) -> list[tuple[str, str | None, int]]:
    """非 git 目录的退路：走文件系统。

    只在没有 .git 时才用——这时候没有 commit 可绑定，索引只能标 `head_commit=NULL`。
    """
    out: list[tuple[str, str | None, int]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in filenames:
            full = Path(dirpath) / name
            try:
                size = full.stat().st_size
            except OSError:
                continue
            rel = full.relative_to(root).as_posix()
            out.append((rel, None, size))
    return out


def list_repo_files(root: Path, *, ref: str | None = None) -> list[RepoFile]:
    """列出仓库里应该被索引的文件。

    参数
    ----
    root
        仓库根目录。
    ref
        git ref（分支 / tag / commit）。缺省 = 当前 HEAD。

    返回
    ----
    按路径排序的 `RepoFile` 列表。

    规则见 ADR 0015：第一档整目录排除；第二档（vendored）保留但标记
    `in_chunk_index=False`；其余全量保留，**不做任何降权**。
    """
    root = Path(root)
    if not (root / ".git").exists():
        entries = _walk_fallback(root)
    else:
        entries = _git_ls_tree(root, ref)

    files: list[RepoFile] = []
    for path, sha, size in entries:
        if _is_excluded(path):
            continue
        role = _classify_role(path)
        language = _classify_language(path)
        if size > MAX_TEXT_SIZE_BYTES and Path(path).suffix.lower() not in TEXT_LIKE_SUFFIXES:
            continue
        is_vendored = role == "vendored"
        files.append(
            RepoFile(
                path=path,
                blob_sha=sha,
                size_bytes=size,
                language=language,
                role=role,
                in_index=True,
                in_chunk_index=not is_vendored,
            )
        )
    files.sort(key=lambda f: f.path)
    return files


def read_blobs(root: Path, ref: str | None, paths: list[str]) -> dict[str, bytes]:
    """批量读文件内容。

    用**一次** `git cat-file --batch` 管道读全部文件，而不是每个文件起一次
    `git cat-file` ——后者是 N 次进程创建，389 个文件要好几秒。

    `paths` 里不存在于该 ref 的文件会被静默跳过（返回的 dict 里没有）。
    """
    if not paths:
        return {}
    if not (root / ".git").exists():
        # 非 git 目录：退到文件系统读。
        # 源文档 §2.1 说输入可以是「GitHub 地址或**本地项目**」——
        # 人家给一个没有 .git 的目录也得能导入。
        return _read_from_disk(root, paths)
    ref = ref or "HEAD"
    request = "".join(f"{ref}:{p}\n" for p in paths)
    proc = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=root,
        input=request.encode("utf-8"),
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git cat-file --batch 失败：{proc.stderr.decode('utf-8', 'replace').strip()}"
        )

    out: dict[str, bytes] = {}
    data = proc.stdout
    pos = 0
    for path in paths:
        nl = data.find(b"\n", pos)
        if nl < 0:
            break
        header = data[pos:nl].split()
        pos = nl + 1
        if len(header) < 3:
            # "<sha> missing" —— 文件在 ref 里不存在
            continue
        size = int(header[2])
        out[path] = data[pos : pos + size]
        pos += size + 1  # 内容后面跟一个换行
    return out


def _read_from_disk(root: Path, paths: list[str]) -> dict[str, bytes]:
    """非 git 目录的退路：直接读文件。

    路径是仓库相对路径（posix 风格），拼上 root 即可。
    读不到的文件静默跳过（和 git 路径的行为一致）。
    """
    out: dict[str, bytes] = {}
    for path in paths:
        full = root / path
        try:
            out[path] = full.read_bytes()
        except OSError:
            continue
    return out


def module_qualname(path: str) -> str:
    """文件路径 → 模块 qualname。

    `backend/core/chunk_bm25.py` → `backend.core.chunk_bm25`
    `backend/__init__.py`         → `backend`
    `main.py`                     → `main`
    """
    p = path
    if p.endswith(".py"):
        p = p[:-3]
    parts = [seg for seg in p.split("/") if seg]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)
