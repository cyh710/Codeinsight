-- CodeInsight · SQLite schema
-- 检测规则指纹单独编号；教材文章与本体文案变化不使规则版本递增。
CREATE TABLE IF NOT EXISTS concept_rule_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL UNIQUE
);
--
-- 原则（源文档 §3.1 第四层末句）：
--   「项目认知信息与实际代码版本关联，在代码变化后执行必要的增量更新，
--     避免检索结果与当前仓库不一致。」
--   → 认知必须绑定版本；每一处「随代码变化的东西」都带内容哈希。
--
-- 命名约定：表名单数 snake_case；外键显式声明；索引前缀 ix_。

PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────────────────────
-- 项目与仓库状态
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS project (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    root_path   TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 项目被移除后也保留身份高水位，旧浏览器 URL 不能命中新建项目。
CREATE TABLE IF NOT EXISTS project_id_counter (
    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
    last_id INTEGER NOT NULL
);
INSERT INTO project_id_counter(singleton,last_id)
VALUES (1,(SELECT COALESCE(MAX(id),0) FROM project))
ON CONFLICT(singleton) DO UPDATE SET last_id=MAX(last_id,excluded.last_id);

CREATE TABLE IF NOT EXISTS repo_state (
    project_id      INTEGER PRIMARY KEY REFERENCES project(id) ON DELETE CASCADE,
    head_commit     TEXT,                       -- 索引停在这个 commit
    head_branch     TEXT,
    indexed_at      TEXT,
    parser_version  TEXT NOT NULL,              -- 解析器版本，变更则强制重建
    index_epoch     INTEGER NOT NULL DEFAULT 0, -- 每次索引自增，用于检索缓存失效
    concept_version INTEGER NOT NULL DEFAULT 0  -- 概念本体版本，变更则重跑检测
);

-- ─────────────────────────────────────────────────────────────
-- 代码结构（源文档 §2.1 / §2.2）
-- ─────────────────────────────────────────────────────────────

-- role 是**互斥**的单值分类（source|test|vendored|generated|config|doc）。
-- 不用三个布尔列：布尔列会同时表达"既是测试又是第三方"这种无意义组合，
-- 而且前端要的是"这个文件算什么"的一个答案，不是三个 bit 的组合。
-- 优先级：vendored > generated > test > config > doc > source。
CREATE TABLE IF NOT EXISTS file (
    id                 INTEGER PRIMARY KEY,
    project_id         INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    path               TEXT NOT NULL,           -- repo-relative，posix 风格
    language           TEXT NOT NULL,
    blob_sha           TEXT,                    -- git blob sha @ head_commit
    content_sha256     TEXT NOT NULL,
    size_bytes         INTEGER,
    line_count         INTEGER,
    role               TEXT NOT NULL DEFAULT 'source',
    in_index           INTEGER NOT NULL DEFAULT 1,   -- 是否进入符号/块索引
    UNIQUE(project_id, path)
);
CREATE INDEX IF NOT EXISTS ix_file_project ON file(project_id);
CREATE INDEX IF NOT EXISTS ix_file_sha ON file(project_id, content_sha256);
CREATE INDEX IF NOT EXISTS ix_file_role ON file(project_id, role);

-- 项目依赖（源文档 §2.1-1「自动识别…依赖和配置」）。
-- 一个包一行：声明过又在 pyproject/requirements 里出现的合并成一行；
-- 只在源码里 import 到但没声明的，记 source='import'、declared=0。
CREATE TABLE IF NOT EXISTS dependency (
    id          INTEGER PRIMARY KEY,
    project_id  INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,           -- 'fastapi'
    version     TEXT,                    -- '>=0.115'（声明里写的约束）
    source      TEXT NOT NULL,           -- pyproject|requirements|import
    declared    INTEGER NOT NULL DEFAULT 1,
    is_dev      INTEGER NOT NULL DEFAULT 0,  -- dev 依赖组
    UNIQUE(project_id, name)
);
CREATE INDEX IF NOT EXISTS ix_dependency_project ON dependency(project_id);

CREATE TABLE IF NOT EXISTS module (
    id                INTEGER PRIMARY KEY,
    project_id        INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    file_id           INTEGER NOT NULL REFERENCES file(id) ON DELETE CASCADE,
    qualname          TEXT NOT NULL,            -- 'backend.services.agent_tasks'
    docstring         TEXT,
    responsibility    TEXT,                     -- 职责摘要
    is_core           INTEGER NOT NULL DEFAULT 0,
    UNIQUE(project_id, qualname)
);
CREATE INDEX IF NOT EXISTS ix_module_project ON module(project_id);

CREATE TABLE IF NOT EXISTS entry_point (
    id           INTEGER PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    module_id    INTEGER REFERENCES module(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,                -- file | console_script | framework_app
    target       TEXT NOT NULL,                -- 'main:app' / 'module.path:func'
    source_path  TEXT,
    doc          TEXT
);

CREATE TABLE IF NOT EXISTS symbol (
    id               INTEGER PRIMARY KEY,
    project_id       INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    file_id          INTEGER NOT NULL REFERENCES file(id) ON DELETE CASCADE,
    parent_symbol_id INTEGER REFERENCES symbol(id) ON DELETE CASCADE,
    module_id        INTEGER REFERENCES module(id) ON DELETE SET NULL,
    qualname         TEXT NOT NULL,
    name             TEXT NOT NULL,
    kind             TEXT NOT NULL,             -- module|class|function|method|property|constant
    lineno           INTEGER NOT NULL,
    end_lineno       INTEGER NOT NULL,
    header           TEXT,
    docstring        TEXT,
    is_async         INTEGER NOT NULL DEFAULT 0,
    is_private       INTEGER NOT NULL DEFAULT 0,
    is_dunder        INTEGER NOT NULL DEFAULT 0,
    n_lines          INTEGER,
    source_sha256    TEXT NOT NULL,             -- 符号级内容哈希（过期判定的精确层）
    UNIQUE(project_id, file_id, qualname, lineno)
);
CREATE INDEX IF NOT EXISTS ix_symbol_name ON symbol(project_id, name);
CREATE INDEX IF NOT EXISTS ix_symbol_qual ON symbol(project_id, qualname);
CREATE INDEX IF NOT EXISTS ix_symbol_file ON symbol(file_id);
CREATE INDEX IF NOT EXISTS ix_symbol_parent ON symbol(parent_symbol_id);
CREATE INDEX IF NOT EXISTS ix_symbol_sha ON symbol(project_id, source_sha256);

-- 符号关系。dst_symbol_id 为 NULL = 目标是仓库外部符号或无法静态解析。
CREATE TABLE IF NOT EXISTS edge (
    id             INTEGER PRIMARY KEY,
    project_id     INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    src_symbol_id  INTEGER NOT NULL REFERENCES symbol(id) ON DELETE CASCADE,
    dst_symbol_id  INTEGER REFERENCES symbol(id) ON DELETE CASCADE,
    src_qualname   TEXT NOT NULL,
    dst_name       TEXT NOT NULL,
    dst_qualname   TEXT,
    kind           TEXT NOT NULL,               -- call|inherits|imports|decorator|references|returns
    lineno         INTEGER,
    confidence     REAL NOT NULL DEFAULT 1.0,  -- <1 = 推断（动态调用等）
    UNIQUE(project_id, src_symbol_id, dst_qualname, dst_name, kind, lineno)
);
CREATE INDEX IF NOT EXISTS ix_edge_src ON edge(src_symbol_id);
CREATE INDEX IF NOT EXISTS ix_edge_dst ON edge(dst_symbol_id);
CREATE INDEX IF NOT EXISTS ix_edge_dstname ON edge(project_id, dst_name, kind);

-- 关键业务流程（源文档 §2.2-4 / §2.1-6 / §2.4-4）
CREATE TABLE IF NOT EXISTS flow (
    id           INTEGER PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    entry_symbol_id INTEGER REFERENCES symbol(id) ON DELETE CASCADE,
    description  TEXT,
    UNIQUE(project_id, name)
);

CREATE TABLE IF NOT EXISTS flow_step (
    id            INTEGER PRIMARY KEY,
    flow_id       INTEGER NOT NULL REFERENCES flow(id) ON DELETE CASCADE,
    ordinal       INTEGER NOT NULL,
    symbol_id     INTEGER REFERENCES symbol(id) ON DELETE SET NULL,
    qualname      TEXT,
    path          TEXT,
    lineno        INTEGER,
    note          TEXT
);
CREATE INDEX IF NOT EXISTS ix_flow_step ON flow_step(flow_id, ordinal);

-- ─────────────────────────────────────────────────────────────
-- 设计说明及其证据（源文档 §2.4-5 / §2.4-5问 / §2.5）
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS design_decision (
    id             INTEGER PRIMARY KEY,
    project_id     INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    doc_id         TEXT NOT NULL,               -- 'ADR-0018'
    title          TEXT NOT NULL,
    status         TEXT,                       -- proposed|accepted|superseded|deprecated
    body           TEXT,
    path           TEXT,                       -- 文档在仓库中的位置
    decided_at     TEXT,
    -- 声称的机制，用于判断"这条设计说明是否已不再适用"
    claims_json    TEXT,                       -- [{"concept_id":"redis-cache","pattern":"..."}]
    superseded_by  TEXT,
    UNIQUE(project_id, doc_id)
);
CREATE INDEX IF NOT EXISTS ix_decision_project ON design_decision(project_id);

-- 设计说明 → 代码位置的证据
CREATE TABLE IF NOT EXISTS design_decision_evidence (
    id           INTEGER PRIMARY KEY,
    decision_id  INTEGER NOT NULL REFERENCES design_decision(id) ON DELETE CASCADE,
    symbol_id    INTEGER REFERENCES symbol(id) ON DELETE CASCADE,
    path         TEXT,
    lineno       INTEGER,
    note         TEXT
);
CREATE INDEX IF NOT EXISTS ix_decision_evidence ON design_decision_evidence(decision_id);

-- ─────────────────────────────────────────────────────────────
-- 知识层（源文档 §2.6）
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS concept (
    id             TEXT PRIMARY KEY,            -- 'jwt' / 'db-transaction'
    name           TEXT NOT NULL,
    category       TEXT NOT NULL,              -- auth|cache|concurrency|pattern|...
    summary        TEXT NOT NULL,              -- 快速理解：简要解释概念及其用途
    principles     TEXT,                       -- 深入探索：技术原理
    tradeoffs      TEXT,                       -- 深入探索：设计权衡
    alternatives   TEXT,                       -- 深入探索：其他实现方式
    detection_json TEXT NOT NULL,              -- 声明式检测规则
    references_json TEXT,
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS concept_instance (
    id          INTEGER PRIMARY KEY,
    project_id  INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    concept_id  TEXT NOT NULL REFERENCES concept(id) ON DELETE CASCADE,
    symbol_id   INTEGER REFERENCES symbol(id) ON DELETE CASCADE,
    file_id     INTEGER REFERENCES file(id) ON DELETE CASCADE,
    path        TEXT NOT NULL,
    lineno      INTEGER NOT NULL,
    qualname    TEXT,
    evidence    TEXT NOT NULL,                 -- 命中了哪条规则
    confidence  REAL NOT NULL DEFAULT 1.0,
    UNIQUE(project_id, concept_id, path, lineno)
);
CREATE INDEX IF NOT EXISTS ix_concept_instance_concept ON concept_instance(project_id, concept_id);
CREATE INDEX IF NOT EXISTS ix_concept_instance_symbol ON concept_instance(symbol_id);

-- ─────────────────────────────────────────────────────────────
-- 检索单元（源文档 §3.1 第三层 Code RAG）
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS chunk (
    id                   INTEGER PRIMARY KEY,
    project_id           INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    symbol_id            INTEGER NOT NULL REFERENCES symbol(id) ON DELETE CASCADE,
    file_id              INTEGER NOT NULL REFERENCES file(id) ON DELETE CASCADE,
    ordinal              INTEGER NOT NULL DEFAULT 0,   -- 超大符号二次切分时 >0
    part_count           INTEGER NOT NULL DEFAULT 1,
    qualname             TEXT,
    name                 TEXT,
    kind                 TEXT,
    lineno               INTEGER NOT NULL,
    end_lineno           INTEGER NOT NULL,
    header               TEXT,
    body                 TEXT NOT NULL,               -- 原始源码
    token_text           TEXT NOT NULL,               -- 预分词 token 串（FTS 正文）
    source_sha256        TEXT NOT NULL,               -- 块级哈希（过期判定精确层）
    file_content_sha256  TEXT NOT NULL,               -- 入库时文件哈希（粗筛层）
    content_kind         TEXT NOT NULL DEFAULT 'code',-- code|init|doc|config
    UNIQUE(project_id, symbol_id, ordinal)
);
CREATE INDEX IF NOT EXISTS ix_chunk_symbol ON chunk(symbol_id);
CREATE INDEX IF NOT EXISTS ix_chunk_file ON chunk(file_id);
CREATE INDEX IF NOT EXISTS ix_chunk_sha ON chunk(project_id, source_sha256);

-- FTS5 external content 虚表。
--   tokenchars '_' 让 get_user_name 保持单 token（unicode61 默认会切成 get/user/name）。
--   真正的分词在入库前由 split_identifiers 完成，token_text 是已分好词的空格分隔串；
--   查询走同一个函数，保证入库与查询口径一致。
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
    token_text,
    content='chunk',
    content_rowid='id',
    tokenize = "unicode61 tokenchars '_'"
);

CREATE TRIGGER IF NOT EXISTS chunk_ai AFTER INSERT ON chunk BEGIN
    INSERT INTO chunk_fts(rowid, token_text) VALUES (new.id, new.token_text);
END;
CREATE TRIGGER IF NOT EXISTS chunk_ad AFTER DELETE ON chunk BEGIN
    INSERT INTO chunk_fts(chunk_fts, rowid, token_text) VALUES('delete', old.id, old.token_text);
END;
CREATE TRIGGER IF NOT EXISTS chunk_au AFTER UPDATE OF token_text ON chunk BEGIN
    INSERT INTO chunk_fts(chunk_fts, rowid, token_text) VALUES('delete', old.id, old.token_text);
    INSERT INTO chunk_fts(rowid, token_text) VALUES (new.id, new.token_text);
END;

-- ─────────────────────────────────────────────────────────────
-- 向量
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS embedding_model (
    model_id    TEXT PRIMARY KEY,               -- 'bge-m3@1024'
    provider    TEXT,
    dim         INTEGER NOT NULL,
    space       TEXT NOT NULL DEFAULT 'cosine',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS embedding (
    chunk_id    INTEGER NOT NULL REFERENCES chunk(id) ON DELETE CASCADE,
    model_id    TEXT NOT NULL REFERENCES embedding_model(model_id),
    vec         BLOB NOT NULL,                 -- float32 LE
    text_sha256 TEXT NOT NULL,                 -- 被 embed 文本的哈希（内容未变可复用向量）
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (chunk_id, model_id)
);

-- ─────────────────────────────────────────────────────────────
-- 变更与测试证据（源文档 §2.4-6 / §2.5）
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS change_record (
    id            INTEGER PRIMARY KEY,
    project_id    INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    commit_sha    TEXT,
    source        TEXT NOT NULL,               -- git | external_agent
    summary       TEXT,
    rationale     TEXT,                        -- 任务记录：为什么改
    actor         TEXT,
    occurred_at   TEXT,
    added_json    TEXT,
    removed_json  TEXT,
    modified_json TEXT,
    impact_json   TEXT
);
CREATE INDEX IF NOT EXISTS ix_change_project ON change_record(project_id, id DESC);

CREATE TABLE IF NOT EXISTS test_record (
    id           INTEGER PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    commit_sha   TEXT,
    nodeid       TEXT NOT NULL,                -- 'tests/test_x.py::test_y'
    outcome      TEXT NOT NULL,                -- passed|failed|skipped|error
    duration_s   REAL,
    message      TEXT,
    symbol_id    INTEGER REFERENCES symbol(id) ON DELETE SET NULL,
    recorded_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_test_project ON test_record(project_id, id DESC);

-- ─────────────────────────────────────────────────────────────
-- 索引与新鲜度（源文档 §2.4 / §6「持续认知能力」）
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS index_run (
    id               INTEGER PRIMARY KEY,
    project_id       INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    base_commit      TEXT,
    head_commit      TEXT NOT NULL,
    mode             TEXT NOT NULL,            -- full|incremental
    started_at       TEXT,
    finished_at      TEXT,
    ok               INTEGER NOT NULL DEFAULT 0,
    files_total      INTEGER,
    files_changed    INTEGER,
    symbols_added    INTEGER,
    symbols_removed  INTEGER,
    chunks_added     INTEGER,
    chunks_updated   INTEGER,
    chunks_deleted   INTEGER,
    stale_chunks     INTEGER,
    stats_json       TEXT
);
CREATE INDEX IF NOT EXISTS ix_index_run_project ON index_run(project_id, id DESC);

CREATE TABLE IF NOT EXISTS file_snapshot (
    project_id     INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    commit_sha     TEXT NOT NULL,
    path           TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    blob_sha       TEXT,
    PRIMARY KEY (project_id, commit_sha, path)
);

CREATE TABLE IF NOT EXISTS staleness_report (
    id            INTEGER PRIMARY KEY,
    project_id    INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    commit_sha    TEXT NOT NULL,
    total_chunks  INTEGER,
    stale_chunks  INTEGER,
    stale_rate    REAL,
    by_reason     TEXT                         -- JSON
);

-- 粗筛视图：入库时的文件哈希 vs 当前快照哈希。
-- 文件变了但符号没变时，这里会误报——精确判定要用 chunk.source_sha256。
CREATE VIEW IF NOT EXISTS v_stale_candidate AS
SELECT c.id AS chunk_id, c.project_id, c.qualname, c.file_id, f.path
FROM chunk c
JOIN file f ON f.id = c.file_id
JOIN repo_state rs ON rs.project_id = c.project_id
JOIN file_snapshot s
  ON s.project_id = c.project_id
 AND s.path = f.path
 AND s.commit_sha = rs.head_commit
WHERE c.file_content_sha256 <> s.content_sha256;

-- ─────────────────────────────────────────────────────────────
-- Agent 运行状态（源文档 §3.1 第四层「Agent 任务状态」）
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_task (
    id             TEXT PRIMARY KEY,
    project_id     INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    conversation_id TEXT NOT NULL,
    question       TEXT NOT NULL,
    status         TEXT NOT NULL,              -- queued|running|completed|failed|abstained|interrupted
    reason         TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at    TEXT
);
CREATE INDEX IF NOT EXISTS ix_agent_task_conversation ON agent_task(conversation_id, created_at);

-- 事件溯源：工具结果先落事件，再由上下文装配折成 messages。
-- 这样"账本里看到的"与"模型看到的"永远来自同一份记录。
CREATE TABLE IF NOT EXISTS agent_event (
    id          INTEGER PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES agent_task(id) ON DELETE CASCADE,
    type        TEXT NOT NULL,                 -- user.message|assistant.message|assistant.tool_calls|
                                             -- tool.finished|assistant.answer|task.error
    payload_json TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_agent_event_task ON agent_event(task_id, id);

-- 会话展示历史独立于模型的六轮窗口；投影保留结构化来源和请求目标。
CREATE TABLE IF NOT EXISTS conversation (
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '新对话',
    pinned INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    last_read_at TEXT NOT NULL DEFAULT '',
    focus_json TEXT NOT NULL DEFAULT '{}',
    exploration_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY(project_id, id)
);
CREATE TABLE IF NOT EXISTS conversation_turn (
    project_id INTEGER NOT NULL,
    conversation_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    task_id TEXT,
    question TEXT NOT NULL,
    reading_json TEXT,
    answer_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'running',
    legacy INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY(project_id, conversation_id, request_id),
    FOREIGN KEY(project_id,conversation_id) REFERENCES conversation(project_id,id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_conversation_running
    ON conversation_turn(project_id,conversation_id) WHERE status = 'running';
CREATE INDEX IF NOT EXISTS ix_conversation_recent ON conversation(project_id,updated_at);
CREATE INDEX IF NOT EXISTS ix_conversation_turn_history
    ON conversation_turn(project_id,conversation_id,created_at);

-- ─────────────────────────────────────────────────────────────
-- 评测（源文档 §6）
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS eval_task (
    id          TEXT PRIMARY KEY,               -- sha1(template|question|answer)
    project_id  INTEGER REFERENCES project(id) ON DELETE CASCADE,
    template    TEXT NOT NULL,                 -- def_loc|callers|callee|inherit|module_api|concept
    question    TEXT NOT NULL,
    answer_json TEXT NOT NULL,                 -- ground truth
    split       TEXT NOT NULL DEFAULT 'dev'    -- dev|test
);

CREATE TABLE IF NOT EXISTS eval_result (
    id           INTEGER PRIMARY KEY,
    run_id       TEXT NOT NULL,
    task_id      TEXT NOT NULL REFERENCES eval_task(id) ON DELETE CASCADE,
    arm          TEXT NOT NULL,                -- none|bm25|hybrid|symbol|concept
    rank         INTEGER,
    hit          INTEGER,
    answer_acc   REAL,
    cite_precision REAL,
    cite_recall  REAL,
    groundedness REAL,
    stale_cite   REAL,
    abstained    INTEGER,
    tokens_in    INTEGER,
    tokens_out   INTEGER,
    latency_ms   INTEGER,
    raw_json     TEXT
);
CREATE INDEX IF NOT EXISTS ix_eval_result_run ON eval_result(run_id, arm);
