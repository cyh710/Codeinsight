"""评测基础设施（M5）。

验收口径：
- 题库**从索引生成**且可复现（同 seed 同题）；
- 指标带区间；样本太小时区间退化成点估计而不是假装精确；
- 不可用的臂**如实标注**——退化的臂不能静默变成别的臂。
"""

from __future__ import annotations

import sqlite3

import pytest

from codeinsight.eval.arms import ARMS, resolve_arms
from codeinsight.eval.bench import build_tasks, persist_tasks
from codeinsight.eval.metrics import bootstrap_ci, mrr, summarize_ranks, top1_rate
from codeinsight.eval.report import ReportMeta, build_report, format_markdown
from codeinsight.eval.runner import run_arm
from codeinsight.storage.sqlite import apply_schema, open_sqlite

NAMES = [
    ("a.alpha_handler", "alpha_handler"),
    ("a.beta_handler", "beta_handler"),
    ("b.gamma_worker", "gamma_worker"),
    ("b.delta_worker", "delta_worker"),
    ("c.epsilon_service", "epsilon_service"),
    ("c.zeta_service", "zeta_service"),
    ("d.eta_helper", "eta_helper"),
    ("d.theta_helper", "theta_helper"),
]


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = open_sqlite(":memory:", row_factory=True)
    apply_schema(c)
    c.execute("INSERT INTO project (id, name, root_path) VALUES (1, 'demo', 'D:/demo')")
    c.executemany(
        "INSERT INTO file (id, project_id, path, language, content_sha256, role)"
        " VALUES (?, 1, ?, 'python', 'h', 'source')",
        [(1, "a.py"), (2, "b.py"), (3, "c.py"), (4, "d.py")],
    )
    c.execute(
        "INSERT INTO file (id, project_id, path, language, content_sha256, role)"
        " VALUES (5, 1, 'tests/test_a.py', 'python', 'h', 'test')"
    )
    c.executemany(
        "INSERT INTO symbol (id, project_id, file_id, qualname, name, kind, lineno, end_lineno,"
        " header, docstring, source_sha256)"
        " VALUES (?, 1, ?, ?, ?, 'function', ?, ?, 'def f():', ?, 'h')",
        [
            (
                index + 1,
                index % 4 + 1,
                qualname,
                name,
                index * 10 + 1,
                index * 10 + 5,
                "处理一件事并返回结果，包含足够的描述长度",
            )
            for index, (qualname, name) in enumerate(NAMES)
        ],
    )
    # 重名符号：不能当 ground truth
    c.execute(
        "INSERT INTO symbol (id, project_id, file_id, qualname, name, kind, lineno, end_lineno,"
        " header, docstring, source_sha256)"
        " VALUES (99, 1, 1, 'z.alpha_handler', 'alpha_handler', 'function', 99, 100,"
        " 'def alpha_handler():', '重复的名字', 'h')"
    )
    c.commit()
    return c


def test_tasks_are_generated_and_reproducible(conn) -> None:
    first = build_tasks(conn, project_id=1, n_per_kind=3, seed=7)
    second = build_tasks(conn, project_id=1, n_per_kind=3, seed=7)
    assert [task.task_id for task in first] == [task.task_id for task in second]
    assert {task.kind for task in first} == {"name", "docstring"}
    assert all(task.target_path for task in first)


def test_ambiguous_names_are_excluded(conn) -> None:
    tasks = build_tasks(conn, project_id=1, n_per_kind=20, seed=7)
    assert all("alpha_handler" not in task.target_qualname for task in tasks)


def test_persist_tasks_is_idempotent(conn) -> None:
    tasks = build_tasks(conn, project_id=1, n_per_kind=3, seed=7)
    persist_tasks(conn, project_id=1, tasks=tasks)
    persist_tasks(conn, project_id=1, tasks=tasks)
    count = conn.execute("SELECT COUNT(*) FROM eval_task").fetchone()[0]
    assert count == len(tasks)


def test_unknown_kind_is_rejected(conn) -> None:
    with pytest.raises(ValueError):
        build_tasks(conn, project_id=1, kinds=("nonsense",))


def test_concept_tasks_use_instances_from_source_files(conn) -> None:
    conn.execute(
        "INSERT INTO concept (id, name, category, summary, detection_json)"
        " VALUES ('jwt', 'JWT 身份认证', 'auth', '签名令牌', '{}')"
    )
    conn.executemany(
        "INSERT INTO concept_instance (project_id, concept_id, symbol_id, file_id, path, lineno,"
        " qualname, evidence, confidence) VALUES (1, 'jwt', ?, ?, ?, ?, ?, 'call jwt.decode', 1.0)",
        [
            (1, 1, "a.py", 10, "a.alpha_handler"),
            (2, 2, "b.py", 20, "b.beta_handler"),
            (1, 5, "tests/test_a.py", 3, "tests.test_a.test_handler"),
        ],
    )
    conn.commit()

    tasks = build_tasks(conn, project_id=1, n_per_kind=5, seed=7, kinds=("concept",))
    assert tasks
    assert all(task.kind == "concept" and task.match_by_qualname for task in tasks)
    assert all(task.target_qualname in {"a.alpha_handler", "b.beta_handler"} for task in tasks)
    # 问的是「哪里用了 JWT」，答到同概念的另一处实例也算对——包括测试里的用法。
    assert set(tasks[0].target_qualnames) == {
        "a.alpha_handler",
        "b.beta_handler",
        "tests.test_a.test_handler",
    }
    # 但抽中的「示例位置」只从源码里取：测试代码不是「实现在哪」的答案。
    assert tasks[0].target_qualname in {"a.alpha_handler", "b.beta_handler"}
    assert "JWT 身份认证" in tasks[0].question


def test_concept_hit_accepts_any_instance_of_that_concept() -> None:
    from codeinsight.eval.bench import BenchTask
    from codeinsight.eval.runner import _rank_of

    task = BenchTask(
        task_id="concept:jwt",
        kind="concept",
        question="哪里用了 JWT",
        target_path="a.py",
        target_lineno=10,
        target_qualname="a.alpha_handler",
        match_by_qualname=True,
        target_qualnames=("a.alpha_handler", "b.beta_handler"),
    )
    hits = [("b.py", 20, "b.beta_handler"), ("c.py", 1, "c.other")]
    assert _rank_of(task, hits) == 1

    misses = [("c.py", 1, "c.other")]
    assert _rank_of(task, misses) is None


def test_bootstrap_ci_on_constant_values_collapses() -> None:
    estimate = bootstrap_ci([1.0, 1.0, 1.0, 1.0], resamples=200)
    assert estimate.value == 1.0
    assert estimate.low == estimate.high == 1.0
    assert estimate.n == 4


def test_bootstrap_ci_admits_small_samples() -> None:
    estimate = bootstrap_ci([1.0], resamples=200)
    assert estimate.low == estimate.high == estimate.value == 1.0
    assert estimate.n == 1


def test_rank_metrics() -> None:
    ranks = [1, 2, None, 9]
    assert mrr(ranks) == pytest.approx((1 + 0.5 + 0 + 1 / 9) / 4)
    assert top1_rate(ranks) == 0.25


def test_summary_has_three_estimates() -> None:
    summary = summarize_ranks([1, 2, 3, None], k=3)
    assert set(summary) == {"hit_rate", "mrr", "top1_rate"}
    assert summary["hit_rate"].value == 0.75  # 前 3 名命中 3 道


def test_unknown_arm_is_rejected() -> None:
    with pytest.raises(KeyError):
        resolve_arms("bm25,nonsense")
    assert [arm.name for arm in resolve_arms("bm25,full")] == ["bm25", "full"]


def test_none_arm_scores_zero_without_being_skipped(conn) -> None:
    tasks = build_tasks(conn, project_id=1, n_per_kind=2, seed=7)
    run = run_arm(conn, project_id=1, tasks=tasks, arm=ARMS["none"], k=5)
    assert run.available is True
    assert all(outcome.rank is None for outcome in run.outcomes)
    assert run.summarize(k=5, kinds=("name", "docstring"), seed=7)["overall"]["mrr"].value == 0.0


def test_dense_arm_is_marked_unavailable_rather_than_degraded(conn) -> None:
    tasks = build_tasks(conn, project_id=1, n_per_kind=2, seed=7)
    run = run_arm(conn, project_id=1, tasks=tasks, arm=ARMS["hybrid"], k=5, dense_ok=False)
    assert run.available is False
    assert "稠密" in run.reason


def test_report_states_caveats_and_unavailable_arms(conn) -> None:
    tasks = build_tasks(conn, project_id=1, n_per_kind=2, seed=7)
    runs = [
        run_arm(conn, project_id=1, tasks=tasks, arm=ARMS["none"], k=5),
        run_arm(conn, project_id=1, tasks=tasks, arm=ARMS["hybrid"], k=5, dense_ok=False),
    ]
    meta = ReportMeta(
        run_id="run-test",
        project="demo",
        head_commit="abc12345",
        seed=7,
        k=5,
        kinds=("name", "docstring"),
        n_per_kind=2,
        embedding_model="BAAI/bge-m3@1024",
    )
    report = build_report(meta, runs)
    markdown = format_markdown(report)
    assert "不可用" in markdown
    assert "自动生成" in markdown
    assert "95% bootstrap" in markdown
    hybrid = next(arm for arm in report["arms"] if arm["arm"] == "hybrid")
    assert hybrid["available"] is False
