# Agent instructions — editing this TODO.md

This file lives in `.<filename>.dir/agent.md`. It tells coding assistants how
to safely edit the sibling `TODO.md` so the `tsk` task manager stays in sync.

## 1. The file is the source of truth

The sibling `TODO.md` is gittable and human-edited. Every task **must** be on
its own bullet line in `TODO.md`. Metadata (start date, end date, completion
timestamp) lives in `tasks.yaml` next to this file and is managed by `tsk` —
do **not** edit `tasks.yaml` by hand.

## 2. Anatomy of a task line

```
- [ ] <tag>(<hash>): <description>
```

Components:

- `- [ ]` — open task. Use `- [x]` to mark done.
- `<tag>` — optional category (letters, digits, `_`, `-`). May be omitted.
- `(<hash>)` — 5 lowercase hex chars. Assigned by `tsk`. Treat the hash as
  the task's identity — never change it.
- `: <description>` — the human-readable description. Continuation lines
  (further-indented non-checkbox text) become part of the description.

When you add a new task by hand, leave the `(<hash>)` off entirely:

```
- [ ] api: build the parser
```

The next time `tsk` runs (`tsk init`, `tsk up`, `tsk` <path>), it will stamp
a hash into the line.

## 3. Structure

```markdown
# Optional document title       <-- shown in the UI header

## Project name                 <-- starts a project

- [ ] api(a4f9c): top-level task
  Description continues on indented lines.
  - A non-checkbox bullet — part of the description.
  - [ ] (b3d8a): a subtask (one level deeper)
- [x] (c1d2e): completed task
```

Rules:

- `#` H1 is the document title (only the first one is used).
- `##` H2 starts a project. All following tasks belong to it until the next
  `##`.
- Nesting is **two levels max**: a task and its subtasks. Deeper bullets are
  flattened to subtasks with a warning.
- Indentation is lenient (tabs or spaces). For subtasks, prefer 2-space
  indent past the parent.

## 4. Safe edits an agent can make

- **Add a task**: append a new `- [ ]` bullet inside the right `##` section.
  Omit the hash; `tsk` will stamp one.
- **Add a subtask**: append an indented `- [ ]` bullet under its parent's
  block.
- **Mark a task done**: change `- [ ]` to `- [x]` on the same line.
- **Edit a description**: change text after the `:` on the bullet line, or
  the continuation lines below it. **Keep `(<hash>):` exactly as it is.**
- **Move a task between projects**: relocate the entire bullet (and its
  subtasks/description lines) under a different `##`. The hash stays the
  same — its dates move with it.

## 5. Edits to avoid

- Don't rename or rewrite a hash. The hash is the stable identity that links
  the markdown to `tasks.yaml`.
- Don't delete a hash from a bullet line and leave a dangling `()` or
  `(xxxxx):` with bad chars.
- Don't introduce a third level of nesting — it'll be flattened.
- Don't edit `.<file>.dir/tasks.yaml`, `.<file>.dir/config.yaml`, or
  `.<file>.dir/daemon.pid` directly. They are managed by `tsk`.

## 6. CLI commands

If you have shell access, you can use the CLI to make changes too — that's
safer when in doubt:

```bash
tsk add <path/to/TODO.md> -d "the description" -t api -P backend
tsk add <path/to/TODO.md> -d "a subtask" -p <parent-hash>
tsk remove <hash> <path/to/TODO.md>
```

Date flags on `add`: pass at most two of `--start-date YYYY-MM-DD`,
`--end-date YYYY-MM-DD`, `--duration <days>`. The third is derived.

## 7. After editing

Nothing extra to do. The next time the user opens the UI or runs `tsk`, the
file will be re-parsed and any hash-less tasks will be stamped.
