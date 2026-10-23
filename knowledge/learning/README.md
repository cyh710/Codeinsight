# 内置代码学习知识库 · B 线交付

这里包含 46 篇基础文章和 20 篇工程概念讲解。Markdown 是可维护的正文，
`index.json` 提供目录/术语/前置知识/工程概念关联；`sources.json` 锁定来源网页快照哈希。
它不是第三方教材的完整镜像。本文与示例不表示任何被分析项目真的具有相应实现。

## 运行与目录

从 B worktree 根目录运行，使用项目 Python 环境：

```powershell
$env:PYTHONPATH = 'src'
python -m codeinsight.cognitive.concepts.examples.offline_demo --question 'SQL 是什么'
python -m codeinsight.cognitive.concepts.examples.offline_demo --question '这里是什么意思' --reading-topic python-functions --reading-section example --out .ci/reading-demo.json
python -m pytest tests/concepts -q
```

普通加载、阅读和检索不需要网络或模型密钥。概念 YAML 加载需要 PyYAML；
已在 `docs/requests/0001-built-in-learning-library.md` 申请 A 线声明依赖。
当前验证使用现有项目环境中已经安装的 PyYAML，不把偶然安装当成干净安装验收。

## 接入约定

```python
from pathlib import Path
from codeinsight.cognitive.concepts.library import LearningLibrary
from codeinsight.cognitive.concepts.service import KnowledgeService
from codeinsight.cognitive.concepts.links import link_answer, validate_answer_links

library = LearningLibrary(Path('knowledge/learning'))
service = KnowledgeService(library)
tree = library.tree()
topic = library.get('sql-database')
context, entries = service.prepare_turn('SQL 是什么', max_bytes=12000)
# context.content 是实际可以注入的教材片段；references 单独保存知识来源。
# 模型调用和项目代码检索由 A 线负责；下面只演示对一段既有文本添加链接。
answer = link_answer('SQL 可以查询数据库中的表。', library, recommendations=entries)
text = validate_answer_links(answer.text, library)
```

- 默认复用 A 线 `split_identifiers`，入库与查询使用同一实例；也可通过 `tokenizer=` 注入对照实现。
  当前环境未安装 jieba，共享分词器按 A 线实现回退到中文二元词，不将此结果描述为 jieba 验证。
- 搜索返回章节而不是整本书；来源与版本不藏在可截断正文里。
- `reading_context(target)` 从本地资产重新读取，不信任客户端正文；旧版本/旧章节标记截断/失效。
- `link_answer` 对正文首次出现的术语加链接，不触碰代码块、行内代码和已有链接。
- `/learn/{topic_id}#{section_id}` 是 C 线需要拦截的阅读目标，不是已经部署的网站。
- 正文的 `{#section_id}` 是资产锚点标记；C 可按 sections 的 id/title/content 渲染，
  将 id 绑定到标题，不把锚点标记作为面向用户的正文显示。
- `KnowledgeService` 分别保存项目 commit/index_epoch。未注册项目返回 not_indexed，
  不将“没有数据”声称为“项目没有使用技术”。
- `RuleBasedDetector.detect(..., sources=..., edge_confidences=...)` 接收冻结源码与原始边置信度。
  sources 不提供时只做受限名称检测，不回读工作区。缺失置信度保守处理。
- `explain` 是异步函数；quick/project 不调用 Provider；deep 模型不能添加 facts/citations。
  模型格式错误、超时或输入超预算时保留本体与已有证据，并返回可解释 error。
- `compare_claims` 只提供 M6 概念侧支持程度；not_observed 不等于设计已过期。

## 真实仓库验证

```powershell
python -m codeinsight.cognitive.concepts.examples.validate_tapestry --repo '<被测仓库>' --ref agent-v1 --parser-file src/codeinsight/cognitive/parsing/python_parser.py --out .ci/tapestry-concept-review.json
```

脚本读取 git blob，不读被测仓库未提交文件。验证固定 tag 下全部 389 个 Python 文件，
不是主线 scanner 排除规则的验收。实际源快照与解析器哈希写进报告。
30 条样本保留源码与 pending_human_review 标记；没有人工标签就不输出精确率，
没有完整 gold set 就不输出召回率。主要分支不使用付费模型。

## 来源与许可

- A Byte of Python：CC BY-SA 4.0；Python 官方文档：PSF-2.0。
- MDN：按其允许的 CC BY-SA 2.5 或以后版本选用 4.0。
- TypeScript 与 React 文档：CC BY 4.0；PostgreSQL 文档：PostgreSQL License。
- 工程文章逐篇列出 Python、FastAPI、Redis、SQLAlchemy、PyJWT、filelock、Tenacity、Blinker 参考资料。
- 原始许可保存在 `licenses/`。文章的改编内容分别保留来源许可，不改标应用的 Apache-2.0。
- 含 CC BY-SA 来源的文章文本按 CC BY-SA 4.0 分发；本项目新写的教学片段不视为原书代码。
- 来源原始网页缓存位于 `.ci/source-snapshots/`，锁定哈希可用于核验，普通用户无需重新下载。

## 尚待 A/C 完成的集成

全局知识 API、最终 SSE 增量字段、Agent 自动检索注入、实际点击导航、滚动恢复、
干净安装依赖及 wheel 内资产打包，均属于请求 0001 的跨线事项。
B 线的离线样例不是上述交互已经实现的证明。
