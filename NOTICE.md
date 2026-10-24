# NOTICE · CodeInsight

CodeInsight 以 **Apache License 2.0** 发布，完整条款见 [`LICENSE`](./LICENSE)。
本文件记录第三方归属——Apache-2.0 §4(d) 要求在分发时保留 NOTICE 内容。

---

## 1. 第三方组件

| 组件 | 许可 | 位置 | 说明 |
|---|---|---|---|
| Tapestry（织忆） | Apache-2.0 | 部分代码移植 | `docs/ported-from-tapestry.md` 记录了移植了哪些文件、改了什么、丢弃了什么 |
| SQLite FTS5 | 公有领域（SQLite 本身） | 内置 | 关键词检索通道；unicode61 分词器 |
| numpy | BSD-3-Clause | 依赖（pip） | 稠密向量暴力余弦 |
| FastAPI / Starlette / Pydantic | MIT | 依赖（pip） | API 与数据模型层 |
| httpx | BSD-3-Clause | 依赖（pip） | 模型服务客户端 |
| bge-m3 | 见其来源 | 依赖（SiliconFlow API） | 经 API 调用，**权重未随仓分发** |
| jieba | MIT | 依赖（pip，M2 引入） | 中文分词 |
| PyYAML | MIT | 依赖（pip） | 读取概念本体 YAML |
| MCP Python SDK | MIT | 依赖（pip，M7 引入） | 把工具暴露给外部 agent |
| React / React DOM | MIT | 依赖（npm） | 工作台 |
| React Flow | MIT | 依赖（npm） | 关系图（M8） |
| Monaco Editor | MIT | 依赖（npm） | 源码查看 |
| Tailwind CSS | MIT | 依赖（npm） | 样式 |
| Zustand | MIT | 依赖（npm） | 前端状态 |

其余依赖经 `uv.lock` / `package-lock.json` 固定版本，均以各自上游许可分发。

**CodeInsight 自身代码采用 Apache-2.0，与上述组件兼容。**

---

## 2. 知识本体

`knowledge/concepts/` 下的技术概念本体（定义、原理、设计权衡、检测规则）
**由本项目原创编写**，不复制任何外部教材、课程或百科的文本。
每条检测规则描述的是**如何在代码里认出该概念**，属于本项目的原创工程产物。

## 2.1 内置教材

`knowledge/learning/` 下的学习文章是**改写稿**，不是原文转载。
`knowledge/learning/sources.json` 为每篇文章记录了来源与许可，
其中 CC-BY-SA-4.0 / CC-BY-4.0 的条目要求署名，完整清单：

| 来源 | 许可 | 地址 |
|---|---|---|
| A Byte of Python | CC-BY-SA-4.0 | https://python.swaroopch.com/ |
| Python 3.13 教程与标准库 | PSF-2.0 | https://docs.python.org/3.13/tutorial/ |
| MDN Web Docs：学习 Web 开发 | CC-BY-SA-4.0 | https://developer.mozilla.org/zh-CN/docs/Learn_web_development |
| TypeScript Handbook | CC-BY-4.0 | https://www.typescriptlang.org/docs/handbook/intro.html |
| React 中文文档 | CC-BY-4.0 | https://zh-hans.react.dev/learn |
| PostgreSQL Tutorial | PostgreSQL License | https://www.postgresql.org/docs/18/tutorial.html |
| FastAPI：依赖注入与安全 | MIT | https://fastapi.tiangolo.com/tutorial/dependencies/ |
| Redis Python client documentation | MIT | https://redis.readthedocs.io/en/stable/examples.html |
| SQLAlchemy ORM and Core | MIT | https://docs.sqlalchemy.org/en/20/intro.html |
| PyJWT usage | MIT | https://pyjwt.readthedocs.io/en/stable/usage.html |
| filelock tutorial | Unlicense | https://py-filelock.readthedocs.io/en/latest/ |
| Tenacity documentation | Apache-2.0 | https://tenacity.readthedocs.io/en/latest/ |
| Blinker documentation | MIT | https://blinker.readthedocs.io/en/stable/ |

> 教材内容在问答中**单独标注为「教材；非项目代码证据」**，与项目 `citations` 分开，
> 不会与代码事实混用（见 `docs/decisions/` 与 `answer_policy.py`）。

---

## 3. 数据与隐私

- 本项目是**本地单机工具**。索引库（`.ci/`）、评测原始响应（`eval/runs/`）、
  研究记录（`eval/studies/`）均在 `.gitignore` 中，**不随仓库分发**。
- 项目不收集、不上传任何用户数据。调用模型服务时，仅发送**当前问题与检索到的代码片段**。
- API 密钥只从环境变量读取，不落库、不入库、不写入日志。

---

## 4. 免责声明

本项目按「现状」提供，不含任何明示或暗示的担保。
使用者应自行评估其适用性，并遵守其所用模型服务与数据源的条款。
