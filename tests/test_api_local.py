"""本机选择框契约：不在自动测试里弹桌面窗口，不触发导入或模型。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from codeinsight.api import local
from codeinsight.api.app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), client=("127.0.0.1", 50000))


def test_selected_path_and_cancel(client: TestClient, monkeypatch, tmp_path: Path) -> None:
    picker = Mock(side_effect=[str(tmp_path), None])
    monkeypatch.setattr(local, "choose_folder", picker)
    assert client.post("/local/select-folder").json() == {"root_path": str(tmp_path)}
    assert client.post("/local/select-folder").json() == {"root_path": None}
    assert picker.call_count == 2


@pytest.mark.parametrize("origin", ["https://other.example", "null"])
def test_remote_origin_cannot_open_dialog(client: TestClient, monkeypatch, origin: str) -> None:
    picker = Mock()
    monkeypatch.setattr(local, "choose_folder", picker)
    assert client.post("/local/select-folder", headers={"Origin": origin}).status_code == 403
    picker.assert_not_called()


def test_remote_client_cannot_open_dialog(monkeypatch) -> None:
    picker = Mock()
    monkeypatch.setattr(local, "choose_folder", picker)
    client = TestClient(create_app(), client=("192.168.1.10", 50000))
    assert client.post("/local/select-folder").status_code == 403
    picker.assert_not_called()


def test_picker_failure_releases_lock(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(local, "choose_folder", Mock(side_effect=OSError("no desktop")))
    response = client.post("/local/select-folder")
    assert response.status_code == 503
    assert response.json()["error"]["hint"]
    monkeypatch.setattr(local, "choose_folder", lambda: None)
    assert client.post("/local/select-folder").status_code == 200


def test_only_one_picker_and_timeout(client: TestClient, monkeypatch) -> None:
    local._picker_lock.acquire()
    try:
        assert client.post("/local/select-folder").status_code == 409
    finally:
        local._picker_lock.release()
    monkeypatch.setattr(
        local, "choose_folder", Mock(side_effect=subprocess.TimeoutExpired("picker", 300))
    )
    response = client.post("/local/select-folder")
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "timeout"


def test_native_result_validation(monkeypatch, tmp_path: Path) -> None:
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, '{"root_path": null}'))
    monkeypatch.setattr(local.subprocess, "run", runner)
    assert local.choose_folder() is None
    runner.return_value.stdout = json.dumps({"root_path": str(tmp_path)})
    assert local.choose_folder() == str(tmp_path.resolve())
    runner.return_value.stdout = json.dumps({"root_path": str(tmp_path / "missing")})
    with pytest.raises(ValueError, match="不存在"):
        local.choose_folder()
    assert runner.call_args.kwargs["timeout"] == 300
