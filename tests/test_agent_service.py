"""Agent 装配入口。

CLI 传项目名、API 传项目 id，两条路必须走同一套装配——否则「命令行能跑、
接口缺一路」这类漂移迟早出现，而且没人会发现，因为没人把两边输出对起来看过。
"""

from __future__ import annotations

import pytest

from codeinsight.agent.service import ProjectNotFound, open_agent
from codeinsight.storage.sqlite import db_path


def test_open_agent_accepts_project_id_and_name(data_dir, conn) -> None:
    conn.execute("INSERT INTO project (id, name, root_path) VALUES (7, 'demo', 'D:/x')")
    conn.commit()

    by_id = open_agent(db_path(data_dir), 7)
    try:
        assert by_id.project_id == 7
        assert by_id.project_name == "demo"
    finally:
        by_id.close()

    by_name = open_agent(db_path(data_dir), "demo")
    try:
        assert by_name.project_id == 7
    finally:
        by_name.close()


def test_open_agent_unknown_project_raises(data_dir, conn) -> None:
    conn.execute("INSERT INTO project (id, name, root_path) VALUES (7, 'demo', 'D:/x')")
    conn.commit()
    with pytest.raises(ProjectNotFound):
        open_agent(db_path(data_dir), 99)
    with pytest.raises(ProjectNotFound):
        open_agent(db_path(data_dir), "nope")
