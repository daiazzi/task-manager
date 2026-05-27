# tsk

Local-first task manager for dev/data projects. Your `TODO.md` stays the
single human-edited, gittable source of truth; the manager adds dates and a
Gantt/Calendar view backed by a sidecar YAML file.

```
$ tsk path/to/TODO.md
tsk: serving /abs/path/to/TODO.md
tsk: open http://127.0.0.1:42117
```

The web UI opens in your default browser (or paste the URL into the VS Code
Simple Browser). Ctrl-C stops the server. Run it detached with `tsk up
<path>` / `tsk down <path>`.

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
- Light/dark theme toggle.
- Per-tag colours from `config.yaml`.

The markdown is the source of truth for: which tasks exist, hierarchy,
project, tag, description, done state. The yaml owns dates and timestamps.

## TODO.md format

```markdown
# Project title              <-- shown in the UI header

## backend                   <-- starts a project

- [ ] api(a4f9c): Build the parser
  Continued description on indented lines.
  - A bullet inside the description (no checkbox).
  - [ ] (b3d8a): A subtask
- [x] (c1d2e): Completed

## frontend
- [ ] ui: Design the layout      <-- unstamped; gets a hash on next run
```

- H1 (`#`) is the document title — shown in the UI header.
- H2 (`##`) headings are projects. Tasks belong to the most recent one.
- A task is `- [ ]` (or `- [x]`, `*`, mixed) followed by an optional `tag`,
  `(hash)`, `:`, then the description.
- The hash is mandatory in the canonical form; unstamped tasks are accepted
  and stamped on the next `tsk` or `tsk init` run.
- Tag is an optional free-form category.
- Subtasks are indented deeper than their parent. Max 2 levels.
- Continuation lines (non-checkbox content under a task) become part of its
  description.

Full grammar: `tsk help format`.

## Install

```bash
# clone, then in the repo:
pixi install
pixi run tsk --help
```

The CLI is exposed as `tsk` inside the pixi environment.

## CLI

`<path>` is optional on every command. When omitted, `tsk` looks in the
current directory for an initialized `.<name>.dir/` sidecar; if exactly one
exists it is used. Otherwise it falls back to `./TODO.md`, then errors.

| Command | What it does |
|---|---|
| `tsk [path]` | Auto-init, start the web UI in foreground, open the browser. Ctrl-C to stop. |
| `tsk up [path]` | Start the server detached (background). Writes pid/url into the sidecar. |
| `tsk down [path]` | Stop the daemon for that TODO. |
| `tsk init [path]` | Create the sidecar dir, copy `agent.md`, stamp hashes. Creates the file if missing (parent dir must exist). Defaults to `./TODO.md`. |
| `tsk task add [path] -d "<desc>" [-t tag] [-p parent_hash] [-P project] [-s YYYY-MM-DD] [-e YYYY-MM-DD] [--duration N]` | Add a task to the markdown. |
| `tsk task remove <hash> [path]` | Remove a task (and its subtasks). |
| `tsk config mode <dark\|light> [path]` | Set the UI theme in `config.yaml`. |
| `tsk config tag --color <COLOR> <tag> [path]` | Set a tag's colour. `<COLOR>` is a palette name or hex. |
| `tsk config tag colors` | Print the available colour palette with swatches. |
| `tsk help format` | Print the TODO.md format spec. |

Date flags for `task add`: pass at most two of `--start-date`, `--end-date`,
`--duration` (days, inclusive). The third is derived.

Editing `config.yaml` through `tsk config` rewrites the file via YAML
serialisation, which drops any comments. Edit the file by hand to keep
them.

## Sidecar files

For `/path/to/myTODO.md` the manager uses:

```
/path/to/.myTODO.md.dir/
    tasks.yaml      # dates + timestamps, one row per hash
    config.yaml     # port, theme, tag colours
    agent.md        # instructions for coding assistants editing TODO.md
    daemon.pid      # only while detached (written by `tsk up`)
    daemon.url
    daemon.log
```

`config.yaml` shape:

```yaml
port: null               # int (1024-65535) or null for auto
theme: dark              # "dark" or "light"
colors:
  default: "#7aa2f7"
  api: "#9ece6a"
  db:  "#f7768e"
```

Add `*/.*.dir/` to your `.gitignore` if you don't want to commit the
metadata, or commit it if you do — both are valid workflows.

## Agents

`tsk init` drops a `agent.md` into the sidecar. Point your coding assistant
at it (the file documents the TODO.md format, what edits are safe, and
recommends `tsk task add/remove` for non-trivial changes).

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
pixi run tsk <path/to/TODO.md>

# enter the env interactively
pixi shell
```

The package layout:

```
src/task_manager/
    models.py          # dataclasses
    parser.py          # TODO.md → ParsedDocument
    writer.py          # mutate TODO.md (stamp, add, remove)
    store.py           # tasks.yaml + config.yaml + agent.md
    daemon.py          # detached server lifecycle (tsk up/down)
    cli.py             # rich-click commands
    server.py          # Starlette app
    static/            # HTML + CSS + JS + agent.md template
tests/                 # pytest suite
docs/                  # requirements, technical design, specifications, tasks
```

Read [docs/requirements.md](docs/requirements.md) before contributing.

## Status

v1 — single TODO file per server invocation, no archive, no live file
watching. See [docs/requirements.md §11](docs/requirements.md) for deferred
nice-to-haves.
