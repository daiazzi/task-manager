# todofile — Build Plan

The order below is dependency-respecting. Earlier milestones unblock later
ones. Each milestone has a brief acceptance check.

## M1 — Project plumbing

1. Promote `uvicorn` from the `dev` pixi feature to main `dependencies`.
2. Add `starlette` and `pyyaml` to main `dependencies`.
3. Register the CLI entry point: `[project.scripts] todofile = "todofile.cli:main"`.
4. Add a `todofile` pixi task for convenience.

**Accept**: `pixi install -e dev`, `pixi run todofile --help` prints help.

## M2 — Models

1. `models.py` with `Task`, `Project`, `ParsedDocument` dataclasses.
2. `ParsedDocument.children_of(hash)` helper.

**Accept**: `pixi run python -c "from todofile.models import Task"`.

## M3 — Parser

1. `parser.parse_text(text, path=None) -> ParsedDocument`.
2. `parser.parse(path) -> ParsedDocument` thin wrapper.
3. Handle all edge cases listed in [specifications.md §1.7](specifications.md).

**Accept**: parser tests pass on fixtures covering all §1.7 rows.

## M4 — Writer

1. `writer.stamp_hashes(text, existing_hashes) -> (new_text, stamped_map)`.
2. `writer.insert_task(text, ...) -> new_text`.
3. `writer.remove_task(text, hash) -> new_text`.

**Accept**: writer round-trip tests pass (parse → write → re-parse equality).

## M5 — Store

1. `store.sidecar_dir(path)`, `store.ensure_sidecar(path)`.
2. `store.load_tasks_yaml`, `store.save_tasks_yaml` with atomic write.
3. `store.load_config`.
4. `store.sync(doc, path)` implementing the rules in [specifications.md §9](specifications.md).

**Accept**: store tests pass — sync adds new hashes, drops missing, sets/
clears `completed`.

## M6 — CLI

1. `cli.py` with `rich-click` groups.
2. Top-level callback: `todofile <path>` starts server.
3. `init` subcommand.
4. `task add` / `task remove` subcommands with all flags from
   [specifications.md §4.3](specifications.md).
5. `help format` subcommand.

**Accept**: `CliRunner` tests for each subcommand pass.

## M7 — Web server

1. `server.build_app(todo_path)` factory.
2. Routes per [specifications.md §5](specifications.md).
3. Async-wrap blocking parser/writer/store calls with `asyncio.to_thread`.
4. `webbrowser.open()` on launch unless `--no-browser`.

**Accept**: Starlette `TestClient` integration tests pass.

## M8 — Frontend

1. `static/index.html` skeleton.
2. `static/app.css` — minimal styling, dark mode friendly.
3. `static/app.js` — fetch state, render list, render Gantt (SVG),
   render Calendar (CSS grid), toggles, filters, date editing, refresh.

**Accept**: manual: open browser on a sample TODO.md, see list + Gantt;
toggle to Calendar; edit a date; click refresh.

## M9 — Tests

Tests are written incrementally alongside each module, but this milestone is
the final coverage pass: ensure every error path in specifications.md is
exercised at least once.

**Accept**: `pixi run pytest` is green, coverage ≥ 80% over `parser`,
`writer`, `store`, `cli`, `server`.

## M10 — README + verification

1. README.md: install, usage, dev workflow (pixi).
2. End-to-end manual verification on a sample TODO.md.

**Accept**: instructions in README reproduce a working install and a
running server.

## Deferred (post-v1)

- Archive of deleted tasks.
- File watcher for auto-refresh.
- Sub-sub-tasks.
- Multiple TODO files in one server.
- Drag-to-reschedule on the Gantt view.
