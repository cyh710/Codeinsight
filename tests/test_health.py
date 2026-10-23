"""健康检查端点。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from codeinsight.api.app import create_app


def test_health_reports_ok_and_schema_state(data_dir) -> None:
    client = TestClient(create_app())
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["schema_applied"] is True
    assert body["projects"] == 0


def test_root_returns_name_and_version(data_dir) -> None:
    client = TestClient(create_app())
    body = client.get("/").json()
    assert body["name"] == "CodeInsight"
    assert "version" in body


def test_projects_empty_before_import(data_dir) -> None:
    client = TestClient(create_app())
    assert client.get("/projects").json() == []
