# TODO

## Tasks

- [ ] REFACTOR(18c87): Rename package to `todofile`.
  The CLI entry point stays `tsk`.
- [ ] REFACTOR(a7e8c): Make add and remove first class commands.
  Tasks are added with the `task add` command. And removed with the `task remove` command.
- [ ] FEAT(1a194): Command 'annotate' to add a note.
  Notes are added with the `annotate` command.
- [ ] REFACTOR(09067): Default tags should be DOCS, ENV, REFACTOR, FEAT, FIX, PERF, TESTS.
  Should also start with a colour palette when initializing the project.
- [ ] FEAT(a1b6a): Add `tsk restart [path]` command (performs down and up).
- [ ] FEAT(270df): Align horizontally tasks in task panel with gantt visualisation
- [ ] FEAT(33e74): Make notes clickable with popup window like tasks
  - [ ] FEAT(446b5): Add 'delete' button to notes in the pop up window
- [ ] FEAT(2cb04): Make the pop up window's content (task and note) editable.
  Only the description of the task and the note should be editable.
- [ ] FIX(d1f2f): When automatically editing the TODO, after any h (h1, h2, h3) there should be an empty line
- [ ] FIX(47a77): tasks are appended to Notes section if Notes section exists
  after the last task.
  Instead it should go under the project's tasks and Notes should always be at the end of the project.
- [ ] FEAT(095f3): the `tsk init` command should have the same options as `tsk config` so that the project is initiated already with the correct options
- [ ] FEAT(8a283): Make gantt/calendar panel toggle on/off and add tsk config --show-calendar/--no-show-calendar option
