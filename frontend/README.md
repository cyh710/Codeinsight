# CodeInsight 前端

三栏工作台：左栏文件/符号树 · 中栏对话流（SSE）· 右栏证据面板。

- 基建复制自织忆 `ai-companion-agent@agent-v1`（ADR 0013），
  出处清单见 [`docs/ported-from-tapestry.md`](../docs/ported-from-tapestry.md)。
- API 契约见 [`docs/api-contract.md`](../docs/api-contract.md)（冻结），
  TS 类型见 [`src/api/types.ts`](src/api/types.ts)（冻结，改动走 `docs/requests/`）。

## 运行

```bash
npm install
npm run dev        # http://localhost:5173
```

默认 **mock 模式**：数据来自 `public/mock/sample-index.json`——
A 线 `ci dump-fixture` 产出的织忆 `agent-v1` **真实索引快照**
（非手写假数据）。对话走 canned SSE 回放，事件形状与契约 §8.3 一致。

连真实后端（须在 8020 端口）：

```bash
VITE_CI_MOCK=0 npm run dev
```

## 测试与验收

```bash
npm run test       # Vitest（node 环境，无 jsdom，与织忆一致）
npm run lint
npm run build
```

## 快照更新

`public/mock/sample-index.json` 是 `fixtures/sample-index.json` 的副本。
A 线重跑 dump-fixture 后，在仓库根目录执行复制即可：

```bash
cp fixtures/sample-index.json frontend/public/mock/sample-index.json
```

快照里没有的东西（concepts、flows、源码正文），mock 如实返回空/占位，
不编造——等 B 线检测器与 A5 流程检测落地后重跑快照即补齐。
