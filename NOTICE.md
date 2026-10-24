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

其余依赖经 `uv.lock` / `package-lock.json` 固定版本，均以各自上游许可分发。

**CodeInsight 自身代码采用 Apache-2.0，与上述组件兼容。**

---

## 2. 知识本体

`knowledge/concepts/` 下的技术概念本体（定义、原理、设计权衡、检测规则）
**由本项目原创编写**，不复制任何外部教材、课程或百科的文本。
每条检测规则描述的是**如何在代码里认出该概念**，属于本项目的原创工程产物。

`knowledge/learning/` 的教材正文按各篇元数据和文末声明的许可分发，
**不统一改标 Apache-2.0**。作者、原文地址、固定版本及修改记录见
[`sources.json`](./knowledge/learning/sources.json)，许可原文见
[`licenses/`](./knowledge/learning/licenses/)。其中 CC-BY/CC-BY-SA 内容须保留署名、
许可与修改说明；CC-BY-SA 改编内容继续遵循相同许可。

---

## 3. 数据与隐私

- 本项目是**本地单机工具**。索引库（`.ci/`）、评测原始响应（`eval/runs/`）、
  研究记录（`eval/studies/`）均在 `.gitignore` 中，**不随仓库分发**。
- 项目不自动收集或上传用户数据。用户启用模型服务后，会向所配置 Provider 发送
  当前问题、必要会话上下文、检索到的代码证据及教材片段。
- API 密钥只从环境变量读取，不落库、不入库、不写入日志。

---

## 4. 免责声明

本项目按「现状」提供，不含任何明示或暗示的担保。
使用者应自行评估其适用性，并遵守其所用模型服务与数据源的条款。
