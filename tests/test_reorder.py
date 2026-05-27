from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from task_manager.parser import parse, parse_text
from task_manager.server import build_app
from task_manager.store import ensure_sidecar
from task_manager.writer import reorder_tasks


# --- writer.reorder_tasks ----------------------------------------------------


def test_reorder_top_level():
    text = (
        "## p\n"
        "- [ ] (aaaaa): one\n"
        "- [ ] (bbbbb): two\n"
        "- [ ] (ccccc): three\n"
    )
    new_text = reorder_tasks(text, ["ccccc", "aaaaa", "bbbbb"])
    doc = parse_text(new_text)
    order = [t.hash for t in doc.projects[0].tasks]
    assert order == ["ccccc", "aaaaa", "bbbbb"]


def test_reorder_preserves_descriptions():
    text = (
        "## p\n"
        "- [ ] (aaaaa): one\n"
        "  detailed description for one\n"
        "  with two lines\n"
        "- [ ] (bbbbb): two\n"
        "  description for two\n"
    )
    new_text = reorder_tasks(text, ["bbbbb", "aaaaa"])
    assert new_text.index("(bbbbb)") < new_text.index("(aaaaa)")
    assert "detailed description for one" in new_text
    assert "with two lines" in new_text
    assert "description for two" in new_text


def test_reorder_preserves_subtasks():
    text = (
        "## p\n"
        "- [ ] (aaaaa): parent A\n"
        "  - [ ] (a1111): child A1\n"
        "  - [ ] (a2222): child A2\n"
        "- [ ] (bbbbb): parent B\n"
    )
    new_text = reorder_tasks(text, ["bbbbb", "aaaaa"])
    doc = parse_text(new_text)
    order = [t.hash for t in doc.projects[0].tasks]
    assert order == ["bbbbb", "aaaaa"]
    assert doc.tasks_by_hash["a1111"].parent_hash == "aaaaa"
    assert doc.tasks_by_hash["a2222"].parent_hash == "aaaaa"


def test_reorder_subtasks_only():
    text = (
        "## p\n"
        "- [ ] (aaaaa): parent\n"
        "  - [ ] (b1111): c1\n"
        "  - [ ] (b2222): c2\n"
        "  - [ ] (b3333): c3\n"
    )
    new_text = reorder_tasks(text, ["b3333", "b1111", "b2222"])
    doc = parse_text(new_text)
    children_order = [c.hash for c in doc.children_of("aaaaa")]
    assert children_order == ["b3333", "b1111", "b2222"]


def test_reorder_unknown_hash_raises():
    text = "## p\n- [ ] (aaaaa): x\n"
    with pytest.raises(KeyError):
        reorder_tasks(text, ["aaaaa", "fffff"])


def test_reorder_non_contiguous_raises():
    text = (
        "## p\n"
        "- [ ] (aaaaa): a\n"
        "## q\n"
        "- [ ] (bbbbb): b\n"
    )
    with pytest.raises(ValueError):
        reorder_tasks(text, ["bbbbb", "aaaaa"])


# --- POST /api/tasks/reorder -------------------------------------------------


@pytest.fixture
def todo(tmp_path: Path) -> Path:
    p = tmp_path / "TODO.md"
    p.write_text(
        "## backend\n"
        "- [ ] (aaaaa): one\n"
        "- [ ] (bbbbb): two\n"
        "- [ ] (ccccc): three\n"
        "## frontend\n"
        "- [ ] (ddddd): four\n"
    )
    ensure_sidecar(p)
    return p


def test_post_reorder_happy(todo: Path):
    client = TestClient(build_app(todo))
    r = client.post(
        "/api/tasks/reorder",
        json={"project": "backend", "parent_hash": None, "order": ["ccccc", "aaaaa", "bbbbb"]},
    )
    assert r.status_code == 200, r.text
    doc = parse(todo)
    order = [t.hash for t in doc.projects[0].tasks]
    assert order == ["ccccc", "aaaaa", "bbbbb"]


def test_post_reorder_unknown_hash(todo: Path):
    client = TestClient(build_app(todo))
    r = client.post(
        "/api/tasks/reorder",
        json={"project": "backend", "parent_hash": None, "order": ["aaaaa", "fffff", "ccccc"]},
    )
    assert r.status_code == 404


def test_post_reorder_wrong_project(todo: Path):
    client = TestClient(build_app(todo))
    r = client.post(
        "/api/tasks/reorder",
        json={"project": "backend", "parent_hash": None, "order": ["aaaaa", "ddddd", "ccccc"]},
    )
    assert r.status_code == 400
    assert "not in project" in r.json()["error"]


def test_post_reorder_must_include_all_siblings(todo: Path):
    client = TestClient(build_app(todo))
    r = client.post(
        "/api/tasks/reorder",
        json={"project": "backend", "parent_hash": None, "order": ["aaaaa", "ccccc"]},
    )
    assert r.status_code == 400
    assert "sibling hashes" in r.json()["error"]


def test_post_reorder_bad_body(todo: Path):
    client = TestClient(build_app(todo))
    r = client.post("/api/tasks/reorder", json={"project": "backend"})
    assert r.status_code == 400
