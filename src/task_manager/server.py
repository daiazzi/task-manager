from __future__ import annotations

import json
import socket
import threading
import webbrowser
from datetime import date
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import parser as parser_mod
from . import store
from . import writer as writer_mod
from .models import ParsedDocument


STATIC_DIR = Path(__file__).parent / "static"


def _serialise(doc: ParsedDocument, todo_path: Path) -> dict:
    cfg = store.load_config(todo_path)
    def task_dict(task) -> dict:
        return {
            "hash": task.hash,
            "tag": task.tag,
            "description": task.description,
            "done": task.done,
            "parent_hash": task.parent_hash,
            "project": task.project,
            "start": task.start.isoformat() if task.start else None,
            "end": task.end.isoformat() if task.end else None,
            "created": task.created.isoformat(timespec="seconds") if task.created else None,
            "completed": task.completed.isoformat(timespec="seconds") if task.completed else None,
            "subtasks": [task_dict(c) for c in doc.children_of(task.hash)],
        }

    return {
        "todo_path": str(todo_path),
        "title": doc.title,
        "colors": cfg.colors,
        "theme": cfg.theme,
        "projects": [
            {"name": p.name, "tasks": [task_dict(t) for t in p.tasks]} for p in doc.projects
        ],
        "warnings": doc.warnings,
    }


def _reload(todo_path: Path) -> ParsedDocument:
    text = todo_path.read_text(encoding="utf-8")
    existing = parser_mod.existing_hashes(text)
    doc = parser_mod.parse_text(text, path=todo_path)
    unstamped = [h for h in doc.tasks_by_hash if h.startswith("__new")]
    if unstamped:
        new_text, _ = writer_mod.stamp_hashes(text, existing)
        todo_path.write_text(new_text, encoding="utf-8")
        doc = parser_mod.parse(todo_path)
    store.sync(doc, todo_path)
    return doc


def build_app(todo_path: Path) -> Starlette:
    todo_path = Path(todo_path).resolve()

    async def index(request: Request) -> Response:
        return FileResponse(STATIC_DIR / "index.html")

    async def get_tasks(request: Request) -> Response:
        doc = _reload(todo_path)
        return JSONResponse(_serialise(doc, todo_path))

    async def post_refresh(request: Request) -> Response:
        try:
            doc = _reload(todo_path)
        except OSError as e:
            return JSONResponse({"error": f"TODO.md not readable: {e}"}, status_code=500)
        return JSONResponse(_serialise(doc, todo_path))

    async def post_dates(request: Request) -> Response:
        hash_ = request.path_params["hash"]
        body = await request.body()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid JSON body."}, status_code=400)

        doc = _reload(todo_path)
        if hash_ not in doc.tasks_by_hash:
            return JSONResponse({"error": f"No task with hash '{hash_}'."}, status_code=404)

        current = doc.tasks_by_hash[hash_]
        new_start = current.start
        new_end = current.end

        if "start" in data:
            v = data["start"]
            if v is None:
                new_start = None
            elif isinstance(v, str):
                try:
                    new_start = date.fromisoformat(v)
                except ValueError:
                    return JSONResponse(
                        {"error": f"Invalid date '{v}': expected YYYY-MM-DD."}, status_code=400
                    )
            else:
                return JSONResponse({"error": "start must be a date string or null."}, status_code=400)

        if "end" in data:
            v = data["end"]
            if v is None:
                new_end = None
            elif isinstance(v, str):
                try:
                    new_end = date.fromisoformat(v)
                except ValueError:
                    return JSONResponse(
                        {"error": f"Invalid date '{v}': expected YYYY-MM-DD."}, status_code=400
                    )
            else:
                return JSONResponse({"error": "end must be a date string or null."}, status_code=400)

        if new_start and new_end and new_end < new_start:
            return JSONResponse({"error": "end is before start."}, status_code=400)

        meta = store.set_dates(todo_path, hash_, new_start, new_end)
        return JSONResponse(
            {
                "hash": meta.hash,
                "start": meta.start.isoformat() if meta.start else None,
                "end": meta.end.isoformat() if meta.end else None,
            }
        )

    routes = [
        Route("/", index),
        Route("/api/tasks", get_tasks),
        Route("/api/refresh", post_refresh, methods=["POST"]),
        Route("/api/tasks/{hash}/dates", post_dates, methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=str(STATIC_DIR)), name="static"),
    ]

    return Starlette(routes=routes)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run(
    todo_path: Path,
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
    open_browser: bool = True,
) -> None:
    if port is None:
        port = _find_free_port()

    app = build_app(todo_path)
    url = f"http://{host}:{port}"

    print(f"tsk: serving {todo_path}")
    print(f"tsk: open {url}")

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    print("tsk: stopped")
