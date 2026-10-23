"""入口与依赖识别（规格 §1.2 A4，对应源文档 §2.1-1 / §2.1-2）。

源文档 §2.1-2 的原话是「解析文件目录与**项目入口**」，§2.1-1 是
「自动识别编程语言、框架、**依赖和配置**」。这两件事都靠**声明**而不是猜测：

- 入口看 `main.py` / `app.py` / `__main__.py` 的**存在**，
  看 `pyproject.toml` 的 `[project.scripts]` 的**声明**，
  看模块级 `app = FastAPI()` 的**赋值**。
- 依赖看 `pyproject.toml` / `requirements*.txt` 的**声明**；
  只在源码里 `import` 到但没声明的，记 `source='import'`、`declared=0`——
  「装了但没写进依赖表」本身是项目卫生问题，值得被看见。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

# ── 入口文件名的约定 ──────────────────────────────────────────
ENTRY_FILENAMES: frozenset[str] = frozenset({"main.py", "app.py", "__main__.py"})

# ── 框架应用的判定 ────────────────────────────────────────────
# `app = FastAPI()` / `application = Flask(__name__)` 这类模块级赋值。
FRAMEWORK_APP_NAMES: frozenset[str] = frozenset({"app", "application", "api"})
FRAMEWORK_FACTORIES: frozenset[str] = frozenset(
    {
        "FastAPI",
        "Flask",
        "APIRouter",
        "Sanic",
        "Quart",
        "Starlette",
    }
)

# ── 依赖声明解析 ──────────────────────────────────────────────
_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$")
_PEP508_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?:\s*\[(?P<extras>[^\]]*)\])?"
    r"\s*(?P<spec>[^;]*);?"
)
_MARKER_NAMES = {"python", "none", "any"}


@dataclass(frozen=True)
class EntryPointSpec:
    """一个项目入口。"""

    kind: str  # file | console_script | framework_app
    target: str  # 'main:app' / 'backend.main:main'
    module_qualname: str | None = None
    source_path: str | None = None
    doc: str | None = None


@dataclass(frozen=True)
class DependencySpec:
    """一个依赖。"""

    name: str
    version: str | None = None
    source: str = "pyproject"  # pyproject | requirements | import
    declared: bool = True
    is_dev: bool = False


def normalize_distribution(name: str) -> str:
    """把 import 名归一成发行名（`yaml` ↔ `PyYAML` 这种差异只能靠声明侧对齐）。

    归一化只做大小写与 `-`/`_` 统一——PyPI 允许 `zope.interface` 这类带点的名字，
    不能一刀切只留字母数字。
    """
    return name.strip().lower().replace("_", "-")


def parse_requirement_line(line: str, *, source: str = "requirements") -> DependencySpec | None:
    """解析一行依赖声明。

    支持 `fastapi>=0.115`、`fastapi[all]>=0.115`、`pkg==1.0 ; python_version>'3.9'`。
    注释、选项行（`-r`、`--index-url`）返回 None。

    `source` 说明这行声明来自哪儿（requirements 文件 / pyproject），
    会写进依赖表——「这个包是声明的还是只 import 到的」是两种不同的事实。
    """
    text = line.split("#", 1)[0].strip()
    if not text or text.startswith("-"):
        return None
    match = _PEP508_RE.match(text)
    if not match:
        return None
    name = match.group("name")
    if normalize_distribution(name) in _MARKER_NAMES:
        return None
    spec = (match.group("spec") or "").strip()
    return DependencySpec(name=name, version=spec or None, source=source)


def parse_requirements_text(text: str) -> list[DependencySpec]:
    """解析 requirements.txt 内容（一行一个依赖）。"""
    out: list[DependencySpec] = []
    for line in text.splitlines():
        dep = parse_requirement_line(line)
        if dep is not None:
            out.append(dep)
    return out


def parse_pyproject_dependencies(pyproject: dict) -> list[DependencySpec]:
    """从 `pyproject.toml` 的解析结果里取依赖。

    覆盖 `[project].dependencies`、`[project.optional-dependencies]`（dev 组）
    与 `[tool.uv].dev-dependencies` / `[dependency-groups]`。
    """
    out: list[DependencySpec] = []

    project = pyproject.get("project") or {}
    for line in project.get("dependencies") or []:
        dep = parse_requirement_line(str(line), source="pyproject")
        if dep is not None:
            out.append(dep)

    optional = project.get("optional-dependencies") or {}
    for group, lines in optional.items():
        is_dev = normalize_distribution(group) in {"dev", "develop", "development", "test"}
        for line in lines or []:
            dep = parse_requirement_line(str(line), source="pyproject")
            if dep is not None:
                out.append(
                    DependencySpec(
                        name=dep.name,
                        version=dep.version,
                        source="pyproject",
                        declared=True,
                        is_dev=is_dev,
                    )
                )

    # PEP 735 依赖组（`[dependency-groups]`）
    groups = pyproject.get("dependency-groups") or {}
    for group, lines in groups.items():
        is_dev = normalize_distribution(group) in {"dev", "develop", "development", "test"}
        for line in lines or []:
            dep = parse_requirement_line(str(line), source="pyproject")
            if dep is not None:
                out.append(
                    DependencySpec(
                        name=dep.name,
                        version=dep.version,
                        source="pyproject",
                        declared=True,
                        is_dev=is_dev,
                    )
                )

    return out


def parse_console_scripts(pyproject: dict) -> list[EntryPointSpec]:
    """读 `[project.scripts]`（以及 `[tool.poetry.scripts]`）。"""
    out: list[EntryPointSpec] = []
    project = pyproject.get("project") or {}
    scripts = project.get("scripts") or {}
    poetry = ((pyproject.get("tool") or {}).get("poetry") or {}).get("scripts") or {}
    for name, target in {**scripts, **poetry}.items():
        out.append(
            EntryPointSpec(
                kind="console_script",
                target=f"{name} = {target}",
                module_qualname=str(target).split(":")[0] or None,
                source_path="pyproject.toml",
            )
        )
    return out


def detect_entry_points(
    *,
    files: list[str],
    sources: dict[str, str],
    pyproject: dict | None = None,
) -> list[EntryPointSpec]:
    """识别项目入口。

    `files` 是仓库里的文件路径（posix），`sources` 是其中 Python 文件的内容。
    """
    out: list[EntryPointSpec] = []
    seen: set[tuple[str, str]] = set()

    def _add(spec: EntryPointSpec) -> None:
        key = (spec.kind, spec.target)
        if key in seen:
            return
        seen.add(key)
        out.append(spec)

    if pyproject:
        for spec in parse_console_scripts(pyproject):
            _add(spec)

    for path in files:
        name = path.rsplit("/", 1)[-1]
        if name in ENTRY_FILENAMES:
            module_qualname = _module_qualname(path)
            _add(
                EntryPointSpec(
                    kind="file",
                    target=f"{module_qualname}:__main__"
                    if name == "__main__.py"
                    else module_qualname,
                    module_qualname=module_qualname,
                    source_path=path,
                )
            )

    for path, source in sources.items():
        module_qualname = _module_qualname(path)
        for app_name in _framework_apps(source):
            _add(
                EntryPointSpec(
                    kind="framework_app",
                    target=f"{module_qualname}:{app_name}",
                    module_qualname=module_qualname,
                    source_path=path,
                )
            )

    return out


def _module_qualname(path: str) -> str:
    p = path
    if p.endswith(".py"):
        p = p[:-3]
    parts = [seg for seg in p.split("/") if seg]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _framework_apps(source: str) -> list[str]:
    """模块级 `app = FastAPI()` 这类框架应用。

    只认模块级赋值——函数内部建 app 不算项目入口。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    found: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id not in FRAMEWORK_APP_NAMES:
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        func = value.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name in FRAMEWORK_FACTORIES:
            found.append(target.id)
    return found


def collect_import_dependencies(
    imported_modules: list[str],
    *,
    stdlib_names: frozenset[str] | None = None,
    local_packages: set[str] | None = None,
) -> list[DependencySpec]:
    """把源码里 import 到、但没在依赖表里声明的包记成 `source='import'`。

    只取**顶层**包名（`backend.core.x` → `backend`）——依赖是发行单位，
    不是模块单位。

    `local_packages` 是本仓库自己的顶层包，它们不是依赖，排除掉。
    """
    out: list[DependencySpec] = []
    seen: set[str] = set()
    local = {normalize_distribution(name) for name in (local_packages or ())}
    for module in imported_modules:
        if not module:
            continue
        top = module.split(".")[0]
        if not top or top in seen:
            continue
        if stdlib_names and top in stdlib_names:
            continue
        if normalize_distribution(top) in local:
            continue
        seen.add(top)
        out.append(DependencySpec(name=top, version=None, source="import", declared=False))
    return out
