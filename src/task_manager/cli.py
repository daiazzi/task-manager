from __future__ import annotations

import re
import sys
import webbrowser
from datetime import date, timedelta
from pathlib import Path

import rich_click as click
from rich.console import Console
from rich.panel import Panel

from . import daemon as daemon_mod
from . import parser as parser_mod
from . import writer as writer_mod
from . import store

_console = Console()
_HASH_RE = re.compile(r"^[0-9a-f]{5}$")


def _load_doc(path: Path):
    """Parse, stamp hashes if needed, sync yaml. Returns the final ParsedDocument."""
    store.ensure_sidecar(path)
    text = path.read_text(encoding="utf-8")
    existing = parser_mod.existing_hashes(text)
    doc = parser_mod.parse_text(text, path=path)

    unstamped = [h for h in doc.tasks_by_hash if h.startswith("__new")]
    if unstamped:
        new_text, _ = writer_mod.stamp_hashes(text, existing)
        path.write_text(new_text, encoding="utf-8")
        doc = parser_mod.parse(path)

    store.sync(doc, path)

    for w in doc.warnings:
        _console.print(f"[yellow]warning:[/yellow] {w}")
    return doc


@click.group(invoke_without_command=False)
@click.version_option(package_name="task-manager", prog_name="tsk")
def cli() -> None:
    """Local task manager backed by a TODO.md.

    Default invocation: `tsk <path/to/TODO.md>` starts the web UI.
    """


@cli.command(hidden=True)
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--no-browser", is_flag=True, help="Do not open the browser on launch.")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=None, help="Override the port from config.yaml.")
def serve(path: Path, no_browser: bool, host: str, port: int | None) -> None:
    """Start the web server for the given TODO.md."""
    from .server import run

    _load_doc(path)
    cfg = store.load_config(path)
    final_port = port if port is not None else cfg.port
    run(path, host=host, port=final_port, open_browser=not no_browser)


@cli.command()
@click.argument("path", type=click.Path(dir_okay=False, path_type=Path))
def init(path: Path) -> None:
    """Create the sidecar directory and stamp hashes into the markdown.

    If the TODO file does not exist, it is created with a default scaffold.
    The parent directory must exist.
    """
    path = path.expanduser().resolve()
    parent = path.parent
    if not parent.is_dir():
        raise click.ClickException(f"Parent directory does not exist: {parent}")

    created = False
    if not path.exists():
        title = path.stem
        path.write_text(f"# {title}\n\n## Tasks\n", encoding="utf-8")
        created = True

    store.ensure_sidecar(path)
    text = path.read_text(encoding="utf-8")
    existing = parser_mod.existing_hashes(text)
    new_text, stamped = writer_mod.stamp_hashes(text, existing)
    if stamped:
        path.write_text(new_text, encoding="utf-8")
    doc = parser_mod.parse(path)
    store.sync(doc, path)
    if created:
        _console.print(f"tsk: created {path}")
    _console.print(f"tsk: initialized {store.sidecar_dir(path).name}")
    _console.print(f"tsk: stamped {len(stamped)} new task(s)")
    for w in doc.warnings:
        _console.print(f"[yellow]warning:[/yellow] {w}")


@cli.command()
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=None, help="Override the port from config.yaml.")
def up(path: Path, host: str, port: int | None) -> None:
    """Start the server detached from the terminal (background)."""
    path = path.expanduser().resolve()
    _load_doc(path)
    try:
        pid, url = daemon_mod.start(path, host=host, port=port)
    except RuntimeError as e:
        raise click.ClickException(str(e))
    _console.print(f"tsk: started daemon (pid {pid})")
    _console.print(f"tsk: open {url}")


@cli.command()
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def down(path: Path) -> None:
    """Stop the daemon associated with the given TODO file."""
    path = path.expanduser().resolve()
    pid = daemon_mod.stop(path)
    if pid is None:
        _console.print("tsk: no daemon running")
    else:
        _console.print(f"tsk: stopped daemon (pid {pid})")


@cli.group()
def task() -> None:
    """Add or remove tasks."""


@task.command(name="add")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--description", "-d", required=True, help="Task description.")
@click.option("--tag", "-t", default=None, help="Optional category tag.")
@click.option("--parent", "-p", "parent_hash", default=None, help="Parent task hash for a subtask.")
@click.option("--project", "-P", default=None, help="Project to add under.")
@click.option("--start-date", "-s", "start", type=str, default=None, help="Start date YYYY-MM-DD.")
@click.option("--end-date", "-e", "end", type=str, default=None, help="End date YYYY-MM-DD.")
@click.option("--duration", type=int, default=None, help="Duration in days (positive).")
def task_add(
    path: Path,
    description: str,
    tag: str | None,
    parent_hash: str | None,
    project: str | None,
    start: str | None,
    end: str | None,
    duration: int | None,
) -> None:
    """Add a new task to the markdown."""
    doc = _load_doc(path)

    if parent_hash:
        if not _HASH_RE.match(parent_hash):
            raise click.ClickException(f"Invalid hash '{parent_hash}': expected 5 lowercase hex chars.")
        parent_task = doc.tasks_by_hash.get(parent_hash)
        if parent_task is None:
            raise click.ClickException(f"No task with hash '{parent_hash}' in {path}.")
        if parent_task.parent_hash is not None:
            raise click.ClickException(
                f"Cannot nest under '{parent_hash}': only one level of subtasks is supported."
            )
        resolved_project = parent_task.project
    else:
        existing_projects = [p.name for p in doc.projects]
        if project is None:
            if len(existing_projects) == 0:
                from .models import NO_PROJECT
                resolved_project = NO_PROJECT
            elif len(existing_projects) == 1:
                resolved_project = existing_projects[0]
            else:
                avail = ", ".join(existing_projects)
                raise click.ClickException(
                    f"Must pass --project when the file has more than one project. Available: {avail}."
                )
        else:
            if project not in existing_projects:
                avail = ", ".join(existing_projects) or "(none)"
                raise click.ClickException(f"No project named '{project}'. Available: {avail}.")
            resolved_project = project

    start_d, end_d = _resolve_dates(start, end, duration)

    new_h = writer_mod.new_hash(set(doc.tasks_by_hash.keys()))
    text = path.read_text(encoding="utf-8")
    new_text = writer_mod.insert_task(
        text,
        project=resolved_project,
        parent_hash=parent_hash,
        tag=tag,
        description=description,
        hash=new_h,
    )
    path.write_text(new_text, encoding="utf-8")

    if start_d is not None or end_d is not None:
        store.set_dates(path, new_h, start_d, end_d)

    doc2 = parser_mod.parse(path)
    store.sync(doc2, path)
    _console.print(f"tsk: added ({new_h}).")


@task.command(name="remove")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("hash")
def task_remove(path: Path, hash: str) -> None:
    """Remove the task with the given hash."""
    if not _HASH_RE.match(hash):
        raise click.ClickException(f"Invalid hash '{hash}': expected 5 lowercase hex chars.")

    doc = _load_doc(path)
    if hash not in doc.tasks_by_hash:
        raise click.ClickException(f"No task with hash '{hash}' in {path}.")

    subtasks = doc.children_of(hash)
    text = path.read_text(encoding="utf-8")
    try:
        new_text = writer_mod.remove_task(text, hash)
    except KeyError:
        raise click.ClickException(f"No task with hash '{hash}' in {path}.")
    path.write_text(new_text, encoding="utf-8")

    doc2 = parser_mod.parse(path)
    store.sync(doc2, path)
    _console.print(f"tsk: removed ({hash}) and {len(subtasks)} subtask(s).")


@cli.group(name="help")
def help_group() -> None:
    """Show documentation on specific topics."""


@help_group.command(name="format")
def help_format() -> None:
    """Print the TODO.md format spec."""
    _console.print(
        Panel.fit(
            _FORMAT_HELP_TEXT,
            title="TODO.md format",
            border_style="cyan",
        )
    )


_FORMAT_HELP_TEXT = """\
[bold]File structure[/bold]
  # Document title             (ignored)
  ## Project name              (starts a project)
  - [ ] tag(hash): task         (a task)
    continued description on indented lines
    - sub-bullet of description (no checkbox)
    - [ ] tag(hash): subtask   (a subtask)
  - [x] (hash): done task

[bold]Rules[/bold]
  • H1 is ignored.
  • H2 starts a project. Tasks belong to the most recent H2.
  • A [italic]task[/italic] is any indented bullet starting with [cyan]- [ ][/cyan] or [cyan]- [x][/cyan].
  • Indentation is lenient (tabs or spaces). Tabs count as 4 spaces.
  • [italic]Subtasks[/italic] are checkbox bullets indented deeper than their parent.
    Maximum nesting is 2 levels; deeper bullets are flattened with a warning.
  • [italic]Description[/italic] is the text after `:` plus subsequent non-checkbox lines
    up to the next checkbox bullet or H2.
  • [italic]Tag[/italic] is optional. Format: [cyan]tag(hash):[/cyan] or [cyan](hash):[/cyan] without tag.
  • [italic]Hash[/italic] is 5 lowercase hex chars. The manager stamps one into new
    tasks automatically.
  • [cyan][x][/cyan] / [cyan][X][/cyan] marks a task as done; [cyan][ ][/cyan] as not done.

[bold]Storage[/bold]
  Metadata (dates, timestamps) lives in [cyan].<filename>.dir/tasks.yaml[/cyan]
  next to the TODO file. The markdown is never written for dates — only for
  hash stamping and explicit `task add` / `task remove`.
"""


def _resolve_dates(
    start_s: str | None, end_s: str | None, duration: int | None
) -> tuple[date | None, date | None]:
    set_count = sum(x is not None for x in (start_s, end_s, duration))
    if set_count == 3:
        raise click.ClickException("Pass at most two of --start-date, --end-date, --duration.")
    if duration is not None and duration <= 0:
        raise click.ClickException("--duration must be a positive integer.")
    if duration is not None and start_s is None and end_s is None:
        raise click.ClickException("--duration needs --start-date or --end-date as an anchor.")

    start_d = _parse_date(start_s) if start_s else None
    end_d = _parse_date(end_s) if end_s else None

    if start_d and end_d and end_d < start_d:
        raise click.ClickException("--end-date is before --start-date.")

    if duration is not None:
        if start_d is not None and end_d is None:
            end_d = start_d + timedelta(days=duration - 1)
        elif end_d is not None and start_d is None:
            start_d = end_d - timedelta(days=duration - 1)
    return start_d, end_d


def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise click.ClickException(f"Invalid date '{s}': expected YYYY-MM-DD.")


def main() -> None:
    argv = sys.argv[1:]
    known_top = {"init", "task", "help", "serve", "up", "down"}
    if argv and not argv[0].startswith("-") and argv[0] not in known_top:
        argv = ["serve"] + argv
    cli.main(args=argv, prog_name="tsk", standalone_mode=True)


if __name__ == "__main__":
    main()
