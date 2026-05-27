from __future__ import annotations

from task_manager.parser import existing_hashes, parse_text
from task_manager.writer import insert_task, remove_task, stamp_hashes


def test_stamp_hashes_adds_to_unstamped():
    text = (
        "## p\n"
        "- [ ] (a4f9c): already stamped\n"
        "- [ ] api: needs hash\n"
        "- [ ] no tag here\n"
    )
    existing = existing_hashes(text)
    new_text, stamped = stamp_hashes(text, existing)
    assert len(stamped) == 2
    # Existing hash should still be there once
    assert new_text.count("(a4f9c)") == 1
    # The two new hashes appear in the text
    for line_no, h in stamped.items():
        assert f"({h})" in new_text


def test_stamp_preserves_tag():
    text = "## p\n- [ ] api: build it\n"
    existing = set()
    new_text, stamped = stamp_hashes(text, existing)
    h = list(stamped.values())[0]
    assert f"- [ ] api({h}): build it" in new_text


def test_stamp_no_tag_format():
    text = "## p\n- [ ] just text\n"
    existing = set()
    new_text, stamped = stamp_hashes(text, existing)
    h = list(stamped.values())[0]
    assert f"- [ ] ({h}): just text" in new_text


def test_stamp_then_parse_roundtrip():
    text = "## p\n- [ ] api: thing\n- [ ] (a4f9c): other\n"
    existing = existing_hashes(text)
    new_text, _ = stamp_hashes(text, existing)
    doc = parse_text(new_text)
    assert len(doc.tasks_by_hash) == 2
    assert "a4f9c" in doc.tasks_by_hash
    assert all(not h.startswith("__new") for h in doc.tasks_by_hash)


def test_insert_top_level():
    text = (
        "## backend\n"
        "- [ ] (aaaaa): existing\n"
    )
    new_text = insert_task(
        text,
        project="backend",
        parent_hash=None,
        tag=None,
        description="new task",
        hash="bbbbb",
    )
    assert "(bbbbb): new task" in new_text
    doc = parse_text(new_text)
    assert len(doc.projects[0].tasks) == 2


def test_insert_subtask_indent():
    text = (
        "## p\n"
        "- [ ] (aaaaa): parent\n"
    )
    new_text = insert_task(
        text,
        project="p",
        parent_hash="aaaaa",
        tag="t",
        description="child",
        hash="bbbbb",
    )
    doc = parse_text(new_text)
    assert doc.tasks_by_hash["bbbbb"].parent_hash == "aaaaa"


def test_insert_subtask_after_existing_subtasks():
    text = (
        "## p\n"
        "- [ ] (aaaaa): parent\n"
        "  - [ ] (bbbbb): existing child\n"
    )
    new_text = insert_task(
        text,
        project="p",
        parent_hash="aaaaa",
        tag=None,
        description="another",
        hash="ccccc",
    )
    doc = parse_text(new_text)
    assert doc.tasks_by_hash["ccccc"].parent_hash == "aaaaa"
    assert len(doc.children_of("aaaaa")) == 2


def test_insert_creates_missing_project():
    text = "## one\n- [ ] (aaaaa): a\n"
    new_text = insert_task(
        text,
        project="two",
        parent_hash=None,
        tag=None,
        description="b",
        hash="bbbbb",
    )
    doc = parse_text(new_text)
    names = [p.name for p in doc.projects]
    assert "two" in names


def test_remove_leaf():
    text = (
        "## p\n"
        "- [ ] (aaaaa): keep\n"
        "- [ ] (bbbbb): remove\n"
    )
    new_text = remove_task(text, "bbbbb")
    doc = parse_text(new_text)
    assert "bbbbb" not in doc.tasks_by_hash
    assert "aaaaa" in doc.tasks_by_hash


def test_remove_parent_removes_subtree():
    text = (
        "## p\n"
        "- [ ] (aaaaa): parent\n"
        "  - [ ] (bbbbb): child\n"
        "  description line\n"
        "- [ ] (ccccc): sibling\n"
    )
    new_text = remove_task(text, "aaaaa")
    doc = parse_text(new_text)
    assert "aaaaa" not in doc.tasks_by_hash
    assert "bbbbb" not in doc.tasks_by_hash
    assert "ccccc" in doc.tasks_by_hash


def test_remove_unknown_hash_raises():
    import pytest
    text = "## p\n- [ ] (aaaaa): x\n"
    with pytest.raises(KeyError):
        remove_task(text, "fffff")
