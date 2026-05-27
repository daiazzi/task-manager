from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Tmp directory used as a project root."""
    return tmp_path


@pytest.fixture
def todo_file(workspace: Path) -> Path:
    p = workspace / "TODO.md"
    p.write_text("# TODO\n\n## backend\n\n- [ ] (a4f9c): build parser\n", encoding="utf-8")
    return p
