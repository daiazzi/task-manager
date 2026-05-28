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


def new_note_id(existing: set[str]) -> str:
    """Generate a note id like xabcde not already in `existing`. Mutates `existing`."""
    while True:
        candidate = "x" + secrets.token_hex(3)[:5]
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


_HEADING_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<hashes>#{1,6})(?:\s|$)")


def ensure_blank_line_after_headings(text: str) -> str:
    """Ensure there's an empty line after any markdown heading.

    Applies to headings like `# ...`, `## ...`, `### ...` (and deeper).
    Does not introduce duplicate blank lines.
    """
    lf_text, eol = _normalise(text)
    lines = lf_text.split("\n")
    out: list[str] = []

    i = 0
    while i < len(lines):
        out.append(lines[i])
        if _HEADING_RE.match(lines[i].lstrip("\ufeff")):
            # If next line exists and is non-blank, insert a blank line.
            if i + 1 < len(lines) and lines[i + 1].strip() != "":
                out.append("")
        i += 1

    return eol.join(out)


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

    return ensure_blank_line_after_headings(eol.join(lines)), stamped


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
    return ensure_blank_line_after_headings(eol.join(lines))


def insert_note(
    text: str,
    *,
    project: str,
    note_id: str,
    note_text: str,
) -> str:
    """Insert a new note bullet under the project's ### Notes section (creating it if needed)."""
    lf_text, eol = _normalise(text)
    lines = lf_text.split("\n")

    insert_idx = _ensure_notes_section(lines, project)
    new_line = f"- ({note_id}): {note_text}".rstrip()
    lines.insert(insert_idx, new_line)
    return ensure_blank_line_after_headings(eol.join(lines))


def reorder_tasks(text: str, order: list[str]) -> str:
    """Reorder a contiguous group of sibling task blocks according to `order`.

    Each hash in `order` must point to a bullet in the text, and the blocks
    (bullet + its description/subtasks up to the next same-or-shallower
    boundary) must be contiguous with no foreign content between them.
    """
    lf_text, eol = _normalise(text)
    lines = lf_text.split("\n")

    blocks: dict[str, tuple[int, int]] = {}
    for h in order:
        idx, _ = _find_bullet_by_hash(lines, h)
        if idx is None:
            raise KeyError(h)
        s, e = _block_extent(lines, idx)
        blocks[h] = (s, e)

    sorted_ranges = sorted(blocks.values())
    region_start = sorted_ranges[0][0]
    region_end = sorted_ranges[-1][1]
    cursor = region_start
    for s, e in sorted_ranges:
        if s != cursor:
            raise ValueError(f"tasks are not contiguous near line {cursor + 1}")
        cursor = e

    new_lines = lines[:region_start]
    for h in order:
        s, e = blocks[h]
        new_lines.extend(lines[s:e])
    new_lines.extend(lines[region_end:])
    return ensure_blank_line_after_headings(eol.join(new_lines))


def _block_extent(lines: list[str], start_idx: int) -> tuple[int, int]:
    """Range [start, end) of lines belonging to the task at start_idx."""
    bullet = _BULLET_RE.match(lines[start_idx])
    assert bullet is not None
    base_indent = _indent_width(bullet.group("indent"))
    end = start_idx + 1
    while end < len(lines):
        ln = lines[end]
        if _is_h2(ln):
            break
        m = _BULLET_RE.match(ln)
        if m and _indent_width(m.group("indent")) <= base_indent:
            break
        end += 1
    return start_idx, end


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
        return ensure_blank_line_after_headings(eol.join(lines))
    raise KeyError(hash)


def set_description(text: str, hash: str, description: str) -> str:
    """Replace a task's description (including continuation lines) by hash.

    This updates the bullet's inline description and any following "description
    continuation" lines, but preserves any subtasks (checkbox bullets) and the
    rest of the document structure.
    """
    lf_text, eol = _normalise(text)
    lines = lf_text.split("\n")

    idx, _ = _find_bullet_by_hash(lines, hash)
    if idx is None:
        raise KeyError(hash)

    m = _BULLET_RE.match(lines[idx])
    assert m is not None
    indent = m.group("indent")
    marker = m.group("marker")
    check = m.group("check")
    body = (m.group("body") or "").strip()

    stamped = _BODY_STAMPED_RE.match(body)
    if not stamped:
        # We only support editing stamped tasks (hash must be present).
        raise KeyError(hash)

    tag = stamped.group("tag")
    h = stamped.group("hash").lower()
    if h != hash.lower():
        raise KeyError(hash)

    # New description lines: first line stays on the bullet; remaining lines
    # become continuation lines indented under the bullet.
    desc_lines = (description or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    first = (desc_lines[0] if desc_lines else "").rstrip()
    rest = [ln.rstrip() for ln in desc_lines[1:]]
    while rest and not rest[-1].strip():
        rest.pop()

    prefix = f"{tag}({h}):" if tag else f"({h}):"
    lines[idx] = f"{indent}{marker} [{check}] {prefix} {first}".rstrip()

    # Replace existing continuation lines until the first checkbox bullet (any
    # indent) or the next H2.
    end = idx + 1
    while end < len(lines):
        ln = lines[end]
        if _is_h2(ln):
            break
        if _BULLET_RE.match(ln):
            break
        end += 1

    cont_indent = indent + "  "
    new_cont = [cont_indent + ln if ln != "" else "" for ln in rest]
    lines[idx + 1 : end] = new_cont

    return ensure_blank_line_after_headings(eol.join(lines))


def remove_task(text: str, hash: str) -> str:
    """Remove a task bullet (and any subtree if it's a parent)."""
    lf_text, eol = _normalise(text)
    lines = lf_text.split("\n")

    start, end = _find_task_span(lines, hash)
    if start is None:
        raise KeyError(hash)

    del lines[start:end]
    return ensure_blank_line_after_headings(eol.join(lines))


def stamp_note_hashes(text: str, existing: set[str]) -> tuple[str, dict[int, str]]:
    """Stamp ids into unstamped note bullets under ### Notes headings.

    Returns (new_text, stamped_map) where stamped_map keys are 1-based line numbers.
    """
    lf_text, eol = _normalise(text)
    lines = lf_text.split("\n")
    stamped: dict[int, str] = {}

    in_notes = False
    for i, line in enumerate(lines):
        s = line.lstrip()
        if s.startswith("## ") or s == "##":
            in_notes = False
            continue
        if _is_notes_h3(line):
            in_notes = True
            continue
        if not in_notes:
            continue
        # Note bullet is a non-checkbox bullet (same as parser semantics)
        if _BULLET_RE.match(line):
            in_notes = False
            continue
        m = re.match(r"^(?P<indent>[ \t]*)(?P<marker>[-*])\s+(?!\[(?: |x|X)\])(?P<body>.*)$", line)
        if not m:
            continue
        body = (m.group("body") or "").strip()
        if re.match(r"^\(x[0-9a-fA-F]{5}\)\s*:\s*", body):
            continue
        note_id = new_note_id(existing)
        stamped[i + 1] = note_id
        indent = m.group("indent")
        marker = m.group("marker")
        # Preserve body exactly, just prefix the id.
        new_body = f"({note_id}): {body}".rstrip()
        lines[i] = f"{indent}{marker} {new_body}".rstrip()

    return ensure_blank_line_after_headings(eol.join(lines)), stamped


def remove_note(text: str, note_id: str) -> str:
    """Remove a note block with id x<5hex> from a ### Notes section."""
    if not re.fullmatch(r"x[0-9a-f]{5}", note_id):
        raise ValueError("invalid note id")
    lf_text, eol = _normalise(text)
    lines = lf_text.split("\n")

    start, end = _find_note_span(lines, note_id)
    if start is None:
        raise KeyError(note_id)
    del lines[start:end]
    return ensure_blank_line_after_headings(eol.join(lines))


def set_note_content(text: str, note_id: str, content: str) -> str:
    """Replace the content of a note block (including continuation lines)."""
    if not re.fullmatch(r"x[0-9a-fA-F]{5}", note_id):
        raise ValueError("invalid note id")
    lf_text, eol = _normalise(text)
    lines = lf_text.split("\n")

    start, end = _find_note_span(lines, note_id.lower())
    if start is None:
        raise KeyError(note_id)

    m = re.match(
        r"^(?P<indent>[ \t]*)(?P<marker>[-*])\s+(?!\[(?: |x|X)\])(?P<body>.*)$",
        lines[start],
    )
    assert m is not None
    indent = m.group("indent")
    marker = m.group("marker")

    body_lines = (content or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    first = (body_lines[0] if body_lines else "").rstrip()
    rest = [ln.rstrip() for ln in body_lines[1:]]
    while rest and not rest[-1].strip():
        rest.pop()

    new_first = f"{indent}{marker} ({note_id.lower()}): {first}".rstrip()
    cont_indent = indent + "  "
    new_rest = [cont_indent + ln if ln != "" else "" for ln in rest]
    lines[start:end] = [new_first, *new_rest]
    return ensure_blank_line_after_headings(eol.join(lines))


# --- helpers ----------------------------------------------------------------


def _project_heading_re(project: str) -> re.Pattern[str]:
    return re.compile(r"^##\s+" + re.escape(project) + r"\s*$")


def _is_h2(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("## ") or s == "##"


def _is_notes_h3(line: str) -> bool:
    s = line.lstrip()
    return s.lower().startswith("### notes") and (
        len(s) == len("### notes") or s[len("### notes")] in (" ", "\t")
    )


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
        # Insert before a Notes section if present in the no-project region
        notes_idx = next((i for i, ln in enumerate(lines[:first_h2]) if _is_notes_h3(ln)), None)
        if notes_idx is not None:
            end = _trim_trailing_blank(lines, notes_idx)
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
    # If the project has a Notes section, keep Notes at the end by inserting before it.
    notes_idx = next(
        (i for i in range(heading_idx + 1, section_end) if _is_notes_h3(lines[i])),
        None,
    )
    if notes_idx is not None:
        end = _trim_trailing_blank(lines, notes_idx)
        return end, 0
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


def _ensure_notes_section(lines: list[str], project: str) -> int:
    """Ensure the given project has a ### Notes section. Returns insertion index for the first note."""
    from .models import NO_PROJECT

    if project == NO_PROJECT:
        first_h2 = next((i for i, ln in enumerate(lines) if _is_h2(ln)), len(lines))
        # Search for existing Notes in the no-project region
        for i in range(0, first_h2):
            if _is_notes_h3(lines[i]):
                return i + 1
        # Create Notes heading at end of no-project region
        end = _trim_trailing_blank(lines, first_h2)
        block = ["", "### Notes", ""]
        lines[end:end] = block
        return end + 3

    # Locate project heading
    heading_re = _project_heading_re(project)
    heading_idx = next((i for i, ln in enumerate(lines) if heading_re.match(ln)), None)
    if heading_idx is None:
        # Create project section at end, with Notes
        end = len(lines)
        while end > 0 and lines[end - 1] == "":
            end -= 1
        block = ["", f"## {project}", "", "### Notes", ""]
        lines[end:end] = block
        return end + len(block)

    # Determine project section bounds
    section_end = len(lines)
    for j in range(heading_idx + 1, len(lines)):
        if _is_h2(lines[j]):
            section_end = j
            break

    # If Notes exists, insert right after heading.
    for i in range(heading_idx + 1, section_end):
        if _is_notes_h3(lines[i]):
            return i + 1

    # Create Notes at end of project section
    end = _trim_trailing_blank(lines, section_end)
    block = ["", "### Notes", ""]
    lines[end:end] = block
    return end + 3


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


def _find_note_span(lines: list[str], note_id: str) -> tuple[int | None, int]:
    """Return (start, end) indices for the note block starting at (note_id)."""
    target = f"({note_id})"
    in_notes = False
    notes_heading_indent: int | None = None

    for i, line in enumerate(lines):
        if _is_h2(line):
            in_notes = False
            notes_heading_indent = None
            continue
        if _is_notes_h3(line):
            in_notes = True
            notes_heading_indent = _indent_width(line[: len(line) - len(line.lstrip(" \t"))])
            continue
        if not in_notes:
            continue
        if _BULLET_RE.match(line):
            in_notes = False
            notes_heading_indent = None
            continue
        m = re.match(r"^(?P<indent>[ \t]*)(?P<marker>[-*])\s+(?!\[(?: |x|X)\])(?P<body>.*)$", line)
        if not m:
            continue
        body = m.group("body") or ""
        if target not in body:
            continue
        start = i
        base_indent = _indent_width(m.group("indent"))
        end = i + 1
        while end < len(lines):
            ln = lines[end]
            if _is_h2(ln):
                break
            if _BULLET_RE.match(ln):
                break
            if _is_notes_h3(ln):
                break
            m2 = re.match(
                r"^(?P<indent>[ \t]*)(?P<marker>[-*])\s+(?!\[(?: |x|X)\])(?P<body>.*)$",
                ln,
            )
            if m2:
                ind = _indent_width(m2.group("indent"))
                if ind == base_indent:
                    break
            end += 1
        return start, end

    return None, 0
