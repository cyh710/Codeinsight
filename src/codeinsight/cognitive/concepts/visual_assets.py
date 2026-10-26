"""教材图片清单与受控读取；资源损坏不阻断文章文字。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType

from codeinsight.cognitive.concepts.learning_models import KnowledgeError
from codeinsight.cognitive.concepts.ontology import ID_PATTERN

IMAGE_LINK = re.compile(r"!\[([^\]]*)\]\(/knowledge/assets/([a-z][a-z0-9-]*)\)")
_MEDIA_TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp"}


@dataclass(frozen=True)
class VisualAsset:
    """清单中的资源；文件路径只供服务端使用，href 固定到预期内容版本。"""

    id: str
    topic_id: str
    section_id: str
    file: str
    title: str
    description: str
    width: int
    height: int
    author: str
    license: str
    source_ids: tuple[str, ...]
    sha256: str

    @property
    def href(self) -> str:
        return f"/knowledge/assets/{self.id}/{self.sha256}"

    @property
    def media_type(self) -> str:
        return _MEDIA_TYPES[Path(self.file).suffix]

    def public(self) -> dict:
        """不向浏览器暴露安装路径。"""
        return {k: v for k, v in asdict(self).items() if k != "file"} | {
            "href": self.href,
            "media_type": self.media_type,
        }


class VisualAssets:
    """只加载本地受维护清单；实际资源缺失/损坏记录指纹，读取时明确降级。"""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        manifest = directory / "assets.json"
        try:
            raw = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
        except (OSError, ValueError) as exc:
            raise KnowledgeError(f"图示清单无法读取：{exc}") from exc
        if not isinstance(raw, list):
            raise KnowledgeError("图示清单必须是列表")
        records: dict[str, VisualAsset] = {}
        fingerprints: dict[str, str] = {}
        for item in raw:
            try:
                if not isinstance(item, dict):
                    raise ValueError("资源条目必须是映射")
                item = {**item, "source_ids": tuple(item.get("source_ids", []))}
                asset = VisualAsset(**item)
                if any(
                    not isinstance(v, str) or not v.strip()
                    for k, v in item.items()
                    if k not in {"width", "height", "source_ids"}
                ):
                    raise ValueError("资源文本字段不能为空")
                if (
                    any(
                        not ID_PATTERN.fullmatch(v)
                        for v in (asset.id, asset.topic_id, asset.section_id)
                    )
                    or asset.id in records
                ):
                    raise ValueError("重复或非法资源 ID")
                if any(
                    type(v) is not int or not 0 < v <= 10000 for v in (asset.width, asset.height)
                ):
                    raise ValueError("资源尺寸必须为有效整数")
                if not re.fullmatch(r"[0-9a-f]{64}", asset.sha256):
                    raise ValueError("资源缺少内容哈希")
                path = (directory / asset.file).resolve()
                if (
                    not path.is_relative_to((directory / "assets").resolve())
                    or path.suffix not in _MEDIA_TYPES
                ):
                    raise ValueError("资源必须位于 assets 目录，格式须为 SVG/PNG/WebP")
                records[asset.id] = asset
                try:
                    fingerprints[asset.id] = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError:
                    # 缺图时仍提供元数据与正文，图片端点及界面解释资源不可用。
                    fingerprints[asset.id] = "unavailable"
            except (TypeError, ValueError) as exc:
                raise KnowledgeError(f"图示清单条目无效：{exc}") from exc
        self.records = MappingProxyType(records)
        self.fingerprints = MappingProxyType(fingerprints)

    def for_topic(self, topic_id: str) -> tuple[VisualAsset, ...]:
        return tuple(a for a in self.records.values() if a.topic_id == topic_id)

    def version_data(self, topic_id: str) -> list[dict]:
        return [
            a.public() | {"actual_sha256": self.fingerprints[a.id]}
            for a in self.for_topic(topic_id)
        ]

    def read(self, asset_id: str, expected_hash: str) -> tuple[VisualAsset, bytes]:
        """只读取与当前清单及 URL 哈希一致的字节，旧 URL 不会取到新图片。"""
        asset = self.records.get(asset_id)
        if asset is None or asset.sha256 != expected_hash:
            raise KnowledgeError("图示不存在或版本已更新，请打开当前教材版本。")
        path = (self.directory / asset.file).resolve()
        if not path.is_relative_to((self.directory / "assets").resolve()):
            raise KnowledgeError("图示路径无效。")
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise KnowledgeError("图示文件不可用，章节文字仍可阅读。") from exc
        if hashlib.sha256(content).hexdigest() != expected_hash:
            raise KnowledgeError("图示内容校验失败，章节文字仍可阅读。")
        return asset, content

    def describe(self, content: str) -> str:
        """将已解析图片引用转换成图意，SVG 和图片 URL 不进入文字知识通道。"""

        def replace(match: re.Match) -> str:
            asset = self.records.get(match[2])
            return f"[教学图：{asset.title}] {asset.description}" if asset else match[1]

        parts = re.split(r"(```.*?```|~~~.*?~~~)", content, flags=re.DOTALL)
        return "".join(
            part if i % 2 else IMAGE_LINK.sub(replace, part) for i, part in enumerate(parts)
        )
