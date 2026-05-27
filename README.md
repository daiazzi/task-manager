# task-manager

Local-first task manager for dev/data projects. Your `TODO.md` stays the
single human-edited, gittable source of truth; the manager adds dates and a
Gantt/Calendar view backed by a sidecar YAML file.

```
$ task-manager path/to/TODO.md
task-manager: serving /abs/path/to/TODO.md
task-manager: open http://127.0.0.1:42117
```

The web UI opens in your default browser (or paste the URL into the VS Code
Simple Browser). Ctrl-C stops the server.

## What it does

- Parses your `TODO.md` and shows tasks in a list + a Gantt timeline +
  a month calendar.
- Lets you click-and-set start/end dates inline. Dates persist to
  `./<dir-of-todo>/.<filename>.dir/tasks.yaml` — your `TODO.md` is **not**
  rewritten for dates.
- Stamps a stable 5-char hash into each task on first sight, so dates
  survive edits to the task text.
- Filters by project (multi-select chips).
- Toggles between Gantt and Calendar views.

The markdown is the source of truth for: which tasks exist, hierarchy,
project, tag, description, done state. The yaml owns dates and timestamps.

## TODO.md format

```markdown
# Project title              <-- ignored

## backend                   <-- starts a project

- [ ] api(a4f9c): Build the parser
  Continued description on indented lines.
  - A bullet inside the description (no checkbox).
  - [ ] (b3d8a): A subtask
- [x] (c1d2e): Completed

## frontend
- [ ] ui: Design the layout      <-- unstamped; gets a hash on next run
```

- H2 (`##`) headings are projects. Tasks belong to the most recent one.
- A task is `- [ ]` (or `- [x]`, `*`, mixed) followed by an optional `tag`,
  `(hash)`, `:`, then the description.
- The hash is mandatory in the canonical form; unstamped tasks are accepted
  and stamped on the next `task-manager` or `task-manager init` run.
- Tag is an optional free-form category.
- Subtasks are indented deeper than their parent. Max 2 levels.
- Continuation lines (non-checkbox content under a task) become part of its
  description.

Full grammar: `task-manager help format`.

## Install

```bash
# clone, then in the repo:
pixi install
pixi run task-manager --help
```

The CLI is exposed as `task-manager` inside the pixi environment.

## CLI

| Command | What it does |
|---|---|
| `task-manager <path>` | Auto-init, start the web UI, open the browser. |
| `task-manager init <path>` | Create the sidecar dir and stamp hashes. Does not start the server. |
| `task-manager task add <path> -d "<desc>" [-t tag] [-p parent_hash] [-P project] [-s YYYY-MM-DD] [-e YYYY-MM-DD] [--duration N]` | Add a task to the markdown. |
| `task-manager task remove <path> <hash>` | Remove a task (and its subtasks). |
| `task-manager help format` | Print the TODO.md format spec. |

Date flags for `task add`: pass at most two of `--start-date`, `--end-date`,
`--duration` (days, inclusive). The third is derived.

## Sidecar files

For `/path/to/myTODO.md` the manager uses:

```
/path/to/.myTODO.md.dir/
    tasks.yaml      # dates + timestamps, one row per hash
    config.yaml     # { port: null }    -- override the auto-picked port
```

Add `*/.*.dir/` to your `.gitignore` if you don't want to commit the
metadata, or commit it if you do — both are valid workflows.

## Development

This project uses [pixi](https://pixi.sh) for environment and dependency
management. Do not call `pip` or `conda` directly.

```bash
# add a runtime dependency from PyPI
pixi add --pypi <pkg>

# add a dev-only dependency
pixi add --feature dev <pkg>

# run tests
pixi run pytest

# run the CLI in development
pixi run task-manager <path/to/TODO.md>

# enter the env interactively
pixi shell
```

The package layout:

```
src/task_manager/
    models.py          # dataclasses
    parser.py          # TODO.md → ParsedDocument
    writer.py          # mutate TODO.md (stamp, add, remove)
    store.py           # tasks.yaml + config.yaml
    cli.py             # rich-click commands
    server.py          # Starlette app
    static/            # HTML + CSS + JS
tests/                 # pytest suite
docs/                  # requirements, technical design, specifications, tasks
```

Read [docs/requirements.md](docs/requirements.md) before contributing.

## Status

v1 — single TODO file per server invocation, no archive, no live file
watching. See [docs/requirements.md §11](docs/requirements.md) for deferred
nice-to-haves.
