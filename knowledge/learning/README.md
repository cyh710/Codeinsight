# 内置代码学习知识库 · B 线交付

这里包含 46 篇基础文章、20 篇工程概念讲解与 1 篇工程实践样章。Markdown 是可维护的正文，
`index.json` 提供目录/术语/前置知识/工程概念关联；`sources.json` 锁定来源网页快照哈希。
它不是第三方教材的完整镜像。本文与示例不表示任何被分析项目真的具有相应实现。

## 图文样章与本地验证

Python 函数、SQL 入门、状态生命周期三篇已接入原创 SVG、图注与长文。
`assets.json` 记录图片归属、尺寸、图意、作者、许可与哈希；`assets/` 随知识包分发。
SVG 是原创内容，许可单独列明，不能据此改变正文参考资料的原许可。

```powershell
python scripts/build_learning_figures.py --check
python knowledge/learning/examples/sql_basics.py
python knowledge/learning/examples/state_lifetime.py
```

修改图时编辑生成脚本并运行 `python scripts/build_learning_figures.py`，不要手改哈希。
生成器固定 UTF-8/LF 字节，避免 Windows 换行转换使资源校验失效。
图示的实际字节与元数据参与所属文章版本；旧资源 URL 不会读取新图。
缺图时 API 返回明确错误，章节正文及图意仍可阅读。图注可以选择提问，
图内标签不伪装成 Markdown 原文选区，文字 Provider 通过教材图意理解关系。

## 运行与目录

从 B worktree 根目录运行，使用项目 Python 环境：

```powershell
$env:PYTHONPATH = 'src'
python -m codeinsight.cognitive.concepts.examples.offline_demo --question 'SQL 是什么'
python -m codeinsight.cognitive.concepts.examples.offline_demo --question '这里是什么意思' --reading-topic python-functions --reading-section example --out .ci/reading-demo.json
python -m pytest tests/concepts -q
```

普通加载、阅读和检索不需要网络或模型密钥。概念 YAML 加载需要 PyYAML；
已在 pyproject 与 lock 中声明；wheel 包含教材、本体和来源许可。
资产由 CodeInsight 包或源码目录定位，不从被分析仓库或进程工作目录查找。

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

跨线接入优先使用 `integration.LearningBridge`，目录/正文/检索返回可序列化的
`ToolResult.data`；`prepare_turn()` 返回同一回合的只读快照，最终答案沿用该快照：

```python
from codeinsight.cognitive.concepts.integration import LearningBridge

bridge = LearningBridge(service)
directory = bridge.tree().data
article = bridge.topic('sql-database').data
prepared = bridge.prepare_turn('SQL 是什么', max_bytes=12000)
model_context = prepared.as_tool_result()  # content 注入模型，data 单独保存
final = bridge.finalize_answer('SQL 是语言；“表”组织数据，SELECT 查询数据。', prepared)
# 非流式答案与 SSE 最终 answer 都复用 final，不重复检索、更换来源。
```

阅读上下文只传 `kind='knowledge'`、`topic_id`、`section_id`、`version`。
`reading_status` 区分 `ok/stale/not_found/invalid/outside_budget`；无效目标仍可独立检索
问题，但不能把“这里”假装解释成功。`kind='code'` 明确交给 A 线重新读取项目代码。
客户端附带的 title/snippet/body 不会进入模型。`knowledge_sources` 只列实际注入章节；
正文的学习链接在 `learning_targets` 中独立保存，不因链接存在就伪造已引用来源。
这些兼容增量已依请求 0005 接入本分支；正式字段见 `docs/api-contract.md` §11。
纯指代续问缺少目标时标记 `missing`，不把通用词检索产生的碰巧命中当作答案。
同名术语根据当前文章语言消歧：React 中的“函数”指向 JavaScript 函数；
没有足够上下文的歧义词保持普通文字。“请求”这样的通用词不独立当作 HTTP。

- 默认复用 A 线 `split_identifiers`，入库与查询使用同一实例；也可通过 `tokenizer=` 注入对照实现。
  当前接线使用 A 线已声明的 jieba，并保留中文二元词；未安装时仍有共享回退实现。
- 搜索返回章节而不是整本书；来源与版本不藏在可截断正文里。
- `reading_context(target)` 从本地资产重新读取，不信任客户端正文；旧版本/旧章节标记截断/失效。
- `link_answer` 对正文首次出现的术语加链接，不触碰代码块、行内代码和已有链接。
- `/learn/{topic_id}#{section_id}` 由工作台拦截后打开右栏；未知目标保持文字。
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
python -m codeinsight.cognitive.concepts.examples.validate_tapestry --repo 'D:/path/to/some-repo' --ref agent-v1 --parser-file src/codeinsight/cognitive/parsing/python_parser.py --out .ci/tapestry-concept-review.json
```

脚本读取 git blob，不读被测仓库未提交文件。验证固定 tag 下全部 389 个 Python 文件，
不是主线 scanner 排除规则的验收。实际源快照与解析器哈希写进报告。
30 条样本保留源码与 pending_human_review 标记；没有人工标签就不输出精确率，
没有完整 gold set 就不输出召回率。主要分支不使用付费模型。

M5 人工审核计分（不自动填写标签）：

```powershell
python -m codeinsight.cognitive.concepts.examples.score_review
python -m codeinsight.cognitive.concepts.examples.score_review --review .ci/human-reviewed.json --out .ci/review-score.json
```

请复制审核文件后逐条填 `label: true/false` 与 `reviewed_by`；未审核保留 `null`。
脚本拒绝重复位置、混用冻结版本、非布尔标签和缺少审核者的记录。
全部至少 30 条完成才判断样本是否达到 0.8；部分标签只显示部分样本精确率。
计分工具不认证审核者身份，且没有完整真值全集时始终不报告 recall/F1。

## 来源与许可

- A Byte of Python：CC BY-SA 4.0；Python 官方文档：PSF-2.0。
- MDN：按其允许的 CC BY-SA 2.5 或以后版本选用 4.0。
- TypeScript 与 React 文档：CC BY 4.0；PostgreSQL 文档：PostgreSQL License。
- 工程文章逐篇列出 Python、FastAPI、Redis、SQLAlchemy、PyJWT、filelock、Tenacity、Blinker 参考资料。
- 原始许可保存在 `licenses/`。文章的改编内容分别保留来源许可，不改标应用的 Apache-2.0。
- 含 CC BY-SA 来源的文章文本按 CC BY-SA 4.0 分发；本项目新写的教学片段不视为原书代码。
- 来源原始网页缓存位于 `.ci/source-snapshots/`，锁定哈希可用于核验，普通用户无需重新下载。

## 已接入的页面与验证

本分支已接入知识 API、Agent 有界知识上下文、普通/SSE 最终元数据，
以及目录搜索、章节阅读、内部链接、项目实例、往返导航和阅读位置恢复。
正文与代码共用右栏；客户端只传阅读目标，服务器重新取证。
旧版本会提示更新，项目切换会停止旧请求并隔离上下文。

```powershell
python -m pytest -q
cd frontend
npm ci
npm test
npm run build
npm run test:browser
```

浏览器测试使用本机 Edge；可通过 `CI_TEST_PYTHON` 指定项目 Python 环境。
测试自建临时 Git/SQLite 和假 Provider，连接真实 API；不是静态 mock 页面验收。
安装包验证与固定织忆 `agent-v1` 验证详见 `VALIDATION.md`。
真实模型质量和独立人工阅读/精确率验收仍单独报告。
