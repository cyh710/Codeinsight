"""运行指纹描述加载状态，不把新源码误报为已加载。"""

from fastapi.testclient import TestClient

from codeinsight import runtime_version
from codeinsight.api.app import create_app


def test_root_and_health_identify_loaded_runtime_and_disk_change(monkeypatch):
    with TestClient(create_app()) as client:
        first = client.get("/").json()
        assert first["runtime_revision"] == runtime_version.LOADED_REVISION
        monkeypatch.setattr(runtime_version, "current_revision", lambda: "modified-on-disk")
        for path in ("/", "/health"):
            info = client.get(path).json()
            assert info["restart_required"]
            assert info["runtime_revision"] == first["runtime_revision"]
