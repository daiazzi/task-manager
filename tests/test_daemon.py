from __future__ import annotations

import time
import urllib.request
from pathlib import Path

import pytest

from task_manager import daemon as daemon_mod


def _wait_for_url(url: str, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.1)
    return False


@pytest.fixture
def todo(tmp_path: Path) -> Path:
    p = tmp_path / "TODO.md"
    p.write_text("# t\n\n## p\n- [ ] (aaaaa): x\n")
    return p


def test_status_empty(todo: Path):
    assert daemon_mod.read_status(todo) == (None, None)


def test_start_then_stop(todo: Path):
    pid, url = daemon_mod.start(todo)
    try:
        assert isinstance(pid, int)
        assert url.startswith("http://127.0.0.1:")
        assert _wait_for_url(url + "/api/tasks"), "daemon never became reachable"
        running_pid, running_url = daemon_mod.read_status(todo)
        assert running_pid == pid
        assert running_url == url
    finally:
        killed = daemon_mod.stop(todo)
        assert killed == pid


def test_double_start_refused(todo: Path):
    pid, _ = daemon_mod.start(todo)
    try:
        with pytest.raises(RuntimeError, match="already running"):
            daemon_mod.start(todo)
    finally:
        daemon_mod.stop(todo)


def test_stop_when_not_running(todo: Path):
    assert daemon_mod.stop(todo) is None


def test_stop_cleans_stale_pid(todo: Path):
    from task_manager.store import ensure_sidecar, sidecar_dir
    ensure_sidecar(todo)
    (sidecar_dir(todo) / "daemon.pid").write_text("99999999\n")
    (sidecar_dir(todo) / "daemon.url").write_text("http://127.0.0.1:1\n")
    assert daemon_mod.stop(todo) is None
    assert not (sidecar_dir(todo) / "daemon.pid").exists()
