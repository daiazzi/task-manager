# todofile — Technical Design

This document is the *how* to the requirements' *what*. It locks down the
library choices, module boundaries, data flow, and the contracts between the
CLI, the parser/writer, the store, and the web UI.

> Read [requirements.md](requirements.md) first.

## 1. Library choices

| Concern | Library | Why |
|---|---|---|
| CLI framework | `rich-click` | Already pinned in `pyproject.toml`. Click's command-group model fits `add` / `remove` / `help format` cleanly, rich-click renders the `--help` nicely. |
| Web framework | `starlette` | We need ~4 endpoints + static files. Starlette is the minimal ASGI framework. FastAPI's Pydantic validation is overkill at this scale; we'll do our own validation in ~10 lines. |
| ASGI server | `uvicorn` | Already pinned (currently in dev — will be promoted to main). |
| YAML | `PyYAML` | Ubiquitous, sufficient. `tasks.yaml` is machine-managed so comment preservation is not needed. |
| Tests | `pytest` | Already in dev deps. |

No frontend framework. The UI is one HTML page + one CSS + one JS file, served
as static assets from the installed package. No build step. The implementation
target is modern evergreen browsers and the VS Code Simple Browser (Chromium
recent enough to support standard ES2022).

## 2. Package layout

```
src/todofile/
    __init__.py        # version, public re-exports
    models.py          # dataclasses: Task, Project, ParsedDocument
    parser.py          # markdown → ParsedDocument
    writer.py          # mutate TODO.md (stamp hash, add bullet, remove bullet)
    store.py           # sidecar paths, tasks.yaml load/save, config.yaml, sync
    server.py          # Starlette app + endpoints
    cli.py             # rich-click entry points
    static/
        index.html
        app.css
        app.js
tests/
    conftest.py
    fixtures/
    test_parser.py
    test_writer.py
    test_store.py
    test_cli.py
```

## 3. Data model

Defined in `models.py` as `@dataclass(slots=True)` types. Plain dataclasses, no
ORM, no validators — these are in-memory shapes only.

```python
@dataclass(slots=True)
class Task:
    hash: str                  # 5-char lowercase hex
    tag: str | None            # category, optional
    description: str           # first line + continuation, stripped
    done: bool                 # [x] vs [ ]
    project: str               # parent H2; "(no project)" if none
    parent_hash: str | None    # None for top-level
    # metadata from tasks.yaml — None until merged
    start: date | None = None
    end: date | None = None
    created: datetime | None = None
    completed: datetime | None = None

@dataclass(slots=True)
class Project:
    name: str
    tasks: list[Task]          # top-level only; subtasks live under their parent

@dataclass(slots=True)
class ParsedDocument:
    path: Path
    projects: list[Project]
    # hash → task index, kept after parsing for O(1) lookup
    tasks_by_hash: dict[str, Task]
    # warnings the parser emitted (deeper-than-2 nesting, duplicate hashes, ...)
    warnings: list[str]
```

Subtasks are NOT exposed as a separate field on `Project`. They live as
`Task`s with `parent_hash` set, owned by their parent in a sibling list. The
parser builds parent→children adjacency separately and exposes it via
`ParsedDocument.children_of(hash) -> list[Task]`.

## 4. Module responsibilities

### 4.1 `parser.py`

Pure function:

```python
def parse(path: Path) -> ParsedDocument
def parse_text(text: str, path: Path | None = None) -> ParsedDocument
```

Algorithm — single pass over lines:

1. Track current project (most recent `## heading`).
2. For each line, classify:
   - `#` → ignore.
   - `##` → new project.
   - checkbox bullet (regex: `^(\s*)[-*]\s+\[([ xX])\]\s+(.*)$`) → new task.
   - Anything else under the most recent task → append to that task's
     description buffer.
3. For checkbox bullets, compute nesting level by comparing leading whitespace
   to the *parent task's* indent. We don't require a specific number of
   spaces — any strictly-greater indent is "deeper."
4. If a checkbox bullet's indent is more than one level deeper than the
   current parent (e.g., a sub-sub-task), flatten to a subtask of the nearest
   top-level task in that branch and emit a warning.
5. Extract `(tag(hash):)` from the bullet content with regex
   `^(?:([A-Za-z0-9_\-]+))?\(([0-9a-f]{5})\)\s*:\s*(.*)$`. If the parens are
   missing, the task is unstamped and gets a placeholder; the writer will
   assign a hash on the next stamping pass.
6. Strip trailing whitespace, normalise CRLF to LF on read.
7. Collect duplicate hashes — keep first, warn on rest.

Output: `ParsedDocument`. The parser does not touch the filesystem beyond
reading the path.

### 4.2 `writer.py`

Three functions, each operating on the markdown as a string and returning the
new string (the CLI/server wraps with file I/O):

```python
def stamp_hashes(text: str, existing_hashes: set[str]) -> tuple[str, dict[int, str]]
    # Returns the new text and a mapping {line_index: new_hash} for the audit log.

def insert_task(text: str, *, project: str, parent_hash: str | None,
                tag: str | None, description: str, hash: str) -> str

def remove_task(text: str, hash: str) -> str
    # Removes the bullet line. If the hash is a parent, also removes all
    # contiguous lines with deeper indent until the next same-or-lesser-indent
    # line, an H2, or EOF.
```

Insertion rules:

- Top-level task (no parent): find the line index of the project's `##`
  heading, scan forward to the end of that section, append after the last
  non-blank line.
- Subtask: find the parent's bullet line, scan forward over its description
  and subtasks (anything more-indented than the parent), insert after the last
  line that belongs to the parent.
- Indent: subtasks indented with 2 spaces beyond the parent's indent.

The writer preserves the file's existing line endings and trailing newline
state.

### 4.3 `store.py`

```python
def sidecar_dir(todo_path: Path) -> Path
    # /a/b/myTODO.md → /a/b/.myTODO.md.dir

def ensure_sidecar(todo_path: Path) -> Path
    # Creates the dir and default files if missing. Idempotent.

def load_tasks_yaml(todo_path: Path) -> dict[str, TaskMetadata]
    # hash → metadata dict with start/end/created/completed.

def save_tasks_yaml(todo_path: Path, data: dict[str, TaskMetadata]) -> None

def load_config(todo_path: Path) -> Config

def sync(doc: ParsedDocument, todo_path: Path) -> ParsedDocument
    # Merge yaml metadata into the parsed Tasks. Add yaml entries for any
    # task in the md without one (created=now, dates=None). Drop yaml
    # entries for hashes no longer in the md (no archive in v1).
    # Stamps completed=now for tasks newly marked [x].
```

`TaskMetadata` is a small dataclass mirroring the yaml row. We don't use
`Task` here because `Task` carries fields owned by the markdown, and mixing
the two would invite drift.

### 4.4 `cli.py`

A `rich-click` `Group` named `cli`. Subcommands:

- `cli(path)` — default invocation. Aliased so `todofile <path>` works.
- `cli init(path)`.
- `cli add(path, ...)`.
- `cli remove(path, hash)`.
- `cli help format()` — under a `help` group.

Click's `invoke_without_command` + a default callback lets the top-level take
a positional path while still hosting subcommands. We wire that up explicitly.

Each subcommand:

1. Resolves the path (errors clearly if it doesn't exist or isn't a file).
2. Calls `store.ensure_sidecar()`.
3. Calls `parser.parse()`, then `writer.stamp_hashes()` if any unstamped
   tasks were found, then re-parses.
4. Calls `store.sync()` to align yaml with the md.
5. Performs the command-specific action.

For `add`, the date logic resolves the `{start, end, duration}` triple
before writing yaml.

### 4.5 `server.py`

A `starlette.applications.Starlette` instance built by a factory:

```python
def build_app(todo_path: Path) -> Starlette
```

Routes:

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Serve `static/index.html`. |
| GET | `/api/tasks` | Returns the current `ParsedDocument` merged with yaml as JSON. |
| POST | `/api/tasks/{hash}/dates` | Body `{start: str\|null, end: str\|null}`. Updates yaml only. Returns the new row. |
| POST | `/api/refresh` | Re-reads md, re-syncs yaml, returns same shape as `/api/tasks`. |
| (static mount) | `/static/*` | `app.css`, `app.js`, etc. |

The path of the TODO file is captured in the app factory's closure — there is
no per-request path argument.

Response shape for `/api/tasks` and `/api/refresh`:

```json
{
  "projects": [
    {"name": "backend",
     "tasks": [
       {"hash": "a4f9c", "tag": "api", "description": "...",
        "done": false, "parent_hash": null,
        "start": "2026-06-01", "end": "2026-06-10",
        "subtasks": [ /* same shape */ ]}
     ]}
  ],
  "warnings": ["..."]
}
```

Subtasks are nested under their parent in the response — convenient for the
frontend. Tag, description, done come from the parser; dates from the store.

### 4.6 Frontend (`static/`)

Single page. On load:

1. `fetch('/api/tasks')` → render.
2. `Refresh` button → `POST /api/refresh` → re-render.
3. View toggle, show-completed toggle, project chips are all client-side
   filters over the same in-memory data.
4. Date inputs (HTML `<input type="date">`) on each task row. On `change`,
   POST to `/api/tasks/{hash}/dates`. Optimistic UI update; revert on error.

**Gantt** is rendered as inline SVG. X axis = days spanning min-start to
max-end across all visible tasks (with a few days of padding). Y axis = one
row per task. Each task is a rounded rect.

**Calendar** is a CSS grid: 7 columns (Sun–Sat), one row per week, sized to
the visible date range. Tasks render as colored pills that span their days.
Multi-week tasks wrap across rows.

Done tasks render with reduced opacity and a strikethrough. The done-toggle
controls whether they appear in the list and the views.

The page is plain ES modules — `<script type="module" src="/static/app.js">`.
No bundler, no transpile.

## 5. Data flow — start to finish

```
$ todofile /a/b/TODO.md
       │
       ▼
 cli.cli(path) ──► store.ensure_sidecar()
                     creates /a/b/.TODO.md.dir/{tasks.yaml,config.yaml}
                     if missing
       │
       ▼
 parser.parse(path) ──► ParsedDocument(warnings=[...])
       │
       ▼
 if any unstamped:
     writer.stamp_hashes() → write back to TODO.md
     parser.parse(path) again
       │
       ▼
 store.sync(doc, path)
     • adds new yaml rows (created=now)
     • drops missing-from-md rows
     • stamps completed=now for newly-[x] rows
       │
       ▼
 server.build_app(path) → uvicorn.Server(loop="asyncio").serve()
     prints "Open http://127.0.0.1:<port>"
     opens browser via webbrowser.open() unless --no-browser
     blocks until Ctrl-C
```

On every `POST /api/refresh` the parser→stamp→sync chain is re-run.

## 6. Concurrency and atomicity

The server is single-process, single-threaded ASGI. We use the asyncio loop
but the parser/writer/store are all blocking; we wrap calls in
`asyncio.to_thread()`.

File writes are atomic: write to a temporary file next to the target, then
`os.replace()`. This protects against partial writes if the process is killed
during a save.

No file watching, so the manager assumes it's the only writer to `tasks.yaml`
while the server is up. Concurrent edits to `TODO.md` are tolerated — they
are only seen on the next `/api/refresh`.

## 7. Hash generation

```python
import secrets

def new_hash(existing: set[str]) -> str:
    while True:
        candidate = secrets.token_hex(3)[:5]   # 5 hex chars
        if candidate not in existing:
            return candidate
```

5 hex chars → ~1M unique hashes per file. At 100 tasks per file, the
collision probability per generation is ~10⁻⁴; we still check.

## 8. Error handling

Errors are surfaced via:

- **CLI** — `click.ClickException` subclasses, exit code 1, single-line
  message printed in red via rich-click's renderer.
- **Server** — JSON `{"error": "..."}` with appropriate 4xx status. The
  frontend shows a transient toast; no modal dialogs.
- **Parser warnings** — non-fatal, carried in `ParsedDocument.warnings`,
  surfaced in the CLI as yellow lines and in the UI as a small badge near
  the refresh button.

Specific error cases are enumerated in `specifications.md`.

## 9. Testing strategy

| Layer | Approach |
|---|---|
| Parser | Table-driven: a directory of `.md` fixtures paired with expected `ParsedDocument` JSON. Covers all edge cases in requirements §5.3. |
| Writer | Round-trip: parse, write, re-parse, assert structural equality. Plus targeted "insert at exact location" tests. |
| Store | tmp_path-based: build a parsed doc, save, load, assert equality. Sync semantics covered with crafted before/after states. |
| CLI | Click's `CliRunner` against a tmp_path workspace. |
| Server | Starlette `TestClient` against an in-process app. |
| Frontend | None automated in v1 — manual verification. |

## 10. Out of scope (reaffirmed)

- WebSockets, server-sent events, live reload.
- Authentication, CSRF tokens — server binds to 127.0.0.1 only.
- Database — yaml is the persistent store.
- Packaging beyond the editable install via pixi.
