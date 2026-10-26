"""生成原创教学 SVG 与内容清单；--check 只检查，便于离线发布核对。"""

from __future__ import annotations

import argparse
import hashlib
import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "knowledge" / "learning"


def text(x: int, y: int, value: str, size: int = 20, anchor: str = "middle") -> str:
    return f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}">{escape(value)}</text>'


def box(x: int, y: int, width: int, label: str, fill: str = "#e6f3f9") -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="56" rx="6" '
        f'fill="{fill}" stroke="#cfdee8"/>' + text(x + width // 2, y + 35, label)
    )


def arrow(x1: int, y1: int, x2: int, y2: int) -> str:
    return (
        f'<path d="M{x1},{y1} L{x2},{y2}" stroke="#6296af" stroke-width="2" '
        'fill="none" marker-end="url(#arrow)"/>'
    )


def table(y: int, title: str, columns: list[str], rows: list[list[str]]) -> str:
    width = 380 // len(columns)
    result = text(30, y, title, 21, "start")
    for index, row in enumerate([columns, *rows]):
        top = y + 16 + index * 40
        result += (
            f'<rect x="30" y="{top}" width="380" height="40" '
            f'fill="{"#e6f3f9" if index == 0 else "#fff"}" stroke="#d8e4ec"/>'
        )
        for col, value in enumerate(row):
            result += text(30 + col * width + width // 2, top + 26, value, 19)
    return result


def document(title: str, description: str, height: int, content: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="440" '
        f'height="{height}" viewBox="0 0 440 {height}" role="img" '
        'aria-labelledby="title description">'
        f'<title id="title">{escape(title)}</title><desc id="description">{escape(description)}</desc>'
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" '
        'orient="auto"><path d="M0 0L8 4L0 8" fill="#6296af"/></marker></defs>'
        '<rect width="100%" height="100%" rx="8" fill="#f6f9fb"/>'
        '<g fill="#293f53" font-family="Microsoft YaHei,sans-serif">'
        f"{content}</g></svg>\n"
    )


def figures() -> list[tuple[dict, str]]:
    """图中的数据对应三篇样章；SVG 不依赖网络、脚本或运行时布局。"""
    result = []

    def add(
        aid: str, topic: str, section: str, title: str, description: str, height: int, content: str
    ) -> None:
        svg = document(title, description, height, content)
        result.append(
            (
                dict(
                    id=aid,
                    topic_id=topic,
                    section_id=section,
                    file=f"assets/{topic}/{aid}.svg",
                    title=title,
                    description=description,
                    width=440,
                    height=height,
                    author="CodeInsight",
                    license="Apache-2.0",
                    source_ids=[],
                    sha256=hashlib.sha256(svg.encode()).hexdigest(),
                ),
                svg,
            )
        )

    content = text(220, 36, "打印与返回值经过不同的出口", 22)
    content += box(45, 62, 350, "calculate_total(12, 3)")
    content += arrow(220, 118, 220, 148)
    content += box(45, 152, 350, "函数内 print(36)", "#fff")
    content += text(220, 237, "屏幕先显示：36", 19)
    content += arrow(220, 248, 220, 278)
    content += box(45, 282, 350, "无 return，正常结束", "#fff")
    content += arrow(220, 338, 220, 368)
    content += box(45, 372, 350, "调用者拿到 None")
    content += arrow(220, 428, 220, 458)
    content += text(220, 490, "外部 print(amount) 显示：None", 20)
    content += text(220, 529, "改用 return 才把 36 交给调用者", 19)
    add(
        "python-return-path",
        "python-functions",
        "example",
        "打印与返回值",
        "内部 print 显示 36；普通函数没有显式 return 且正常结束时返回 None，amount 因此是 None，外部 print 再显示 None。改用 return 可把 36 交给调用者。",
        560,
        content,
    )

    content = table(
        38,
        "products · 被引用的商品",
        ["id", "name", "price"],
        [["1", "笔记本", "12.0"], ["2", "钢笔", "35.0"]],
    )
    content += arrow(220, 314, 220, 206)
    content += text(235, 248, "外键引用", 19, "start")
    content += text(235, 278, "不是执行顺序", 18, "start")
    content += table(
        342,
        "orders · 通过 product_id 找商品",
        ["id", "product_id", "quantity"],
        [["101", "1", "2"], ["102", "1", "1"], ["103", "2", "1"]],
    )
    content += text(220, 560, "订单 101、102 引用同一个商品 1", 19)
    add(
        "sql-table-relation",
        "sql-database",
        "relationships",
        "商品与订单的引用关系",
        "orders.product_id 引用 products.id；101 和 102 都引用商品 1，103 引用商品 2。箭头表示外键引用，不是执行顺序。SQL 声明并启用约束，画线本身不创建约束。",
        590,
        content,
    )

    content = text(220, 38, "状态的逻辑归属", 23)
    content += box(45, 65, 350, "一次应用运行")
    content += '<path d="M50 121V438H75M50 205H75" fill="none" stroke="#a4bdcc" stroke-width="2"/>'
    content += '<rect x="75" y="157" width="330" height="178" rx="7" fill="#fff" stroke="#cfdee8"/>'
    content += text(95, 191, "浏览器侧", 22, "start")
    content += text(95, 231, "页面内存：组件状态 / store", 19, "start")
    content += text(95, 271, "浏览器存储：localStorage", 19, "start")
    content += text(95, 304, "与 IndexedDB", 19, "start")
    content += '<rect x="75" y="374" width="330" height="155" rx="7" fill="#fff" stroke="#cfdee8"/>'
    content += text(95, 408, "后端侧", 22, "start")
    content += text(95, 449, "进程内存：任务 / 临时缓存", 19, "start")
    content += text(95, 491, "数据文件：SQLite / 索引", 19, "start")
    content += text(220, 574, "包含关系不等于相同生命周期", 19)
    add(
        "state-storage-boundaries",
        "state-lifecycle",
        "ownership",
        "状态与存储的层级",
        "按职责分为浏览器与后端。浏览器包含页面内存及 localStorage/IndexedDB；后端包含进程内存和 SQLite 等数据文件。刷新页面与重启后端影响不同对象。",
        602,
        content,
    )

    content = text(220, 38, "模块再次执行，不等于原状态仍在", 21)
    content += box(45, 65, 350, "已有 store：4 个项目")
    content += arrow(220, 121, 220, 151)
    content += text(220, 182, "发生开发期 HMR", 20)
    content += arrow(200, 205, 122, 249) + arrow(240, 205, 320, 249)
    content += box(25, 265, 180, "重新创建 store", "#fff")
    content += box(235, 265, 180, "复用原 store", "#e6f3f9")
    content += arrow(115, 321, 115, 364) + arrow(325, 321, 325, 364)
    content += text(115, 396, "新对象：0 项", 20) + text(325, 396, "同一对象：4 项", 20)
    content += text(115, 434, "初始化没有重跑", 18) + text(325, 434, "hot.data 保留身份", 18)
    content += text(220, 493, "此机制服务开发热更新，不跨整页刷新", 19)
    add(
        "state-hmr-identity",
        "state-lifecycle",
        "hmr",
        "HMR 中的容器身份",
        "事故中模块重新创建空 store，而启动初始化未重跑，项目从 4 变成 0。修复复用 hot.data 中的完整容器，保留状态及闭包；它不提供网页刷新后的持久化。",
        524,
        content,
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    assets = figures()
    files = {ROOT / record["file"]: svg for record, svg in assets}
    files[ROOT / "assets.json"] = (
        json.dumps([r for r, _ in assets], ensure_ascii=False, indent=2) + "\n"
    )
    for path, content in files.items():
        if args.check:
            if not path.exists() or path.read_bytes() != content.encode("utf-8"):
                raise SystemExit(f"教学图需要重建：{path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content.encode("utf-8"))
    print(f"{'检查' if args.check else '生成'} {len(assets)} 张原创教学图。")


if __name__ == "__main__":
    main()
