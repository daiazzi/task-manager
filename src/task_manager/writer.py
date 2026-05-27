from __future__ import annotations

import re
import secrets

from .parser import _BODY_STAMPED_RE, _BULLET_RE, _indent_width


def new_hash(existing: set[str]) -> str:
    """Generate a 5-hex-char hash not already in `existing`. Mutates `existing`."""
    while True:
        candidate = secrets.token_hex(3)[:5]
        if candidate not in existing:
            existing.add(candidate)
            return candidate


def _normalise(text: str) -> tuple[str, str]:
    """Return (text_with_lf, line_ending_for_output)."""
    if "\r\n" in text:
        eol = "\r\n"
    else:
        eol = "\n"
    return text.replace("\r\n", "\n").replace("\r", "\n"), eol


def stamp_hashes(text: str, existing: set[str]) -> tuple[str, dict[int, str]]:
    """Stamp hashes into unstamped task bullets. Returns (new_text, stamped_map).

    The stamped_map keys are 1-based line numbers.
    """
    lf_text, eol = _normalise(text)
    lines = lf_text.split("\n")
    stamped: dict[int, str] = {}

    for i, line in enumerate(lines):
        m = _BULLET_RE.match(line)
        if not m:
            continue
        body = m.group("body").strip()
        if _BODY_STAMPED_RE.match(body):
            continue
        # Unstamped — parse tag/desc
        tag, desc = _split_tag_desc(body)
        h = new_hash(existing)
        stamped[i + 1] = h
        indent = m.group("indent")
        marker = m.group("marker")
        check = m.group("check")
        prefix = f"{tag}({h}):" if tag else f"({h}):"
        new_line = f"{indent}{marker} [{check}] {prefix} {desc}".rstrip()
        lines[i] = new_line

    return eol.join(lines), stamped


def _split_tag_desc(body: str) -> tuple[str | None, str]:
    m = re.match(r"^(?P<tag>[A-Za-z0-9_\-]+):\s*(?P<desc>.*)$", body)
    if m:
        return m.group("tag"), m.group("desc").strip()
    return None, body.strip()


def insert_task(
    text: str,
    *,
    project: str,
    parent_hash: str | None,
    tag: str | None,
    description: str,
    hash: str,
) -> str:
    """Append a new task bullet to the markdown. Returns new text.

    Top-level tasks are appended to the end of their project section.
    Subtasks are appended after the parent's existing subtasks.
    """
    lf_text, eol = _normalise(text)
    lines = lf_text.split("\n")
    bullet_prefix = f"{tag}({hash}):" if tag else f"({hash}):"
    new_bullet_body = f"- [ ] {bullet_prefix} {description}".rstrip()

    if parent_hash is None:
        insert_idx, indent = _find_top_level_insert_point(lines, project)
        new_line = (" " * indent) + new_bullet_body
    else:
        insert_idx, indent = _find_subtask_insert_point(lines, parent_hash)
        new_line = (" " * indent) + new_bullet_body

    lines.insert(insert_idx, new_line)
    return eol.join(lines)


def set_done(text: str, hash: str, done: bool) -> str:
    """Flip the checkbox for the bullet carrying `hash`. Raises KeyError if not found."""
    lf_text, eol = _normalise(text)
    lines = lf_text.split("\n")
    target = f"({hash})"
    for i, line in enumerate(lines):
        m = _BULLET_RE.match(line)
        if not m:
            continue
        if target not in m.group("body"):
            continue
        indent = m.group("indent")
        marker = m.group("marker")
        body = m.group("body")
        new_check = "x" if done else " "
        lines[i] = f"{indent}{marker} [{new_check}] {body}".rstrip()
        return eol.join(lines)
    raise KeyError(hash)


def remove_task(text: str, hash: str) -> str:
    """Remove a task bullet (and any subtree if it's a parent)."""
    lf_text, eol = _normalise(text)
    lines = lf_text.split("\n")

    start, end = _find_task_span(lines, hash)
    if start is None:
        raise KeyError(hash)

    del lines[start:end]
    return eol.join(lines)


# --- helpers ----------------------------------------------------------------


def _project_heading_re(project: str) -> re.Pattern[str]:
    return re.compile(r"^##\s+" + re.escape(project) + r"\s*$")


def _is_h2(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("## ") or s == "##"


def _find_top_level_insert_point(lines: list[str], project: str) -> tuple[int, int]:
    """Return (insertion_line_index, indent_spaces) for a new top-level task."""
    from .models import NO_PROJECT

    # Find the project heading
    heading_idx: int | None = None
    if project == NO_PROJECT:
        # Insert at the end of the section before the first H2, or at file end if no H2
        first_h2 = next((i for i, ln in enumerate(lines) if _is_h2(ln)), None)
        if first_h2 is None:
            # whole file is no-project — append at end
            end = _trim_trailing_blank(lines, len(lines))
            return end, 0
        # before first_h2: find last non-blank
        end = _trim_trailing_blank(lines, first_h2)
        return end, 0

    heading_re = _project_heading_re(project)
    for i, ln in enumerate(lines):
        if heading_re.match(ln):
            heading_idx = i
            break
    if heading_idx is None:
        # Project doesn't exist yet — append a new section at end of file
        end = len(lines)
        # Trim trailing pure-empty entries
        while end > 0 and lines[end - 1] == "":
            end -= 1
        new_section = ["", f"## {project}", ""]
        lines[end:end] = new_section
        return end + 3, 0

    # Find end of project section
    section_end = len(lines)
    for j in range(heading_idx + 1, len(lines)):
        if _is_h2(lines[j]):
            section_end = j
            break
    end = _trim_trailing_blank(lines, section_end)
    return end, 0


def _find_subtask_insert_point(lines: list[str], parent_hash: str) -> tuple[int, int]:
    """Return (insertion_line_index, indent_spaces) for a new subtask under parent."""
    parent_idx, parent_indent = _find_bullet_by_hash(lines, parent_hash)
    if parent_idx is None:
        raise KeyError(parent_hash)

    parent_indent_width = _indent_width(lines[parent_idx][: len(lines[parent_idx]) - len(lines[parent_idx].lstrip())])

    # Walk forward past everything that "belongs" to this parent
    end = parent_idx + 1
    while end < len(lines):
        ln = lines[end]
        if _is_h2(ln):
            break
        m = _BULLET_RE.match(ln)
        if m:
            ind = _indent_width(m.group("indent"))
            if ind <= parent_indent_width:
                break
        # else: description continuation (or any non-bullet line) — belongs to parent
        end += 1

    end = _trim_trailing_blank(lines, end)
    return end, parent_indent_width + 2


def _find_bullet_by_hash(lines: list[str], hash: str) -> tuple[int | None, int]:
    """Return (line_index, indent_chars) for the bullet with the given hash."""
    target = f"({hash})"
    for i, ln in enumerate(lines):
        m = _BULLET_RE.match(ln)
        if not m:
            continue
        if target in m.group("body"):
            indent_chars = len(ln) - len(ln.lstrip(" \t"))
            return i, indent_chars
    return None, 0


def _find_task_span(lines: list[str], hash: str) -> tuple[int | None, int]:
    """Return (start, end) indices for the lines belonging to this task (incl. subtree)."""
    start, _ = _find_bullet_by_hash(lines, hash)
    if start is None:
        return None, 0
    parent_indent_width = _indent_width(lines[start][: len(lines[start]) - len(lines[start].lstrip(" \t"))])

    end = start + 1
    while end < len(lines):
        ln = lines[end]
        if _is_h2(ln):
            break
        m = _BULLET_RE.match(ln)
        if m:
            ind = _indent_width(m.group("indent"))
            if ind <= parent_indent_width:
                break
        end += 1
    return start, end


def _trim_trailing_blank(lines: list[str], end_exclusive: int) -> int:
    """Walk backward from end_exclusive over blank lines, return the new end_exclusive."""
    j = end_exclusive
    while j > 0 and not lines[j - 1].strip():
        j -= 1
    return j
