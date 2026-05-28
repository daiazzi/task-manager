# todofile — Requirements

## 1. Purpose

A local-first task manager for dev/data projects. The user's `TODO.md` stays the
single human-edited, git-tracked, GitHub-renderable source of truth. The
manager adds a date/timeline view backed by a sidecar YAML file, plus a small
web UI for visualising and editing dates.

It is invoked per-file: each `TODO.md` has its own sidecar directory next to it.

## 2. Goals

- Local, ephemeral server — launched on demand, stopped with Ctrl-C.
- Markdown remains the source of truth for task existence, hierarchy, project
  grouping, tag, description, and done state.
- Add structured metadata (dates) in a sidecar YAML — markdown stays clean.
- Visualise tasks as a Gantt timeline and a calendar grid (toggle between them).
- Filter by project.
- CLI to add and remove tasks without hand-editing the markdown.
- Work inside the VS Code Simple Browser so the user can keep everything in one
  window.

## 3. Non-goals (v1)

- No multi-user, sync, auth, or remote collaboration.
- No reminders, notifications, or background daemon.
- No automatic file watching — refresh is a button in the UI.
- No archive of deleted tasks (deferred — see §11).

## 4. Core concepts

### 4.1 Source of truth

- `TODO.md` is authoritative for: which tasks exist, their hierarchy, project
  grouping, tag, description text, done/not-done state.
- `tasks.yaml` is authoritative for: start date, end date, created timestamp,
  completed timestamp.
- The manager edits `TODO.md` in three narrow cases only:
  1. Stamping a 5-character hash into a new task on first sight.
  2. `todofile add` — inserts a new bullet.
  3. `todofile remove <hash>` — deletes a bullet.

### 4.2 Task identity

Every task carries a 5-character lowercase hex hash in parentheses, e.g.
`(a4f9c)`. Hashes are:

- Generated randomly, collision-checked against existing hashes in the file.
- Stable across edits to the surrounding text — the hash is the identity.
- Stamped into `TODO.md` by the manager when it first encounters a task without
  one.

### 4.3 Sidecar directory

For a TODO file at `/path/to/myTODO.md`, the manager creates and reads from:

```
/path/to/.myTODO.md.dir/
    tasks.yaml      # metadata: dates, timestamps, per-task
    config.yaml     # port, defaults (extensible)
```

This naming gives a stable namespace per TODO file in the same folder.

## 5. TODO.md format

### 5.1 Structure

```markdown
# <document title>            <-- ignored

## <project name>             <-- defines a project

- [ ] <tag>(<hash>): <task description first line>
  <continued description, free text or non-checkbox bullets>
  - sub-bullet of description (no checkbox)
  - [ ] <tag>(<hash>): <subtask description>

- [x] (<hash>): completed task
```

### 5.2 Parsing rules

- `# heading` (H1) is ignored.
- `## heading` (H2) starts a project. Tasks belong to the most recent H2.
- A **task** is any indented bullet starting with `- [ ]`, `- [x]`, `* [ ]`, or
  `* [x]`.
- Indentation is lenient — tabs or any number of spaces. Nesting depth is
  determined by relative indent compared to the parent.
- A task's **description** is the text after `:` on the bullet line, plus all
  subsequent lines that are not checkbox bullets, up to:
  - the next checkbox bullet at the same or lesser indent, or
  - a new `##` heading, or
  - end of file.
- Non-checkbox bullets (`- text`, `* text`) under a task are part of its
  description.
- A **subtask** is a checkbox bullet indented more than its parent. Maximum
  nesting is 2 levels (task → subtask). Deeper checkbox bullets are flattened
  to level 2 with a warning.
- **Tag** is optional. Format: `<tag>(<hash>):` with tag, or `(<hash>):`
  without. Tag is a free-form category, does not inherit from parent.
- **Hash** is mandatory in canonical form, but tasks added by hand without a
  hash are accepted on read — the manager stamps a hash into the file.
- `[x]` marks a task as done; `[ ]` as not done.

### 5.3 Edge cases the parser must handle

- Mixed tab/space indentation in the same file.
- Tasks under no `##` heading → grouped under a synthetic `(no project)`.
- Blank lines inside a description.
- A description that contains its own (non-checkbox) bullet list.
- A subtask with a deeper sub-sub-task (flatten + warn).
- Duplicate hashes (warn, keep the first occurrence, drop the rest from yaml).
- Trailing whitespace, Windows line endings.

## 6. CLI

Built with [`rich-click`](https://github.com/ewels/rich-click).

### 6.1 Top-level

| Command | Purpose |
|---|---|
| `todofile <path/to/TODO.md>` | Auto-init if needed, start the web server, open browser. |
| `todofile init <path/to/TODO.md>` | Create the sidecar dir and stamp hashes into existing tasks. Does not start the server. |
| `todofile add ...` | Add a task (see below). |
| `todofile remove <hash>` | Remove the task with the given hash from the markdown and its yaml entry. |
| `todofile help format` | Print the TODO.md format spec to the terminal with rich formatting. |

`todofile <path>` auto-inits silently if the sidecar dir does not exist.

### 6.2 `add`

```
todofile add <path/to/TODO.md> [options]
```

| Flag | Short | Meaning |
|---|---|---|
| `--description <text>` | `-d` | Task description (required). |
| `--tag <name>` | `-t` | Optional category tag. |
| `--parent <hash>` | `-p` | If set, the new task is a subtask of this hash. Inherits parent's project. |
| `--project <name>` | `-P` | Project to add under. Required if no `--parent` and the file has more than one project; otherwise inferred. |
| `--start-date <YYYY-MM-DD>` | `-s` | Start date. |
| `--end-date <YYYY-MM-DD>` | `-e` | End date. |
| `--duration <days>` | | Length in days. |

Date semantics:

- Provide any **two** of `{start, end, duration}` and the third is derived.
- Providing only `--duration` (no anchor) is an error.
- Providing all three is an error if they disagree.

Insertion point in `TODO.md`:

- Top-level task: appended to the end of its project's `##` section.
- Subtask: appended after the parent's existing subtasks.

### 6.3 `task remove`

```
todofile remove <hash> <path/to/TODO.md>
```

Removes the bullet line (and any subtask lines if the hash is a parent) from
the markdown, and drops the corresponding entry from `tasks.yaml`. If the hash
is not found, errors with a clear message.

### 6.4 `help format`

```
todofile help format
```

Prints the TODO.md format spec (a rendered version of §5 of this document)
with rich formatting. `help` is a group; future format topics can be added as
sibling subcommands.

## 7. Web UI

### 7.1 Lifecycle

- `todofile <path>` starts an ASGI server bound to `127.0.0.1` on an
  auto-selected free port, unless `config.yaml` pins one. Prints the URL and
  blocks until Ctrl-C.
- VS Code Simple Browser-compatible: plain `http://127.0.0.1:<port>`, no
  websockets required for v1 (manual refresh is enough).

### 7.2 Layout

- **Header**: project filter (multi-select chips), view toggle (Gantt /
  Calendar), "show completed" toggle (on by default), refresh button.
- **Left pane**: flat list of tasks (project name as a section header,
  subtasks indented under parents). Each row shows tag, description, current
  dates, done state.
- **Right pane**: the visualisation —
  - **Gantt view**: horizontal bars across a date axis, one row per task.
  - **Calendar view**: month grid; tasks appear on the days they span.
- Toggling between Gantt and Calendar swaps only the right pane.

### 7.3 Editing

- Inline editors per task row: start date, end date.
- Edits POST to the backend, which updates `tasks.yaml` only — never the
  markdown.
- Setting `[x]` / `[ ]` in the markdown is the only way to toggle done. The UI
  shows done state but does not toggle it.

### 7.4 Sorting

- Tasks sorted by start date ascending. Undated tasks at the bottom.
- Subtasks always grouped under their parent regardless of dates.

## 8. Sidecar files

### 8.1 `tasks.yaml`

```yaml
tasks:
  - hash: a4f9c
    start: 2026-06-01
    end: 2026-06-10
    created: 2026-05-27T14:32:11
    completed: null
  - hash: b3d8a
    start: null
    end: null
    created: 2026-05-27T14:35:02
    completed: 2026-05-28T09:12:44
```

Only metadata lives here. Hierarchy, text, tag, project, done state all come
from the markdown on each read.

### 8.2 `config.yaml`

```yaml
port: null        # null = auto-pick a free port
```

Designed to grow (default filters, theme, etc.) without breaking older files.

## 9. Dev environment

The project uses [pixi](https://pixi.sh) for environment and dependency
management. Contributors should use pixi rather than `pip` or `conda`
directly.

- Add a dep from PyPI: `pixi add --pypi <pkg>`
- Add a dep from conda-forge: `pixi add <pkg>`
- Run tests: `pixi run pytest`
- Run the CLI in dev: `pixi run todofile <path>`

The `README.md` documents this for end-users and contributors.

## 10. Out of scope for v1

- Multi-user / remote sync / auth.
- File watcher / auto-refresh.
- Notifications, reminders, recurring tasks.
- Bulk edit, drag-to-reschedule (single-row edits only).

## 11. Deferred (nice-to-have, post-v1)

- **Archive**: keep yaml entries for tasks removed from the markdown, so dates
  survive accidental deletion or branch switches. Skipped in v1 because the
  user keeps `TODO.md` in git — `git checkout` recovers it.
- **Auto-refresh**: file watcher on `TODO.md`.
- **Sub-sub-tasks** (nesting beyond 2 levels).
- **Multiple TODO files** open simultaneously in one server.
