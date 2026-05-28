# todofile — Specifications

Concrete contracts. Where [requirements.md](requirements.md) says *what* and
[technical-design.md](technical-design.md) says *how*, this document says
*exactly*. Anything ambiguous in those docs is resolved here, and tests
should target the behaviours specified below.

## 1. TODO.md grammar

### 1.1 Tokens (informal)

```
DOCUMENT       := { LINE }
H1_LINE        := "#"  WS TEXT  EOL              -- ignored
H2_LINE        := "##" WS TEXT  EOL              -- starts a project
BULLET_LINE    := INDENT BULLET_MARK WS CHECKBOX WS BULLET_BODY EOL
INDENT         := { " " | "\t" }
BULLET_MARK    := "-" | "*"
CHECKBOX       := "[" (" "|"x"|"X") "]"
BULLET_BODY    := [ TAG ] "(" HASH ")" ":" WS DESCRIPTION
              |  DESCRIPTION                         -- unstamped (writer will stamp)
TAG            := [A-Za-z0-9_-]+
HASH           := [0-9a-f]{5}
DESCRIPTION    := any text to end of line
DESC_CONT      := INDENT (non-checkbox content)      -- attached to most recent task
```

### 1.2 Project assignment

- Tasks belong to the most recent `## heading`. If none has appeared, they are
  assigned to the synthetic project named `(no project)`.
- The H1 (`# heading`) is purely cosmetic and never starts a project.
- Project names are taken verbatim from the H2 line, with leading/trailing
  whitespace stripped. Markdown formatting in the heading (e.g. `**bold**`)
  is *kept as-is* in the name.

### 1.3 Nesting

- A task line's nesting level is determined by comparing its `INDENT` width
  (counted in *characters*, with a tab = 4 chars) to the indent of the
  most-recently-seen task in the document.
- Level 1 = strictly greater indent than the surrounding top-level tasks of
  the same project (which start at indent ≥ 0).
- Maximum supported nesting is 2 (top-level + subtask). A bullet whose indent
  would make it level 3 or deeper is **flattened to level 2** and a warning
  is emitted: `"deep nesting at line N flattened to subtask"`.
- The first task in a project defines the "top-level indent" for that
  project. Subsequent tasks at the same indent are siblings; strictly deeper
  indented checkbox bullets are subtasks of the previous same-or-shallower
  task.

### 1.4 Description continuation

A line is part of the description of the most-recent task when **all** of:

- It is not an H1 or H2 heading.
- It is not a checkbox bullet (no `[ ]` / `[x]` after the bullet marker).
- It appears before the next checkbox bullet at the same-or-lesser indent.
- It appears before the next `##` heading.

Blank lines inside a description are kept as blank lines in the description
text. Leading whitespace common to all continuation lines is stripped (so
descriptions don't carry the markdown indent into the UI).

### 1.5 Tag, hash, description split

Regex applied to the bullet body (everything after `[ ] `):

```
^(?:(?P<tag>[A-Za-z0-9_\-]+))?\((?P<hash>[0-9a-f]{5})\)\s*:\s*(?P<desc>.*)$
```

If the regex does not match, the bullet is treated as **unstamped**:

- A placeholder hash is assigned in-memory for the parse pass.
- The writer's `stamp_hashes` step replaces the placeholder with a real hash
  in the markdown.
- Tag is extracted with a fallback regex: `^([A-Za-z0-9_\-]+):\s*(.*)$`. If
  even that fails, tag is `None` and the full text is the description.

### 1.6 Done state

- `[ ]` → `done = False`.
- `[x]` or `[X]` → `done = True`.
- Anything else inside the brackets → parse warning, treated as `done =
  False`.

### 1.7 Edge cases — required behaviour

| Input | Output |
|---|---|
| Mixed tabs and spaces | Parsed; tab counted as 4 chars for indent comparison. |
| Trailing whitespace | Stripped. |
| CRLF line endings | Normalised to LF on read; preserved on write. |
| Empty file | Empty `ParsedDocument`, no warnings. |
| No H2, only tasks | Tasks go into `(no project)`. |
| Two H2s with identical names | Merged into one project (tasks concatenated). |
| Duplicate hash | First occurrence wins; rest dropped from yaml sync with warning. |
| Hash with uppercase hex | Warning + normalised to lowercase. |
| Sub-sub-task (3rd level) | Flattened to subtask of nearest level-1 ancestor, warning emitted. |
| Non-checkbox bullet at task indent | Treated as description of the most-recent task. |
| Task before any H2 | Goes into `(no project)`. |

## 2. tasks.yaml schema

```yaml
# v1 schema — keys are stable identifiers, values are scalar primitives.
tasks:
  - hash: a4f9c            # required, 5 hex chars
    start: 2026-06-01      # date or null
    end: 2026-06-10        # date or null
    created: 2026-05-27T14:32:11   # ISO-8601, no tz (local time)
    completed: null        # ISO-8601 or null
```

- File is YAML 1.2 safe-loadable.
- Top-level key is always `tasks` (list). Empty file = `tasks: []`.
- Entries are written sorted by `hash` for stable diffs.
- Dates are ISO 8601 (`YYYY-MM-DD`).
- Timestamps are ISO 8601 without timezone — local time on the machine.
  Rationale: this is a local-only tool, no cross-machine ambiguity.
- Unknown keys are preserved on round-trip (so future fields don't lose data
  on older clients).

## 3. config.yaml schema

```yaml
# v1
port: null                # int (1024-65535) or null for auto
```

- File is created on first init with `port: null`.
- Unknown keys are preserved on round-trip.

## 4. CLI — exit codes and messages

| Exit code | Meaning |
|---|---|
| 0 | Success. |
| 1 | User error (bad arguments, missing file, conflicting flags). |
| 2 | Click usage error (handled by Click). |
| 3 | Internal error (uncaught exception — also prints traceback to stderr). |

### 4.1 `todofile <path>`

- Errors if `<path>` doesn't exist or is not a regular file.
- Errors if `<path>` is not readable.
- Auto-inits the sidecar dir silently if missing.
- Output before serving:
  ```
  todofile: serving /abs/path/to/TODO.md
  todofile: open http://127.0.0.1:8421
  ```
- Opens the URL in the default browser unless `--no-browser` is passed (or
  `BROWSER=none` is set in environment).
- Ctrl-C exits with code 0 and prints `todofile: stopped`.

### 4.2 `todofile init <path>`

- Same path validation as above.
- Creates the sidecar dir if missing.
- Stamps hashes into every unstamped task in `<path>`.
- Output:
  ```
  todofile: initialized .TODO.md.dir
  todofile: stamped N new task(s)
  ```
  Where `N` may be 0.
- Idempotent — running twice is a no-op aside from the message.

### 4.3 `todofile task add`

Required flags: `--description`. At least one of: `--project` (if multiple
projects exist and no `--parent`), or `--parent`.

Errors:

| Condition | Message |
|---|---|
| Missing `--description` | `Missing option '--description' / '-d'.` |
| `--parent <hash>` not found | `No task with hash '<hash>' in /path/to/TODO.md.` |
| `--parent` is a subtask | `Cannot nest under '<hash>': only one level of subtasks is supported.` |
| `--project` doesn't exist | `No project named '<name>'. Available: foo, bar.` |
| Multiple projects, no `--parent`, no `--project` | `Must pass --project when the file has more than one project.` |
| `--start`, `--end`, `--duration` count > 2 distinct | `Pass at most two of --start-date, --end-date, --duration.` |
| Only `--duration` given | `--duration needs --start-date or --end-date as an anchor.` |
| Date parse failure | `Invalid date '<input>': expected YYYY-MM-DD.` |
| `--duration` negative or zero | `--duration must be a positive integer.` |
| `--end-date` before `--start-date` | `--end-date is before --start-date.` |

On success: prints the assigned hash, e.g. `todofile: added (a4f9c).`

### 4.4 `todofile task remove <hash>`

- Errors if the hash is not in the markdown.
- Errors if the hash is malformed (not 5 hex chars).
- If the hash is a parent with subtasks, removes the parent and all subtasks
  (their lines are contiguously indented under the parent in the md).
- Output: `todofile: removed (a4f9c) and N subtask(s).`

### 4.5 `todofile help format`

- Always exits 0.
- Prints the rendered format spec to stdout using rich. Content is a
  prose-formatted version of §1 of this document. Sections rendered as
  rich panels with code blocks for examples.

## 5. HTTP API

All responses are JSON. All requests with bodies use `Content-Type:
application/json`.

### 5.1 `GET /`

Returns `static/index.html` as `text/html; charset=utf-8`.

### 5.2 `GET /api/tasks`

Response 200:

```json
{
  "todo_path": "/abs/path/to/TODO.md",
  "projects": [
    {
      "name": "backend",
      "tasks": [
        {
          "hash": "a4f9c",
          "tag": "api",
          "description": "Build the parser",
          "done": false,
          "parent_hash": null,
          "start": "2026-06-01",
          "end": "2026-06-10",
          "created": "2026-05-27T14:32:11",
          "completed": null,
          "subtasks": [
            {"hash": "b3d8a", ...}
          ]
        }
      ]
    }
  ],
  "warnings": ["deep nesting at line 42 flattened to subtask"]
}
```

- Subtasks are nested inside their parent's `subtasks` array.
- `start`, `end`, `completed` are ISO date/datetime strings or `null`.
- `created` is always present (it's stamped on first sync).

### 5.3 `POST /api/tasks/{hash}/dates`

Request body:

```json
{"start": "2026-06-01", "end": "2026-06-10"}
```

Either or both keys may be `null`. Keys missing from the body are treated as
"leave unchanged".

Response 200:

```json
{"hash": "a4f9c", "start": "2026-06-01", "end": "2026-06-10"}
```

Errors:

| Status | Body | Condition |
|---|---|---|
| 400 | `{"error": "Invalid date 'foo': expected YYYY-MM-DD."}` | Date parse failure. |
| 400 | `{"error": "end is before start."}` | Inverted range. |
| 404 | `{"error": "No task with hash 'xxxxx'."}` | Hash not in current md. |

### 5.4 `POST /api/refresh`

No body. Re-runs parse → stamp (if needed) → sync, then returns the same
shape as `GET /api/tasks`.

Errors:

| Status | Body | Condition |
|---|---|---|
| 500 | `{"error": "TODO.md not readable: <details>"}` | I/O failure. |

### 5.5 Static

`GET /static/<file>` serves files from the installed package's `static/`
directory. 404 on missing.

## 6. UI behaviour

### 6.1 Project filter

- Multi-select chips in the header, one per project.
- All chips active by default.
- Clicking a chip toggles its inclusion. The list and the visualisation only
  show tasks from active projects.
- Subtasks follow their parent — a subtask is shown iff its project is
  active.

### 6.2 View toggle

- Two buttons: `Gantt` and `Calendar`. Default = `Gantt`.
- Selection persists in `localStorage` keyed by the absolute TODO path.

### 6.3 Show completed

- Toggle in the header. Default = on (completed tasks visible).
- When off, `[x]` tasks are hidden from both the list and the visualisation.
- A subtask's visibility is independent of its parent's done state.
- Selection persists in `localStorage`.

### 6.4 Refresh button

- POSTs `/api/refresh`, replaces the in-memory state, re-renders.
- Disabled and shows a spinner while in flight.
- On error, shows a red toast for ~4s with the server's error message.

### 6.5 Inline date editing

- Each task row in the left pane has two `<input type="date">` controls.
- On `change`, POST to `/api/tasks/{hash}/dates` with both values.
- Optimistic: update the local state immediately, render. On error, revert
  and toast.

### 6.6 Gantt rendering

- X axis: days. Range = `min(start) - 2d` to `max(end) + 2d` across visible
  tasks. If no tasks have dates, the X axis defaults to a 14-day window
  starting today.
- Y axis: one row per visible task, ordered by `start` ascending, undated at
  the bottom. Subtasks immediately follow their parent.
- A task with no `start` or no `end` is drawn as a thin marker on the date
  it does have, or hidden if it has neither.
- Today is marked with a vertical line.
- Tag is shown to the left of the bar; hovering shows description.

### 6.7 Calendar rendering

- Month grid view. The displayed month defaults to the month containing the
  earliest `start` among visible tasks, falling back to the current month.
- Prev/Next month buttons.
- Tasks render as colored pills on each day they span.
- Multi-week tasks wrap as separate pills on each week.
- Click on a pill scrolls the left pane to that task.

## 7. Sidecar directory lifecycle

For a TODO file at `/dir/myTODO.md`:

- Sidecar: `/dir/.myTODO.md.dir/`
- Contents on first init:
  ```
  /dir/.myTODO.md.dir/tasks.yaml         (contents: "tasks: []\n")
  /dir/.myTODO.md.dir/config.yaml        (contents: "port: null\n")
  ```
- The dir name is computed as `f".{todo_path.name}.dir"`.
- The dir is never deleted by the manager.

## 8. Hash stamping behaviour

When the parser encounters an unstamped task at line `N`:

1. The CLI/server collects all unstamped tasks into a list.
2. `writer.stamp_hashes(text, existing_hashes)` walks the file once:
   - For each unstamped bullet, generate a new hash not in `existing_hashes`.
   - Add the hash to `existing_hashes` before generating the next one.
   - Rewrite the bullet body:
     - With existing tag `foo:`: `- [ ] foo(a4f9c): description`
     - Without tag: `- [ ] (a4f9c): description`
3. The file is rewritten atomically (temp + replace).
4. The parser is run again on the new file before any other step uses the
   parsed data.

## 9. Sync semantics

Given a parsed `ParsedDocument` and an existing `tasks.yaml`:

For each task in the parsed doc:

- If its hash is not in yaml → add a new yaml row with `created = now`,
  `start = end = completed = null`.
- If its hash is in yaml and the task is done in md but `completed` is null
  → set `completed = now`.
- If its hash is in yaml and the task is not done in md but `completed` is
  set → clear `completed` to null. (User un-checking `[x]` un-completes.)

For each hash in yaml not in the parsed doc:

- Drop the row (no archive in v1).

Sync writes only if changes occurred.

## 10. Performance budget

Not a hot path. Target: parse + sync of a 1 MB `TODO.md` in under 100 ms on
a modern laptop. No optimisation work is required to meet this.
