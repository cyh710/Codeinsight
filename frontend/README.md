# CodeInsight 前端

可恢复的 AI 工作台：左栏项目、对话／文件，中间对话／关系图／时间线，
右栏代码、教材、概念等多页签材料。侧栏可开关、拖动调宽，窄窗口在对话与材料之间切换。

- 基建复制自织忆 `ai-companion-agent@agent-v1`（ADR 0013），
  出处清单见 [`docs/ported-from-tapestry.md`](../docs/ported-from-tapestry.md)。
- API 契约见 [`docs/api-contract.md`](../docs/api-contract.md)（冻结），
  TS 类型见 [`src/api/types.ts`](src/api/types.ts)（冻结，改动走 `docs/requests/`）。

## 运行

```bash
npm install
npm run dev        # http://localhost:5173
```

默认连接真实后端，代理目标为 `http://127.0.0.1:8020`；启动器选择其他端口时会通过
`CI_API_TARGET` 同步。浏览器访问 `/api/*`，Vite 剥掉前缀转发。
在仓库根目录启动后端：

```bash
uv run uvicorn codeinsight.api.app:app --host 127.0.0.1 --port 8020
```

仅离线回放时开启 mock：数据来自 `public/mock/sample-index.json` 的固定索引样本，
对话走预设 SSE；它不覆盖当前全部生产交互，不能替代真实 API 验收。

PowerShell 中在 `frontend/` 运行：

```powershell
$env:VITE_CI_MOCK = '1'
npm run dev
# 回到真实后端时移除开关，再重启 Vite
Remove-Item Env:VITE_CI_MOCK
```

## 测试与验收

```bash
npm run test       # Vitest
npm run lint
npm run build
npm run test:browser  # Playwright：独立 API、临时项目及脚本化 Provider
```

浏览器测试默认使用本机 Edge，在 15174／18021 启动独立前后端；
`CI_TEST_PYTHON` 可指定 Python 路径，不复用用户正在运行的服务。

会话与最终回答以服务端 SQLite 为准，草稿、材料与位置保存在 IndexedDB，布局偏好在
localStorage。切换项目／对话不会停止原回答；刷新、断线或停止会保留已保存内容并标记中断，
不自动重发。来源点击携带内容身份，缺版本的旧材料需主动选择“查看当前文件”。

## 快照更新

`public/mock/sample-index.json` 以 `fixtures/sample-index.json` 为底，
再用真引擎并入概念实例与流程：

```bash
# 从仓库根目录执行；先同步固定快照底稿
cp fixtures/sample-index.json frontend/public/mock/sample-index.json
# 2. 真引擎检出 concepts/flows 并写入 mock 副本与本体 JSON
uv run python frontend/tools/regen_mock.py --repo "D:/path/to/some-repo" --ref agent-v1
```

工具会做引用完整性过滤：只保留 qualname 命中样本符号的概念实例
（样本外实例点过去就是 404，完整性比数量重要）。

快照里没有的东西（concepts、flows、源码正文），mock 如实返回空/占位，
不编造。需要更新样本时运行上述脚本；检测器与流程实现已落地，旧样本不代表当前索引结果。
