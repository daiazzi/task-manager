from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from task_manager.server import build_app
from task_manager.store import ensure_sidecar


def _setup(tmp_path: Path) -> Path:
    p = tmp_path / "TODO.md"
    p.write_text("## p\n- [ ] (a4f9c): one\n- [ ] (b3d8a): two\n")
    ensure_sidecar(p)
    return p


def test_get_tasks(tmp_path: Path):
    p = _setup(tmp_path)
    client = TestClient(build_app(p))
    r = client.get("/api/tasks")
    assert r.status_code == 200
    data = r.json()
    assert data["todo_path"]
    assert len(data["projects"]) == 1
    hashes = {t["hash"] for t in data["projects"][0]["tasks"]}
    assert hashes == {"a4f9c", "b3d8a"}


def test_post_dates(tmp_path: Path):
    p = _setup(tmp_path)
    client = TestClient(build_app(p))
    r = client.post(
        "/api/tasks/a4f9c/dates",
        json={"start": "2026-06-01", "end": "2026-06-10"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["start"] == "2026-06-01"
    assert body["end"] == "2026-06-10"


def test_post_dates_invalid(tmp_path: Path):
    p = _setup(tmp_path)
    client = TestClient(build_app(p))
    r = client.post("/api/tasks/a4f9c/dates", json={"start": "bad"})
    assert r.status_code == 400


def test_post_dates_inverted(tmp_path: Path):
    p = _setup(tmp_path)
    client = TestClient(build_app(p))
    r = client.post(
        "/api/tasks/a4f9c/dates", json={"start": "2026-06-10", "end": "2026-06-01"}
    )
    assert r.status_code == 400


def test_post_dates_unknown_hash(tmp_path: Path):
    p = _setup(tmp_path)
    client = TestClient(build_app(p))
    r = client.post("/api/tasks/fffff/dates", json={"start": "2026-06-01"})
    assert r.status_code == 404


def test_refresh(tmp_path: Path):
    p = _setup(tmp_path)
    client = TestClient(build_app(p))
    r = client.post("/api/refresh")
    assert r.status_code == 200
    assert "projects" in r.json()


def test_index_html(tmp_path: Path):
    p = _setup(tmp_path)
    client = TestClient(build_app(p))
    r = client.get("/")
    assert r.status_code == 200
    assert "<html" in r.text.lower()
