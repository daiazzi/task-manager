// todofile frontend — vanilla ES modules, no build step.

const state = {
  todoPath: '',
  title: null,
  colors: {},
  projects: [],
  warnings: [],
  activeProjects: new Set(),
  view: 'gantt',
  showCompleted: true,
  showDates: true,
  autoRefresh: true,
  calendarMonth: null,
  theme: 'dark',
  textSize: 'medium',
  leftPaneWidth: 480,
  expandedNotes: new Set(),
};

// ---------- helpers ----------

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function storageKey(suffix) {
  return `todofile:${state.todoPath}:${suffix}`;
}

function loadPrefs() {
  try {
    const v = localStorage.getItem(storageKey('view'));
    if (v === 'gantt' || v === 'calendar') state.view = v;
    const sc = localStorage.getItem(storageKey('show-completed'));
    if (sc !== null) state.showCompleted = sc === '1';
    const sd = localStorage.getItem(storageKey('show-dates'));
    if (sd !== null) state.showDates = sd === '1';
    const th = localStorage.getItem(storageKey('theme'));
    if (th === 'light' || th === 'dark') state.theme = th;
    const lw = parseInt(localStorage.getItem(storageKey('left-w')) || '', 10);
    if (Number.isFinite(lw) && lw >= 240 && lw <= 1200) state.leftPaneWidth = lw;
  } catch (e) {
    /* localStorage unavailable */
  }
}

function savePrefs() {
  try {
    localStorage.setItem(storageKey('view'), state.view);
    localStorage.setItem(storageKey('show-completed'), state.showCompleted ? '1' : '0');
    localStorage.setItem(storageKey('show-dates'), state.showDates ? '1' : '0');
    localStorage.setItem(storageKey('theme'), state.theme);
    localStorage.setItem(storageKey('left-w'), String(state.leftPaneWidth));
  } catch (e) {}
}

function applyDatesAttr() {
  document.documentElement.setAttribute('data-dates', state.showDates ? 'on' : 'off');
}

function applyTextSize() {
  document.documentElement.setAttribute('data-text', state.textSize);
}

function applyLeftPaneWidth() {
  document.documentElement.style.setProperty('--left-pane-w', state.leftPaneWidth + 'px');
}

function applyTheme() {
  document.documentElement.setAttribute('data-theme', state.theme);
  const btn = document.querySelector('#theme-btn');
  if (btn) btn.textContent = state.theme === 'dark' ? '☾' : '☀';
}

function parseDate(s) {
  if (!s) return null;
  const [y, m, d] = s.split('-').map(Number);
  if (!y || !m || !d) return null;
  return new Date(Date.UTC(y, m - 1, d));
}

function fmtDate(d) {
  if (!d) return '';
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(d.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${dd}`;
}

function addDays(d, n) {
  const r = new Date(d.getTime());
  r.setUTCDate(r.getUTCDate() + n);
  return r;
}

function dayDiff(a, b) {
  return Math.round((b.getTime() - a.getTime()) / (1000 * 60 * 60 * 24));
}

function todayUTC() {
  const now = new Date();
  return new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
}

function colorFor(tag) {
  const c = state.colors || {};
  if (tag && c[tag]) return c[tag];
  return c.default || '#7aa2f7';
}

function withAlpha(hex, alpha) {
  // hex like #rrggbb → rgba(r,g,b,a)
  if (!hex || hex[0] !== '#' || hex.length !== 7) return hex;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function escapeHtml(s) {
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

// ---------- data ----------

async function fetchTasks() {
  const r = await fetch('/api/tasks');
  if (!r.ok) throw new Error('Failed to fetch tasks');
  return r.json();
}

async function refresh() {
  const btn = $('#refresh-btn');
  btn.disabled = true;
  btn.textContent = 'Refreshing…';
  try {
    const r = await fetch('/api/refresh', { method: 'POST' });
    if (!r.ok) {
      const data = await r.json().catch(() => ({ error: 'refresh failed' }));
      toast(data.error || 'refresh failed', 'error');
    } else {
      const data = await r.json();
      applyData(data);
      render();
    }
  } finally {
    btn.disabled = false;
    btn.textContent = 'Refresh';
  }
}

async function postReorder(project, parentHash, order) {
  const r = await fetch('/api/tasks/reorder', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project, parent_hash: parentHash, order }),
  });
  if (!r.ok) {
    const data = await r.json().catch(() => ({ error: 'reorder failed' }));
    throw new Error(data.error || 'reorder failed');
  }
  return r.json();
}

async function postDone(hash, done) {
  const r = await fetch(`/api/tasks/${hash}/done`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ done }),
  });
  if (!r.ok) {
    const data = await r.json().catch(() => ({ error: 'toggle failed' }));
    throw new Error(data.error || 'toggle failed');
  }
  return r.json();
}

async function postDescription(hash, description) {
  const r = await fetch(`/api/tasks/${hash}/description`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description }),
  });
  if (!r.ok) {
    const data = await r.json().catch(() => ({ error: 'update failed' }));
    throw new Error(data.error || 'update failed');
  }
  return r.json();
}

async function postNoteContent(noteId, content) {
  const r = await fetch(`/api/notes/${noteId}/content`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  if (!r.ok) {
    const data = await r.json().catch(() => ({ error: 'update failed' }));
    throw new Error(data.error || 'update failed');
  }
  return r.json();
}

async function postDates(hash, start, end) {
  const r = await fetch(`/api/tasks/${hash}/dates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start, end }),
  });
  if (!r.ok) {
    const data = await r.json().catch(() => ({ error: 'update failed' }));
    throw new Error(data.error || 'update failed');
  }
  return r.json();
}

function applyData(data) {
  state.todoPath = data.todo_path || '';
  state.title = data.title || null;
  state.colors = data.colors || {};
  state.projects = data.projects || [];
  state.warnings = data.warnings || [];
  state.autoRefresh = typeof data.auto_refresh === 'boolean' ? data.auto_refresh : true;
  // Initialise active projects on first load only
  if (state.activeProjects.size === 0) {
    for (const p of state.projects) state.activeProjects.add(p.name);
  } else {
    // Remove vanished projects, keep new ones inactive? Default: add new as active.
    const names = new Set(state.projects.map((p) => p.name));
    for (const n of [...state.activeProjects]) {
      if (!names.has(n)) state.activeProjects.delete(n);
    }
    for (const n of names) {
      if (!state.activeProjects.has(n) && !state._initialisedProjects) {
        state.activeProjects.add(n);
      }
    }
    state._initialisedProjects = true;
  }
}

// ---------- auto refresh (server events) ----------

let autoRefreshSource = null;

function ensureAutoRefresh() {
  if (!state.autoRefresh) {
    if (autoRefreshSource) {
      try { autoRefreshSource.close(); } catch (e) {}
      autoRefreshSource = null;
    }
    return;
  }
  if (autoRefreshSource) return;
  if (!('EventSource' in window)) return;

  autoRefreshSource = new EventSource('/api/events');
  autoRefreshSource.addEventListener('changed', async () => {
    try {
      const data = await fetchTasks();
      applyData(data);
      render();
      ensureAutoRefresh();
    } catch (e) {
      // ignore transient errors; EventSource will retry
    }
  });
  autoRefreshSource.addEventListener('disabled', () => {
    if (autoRefreshSource) {
      try { autoRefreshSource.close(); } catch (e) {}
      autoRefreshSource = null;
    }
  });
  autoRefreshSource.addEventListener('error', () => {
    // allow browser retry; no-op
  });
}

// ---------- rendering ----------

function visibleTasks() {
  const out = [];
  for (const p of state.projects) {
    if (!state.activeProjects.has(p.name)) continue;
    for (const t of p.tasks) {
      if (!state.showCompleted && t.done) continue;
      out.push(t);
      for (const c of t.subtasks || []) {
        if (!state.showCompleted && c.done) continue;
        out.push(c);
      }
    }
  }
  return out;
}

function render() {
  renderWarnings();
  renderBrand();
  renderProjectChips();
  renderTodoPath();
  renderViewToggle();
  renderShowCompleted();
  renderList();
  if (state.view === 'gantt') {
    $('#gantt-view').hidden = false;
    $('#calendar-view').hidden = true;
    renderGantt();
  } else {
    $('#gantt-view').hidden = true;
    $('#calendar-view').hidden = false;
    renderCalendar();
  }
}

function findTaskByHash(hash) {
  for (const p of state.projects) {
    for (const t of p.tasks || []) {
      if (t.hash === hash) return t;
      for (const c of t.subtasks || []) {
        if (c.hash === hash) return c;
      }
    }
  }
  return null;
}

function renderTodoPath() {
  $('#todo-path').textContent = state.todoPath;
}

function renderBrand() {
  $('#brand').textContent = state.title || 'tsk';
}

function renderViewToggle() {
  $('#view-gantt').classList.toggle('active', state.view === 'gantt');
  $('#view-calendar').classList.toggle('active', state.view === 'calendar');
}

function renderShowCompleted() {
  $('#show-completed').checked = state.showCompleted;
}

function renderWarnings() {
  const el = $('#warnings');
  if (!state.warnings.length) {
    el.hidden = true;
    el.innerHTML = '';
    return;
  }
  el.hidden = false;
  el.innerHTML =
    '<ul>' + state.warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join('') + '</ul>';
}

function renderProjectChips() {
  const host = $('#project-chips');
  host.innerHTML = '';
  for (const p of state.projects) {
    const b = document.createElement('button');
    b.className = 'chip' + (state.activeProjects.has(p.name) ? ' active' : '');
    b.textContent = p.name;
    b.addEventListener('click', () => {
      if (state.activeProjects.has(p.name)) state.activeProjects.delete(p.name);
      else state.activeProjects.add(p.name);
      render();
    });
    host.appendChild(b);
  }
}

function renderProjectNotes(notes, projectName) {
  if (!notes || notes.length === 0) return null;
  const expanded = state.expandedNotes.has(projectName);
  const wrap = document.createElement('div');
  wrap.className = 'project-notes' + (expanded ? ' expanded' : '');

  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'project-notes-toggle';
  toggle.setAttribute('aria-expanded', String(expanded));
  const chip = document.createElement('span');
  chip.className = 'project-notes-chip';
  chip.textContent = `ℹ︎ ${notes.length}`;
  chip.title = `${notes.length} note${notes.length === 1 ? '' : 's'}`;
  const label = document.createElement('span');
  label.className = 'project-notes-label';
  label.textContent = 'Notes';
  toggle.appendChild(chip);
  toggle.appendChild(label);
  toggle.addEventListener('click', () => {
    if (state.expandedNotes.has(projectName)) state.expandedNotes.delete(projectName);
    else state.expandedNotes.add(projectName);
    render();
  });
  wrap.appendChild(toggle);

  const body = document.createElement('div');
  body.className = 'project-notes-body';
  for (const note of notes) {
    const item = document.createElement('div');
    item.className = 'project-note markdown-body';
    item.innerHTML = renderMarkdown(note.content || '');
    item.tabIndex = 0;
    item.setAttribute('role', 'button');
    item.setAttribute('aria-label', 'Open note');
    item.addEventListener('click', () => openNoteModal(note, projectName));
    item.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        openNoteModal(note, projectName);
      }
    });
    body.appendChild(item);
  }
  wrap.appendChild(body);
  return wrap;
}

function renderList() {
  const host = $('#task-list');
  host.innerHTML = '';

  let anyVisible = false;
  for (const p of state.projects) {
    if (!state.activeProjects.has(p.name)) continue;
    const tasks = p.tasks.filter((t) => state.showCompleted || !t.done);
    const notes = p.notes || [];
    if (tasks.length === 0 && notes.length === 0) continue;
    anyVisible = true;
    const section = document.createElement('div');
    section.className = 'project-section';
    const header = document.createElement('div');
    header.className = 'project-header';
    header.textContent = p.name;
    section.appendChild(header);

    const notesEl = renderProjectNotes(notes, p.name);
    if (notesEl) section.appendChild(notesEl);

    for (const t of tasks) {
      section.appendChild(renderTaskRow(t, false));
      for (const c of t.subtasks || []) {
        if (!state.showCompleted && c.done) continue;
        section.appendChild(renderTaskRow(c, true));
      }
    }
    host.appendChild(section);
  }
  if (!anyVisible) {
    host.innerHTML = '<div class="empty-state">No tasks to show.</div>';
  }
}

function renderTaskRow(t, isSubtask) {
  const row = document.createElement('div');
  row.className = 'task-row' + (isSubtask ? ' subtask' : '') + (t.done ? ' done' : '');
  row.dataset.hash = t.hash;
  row.dataset.parent = t.parent_hash || '';
  row.dataset.project = t.project;

  const handle = document.createElement('div');
  handle.className = 'drag-handle';
  handle.draggable = true;
  handle.title = 'Drag to reorder';
  handle.textContent = '⋮⋮';
  attachDragHandlers(handle, row, t);
  row.appendChild(handle);

  const check = document.createElement('div');
  check.className = 'task-check' + (t.done ? ' done' : '');
  check.title = t.done ? 'Click to mark not done' : 'Click to mark done';
  check.setAttribute('role', 'checkbox');
  check.setAttribute('aria-checked', String(t.done));
  check.tabIndex = 0;
  const toggleDone = async () => {
    if (check.dataset.busy === '1') return;
    check.dataset.busy = '1';
    const desired = !t.done;
    try {
      const data = await postDone(t.hash, desired);
      applyData(data);
      render();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      delete check.dataset.busy;
    }
  };
  check.addEventListener('click', toggleDone);
  check.addEventListener('keydown', (e) => {
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      toggleDone();
    }
  });
  row.appendChild(check);

  const meta = document.createElement('div');
  meta.className = 'task-meta';
  const main = document.createElement('div');
  main.className = 'task-desc';
  if (t.tag) {
    const tagEl = document.createElement('span');
    tagEl.className = 'task-tag';
    tagEl.textContent = t.tag;
    const c = colorFor(t.tag);
    tagEl.style.color = c;
    tagEl.style.background = withAlpha(c, 0.18);
    main.appendChild(tagEl);
  }
  const hashEl = document.createElement('span');
  hashEl.className = 'task-hash';
  hashEl.textContent = t.hash;
  main.appendChild(hashEl);
  const descEl = document.createElement('span');
  descEl.textContent = firstLine(t.description);
  main.appendChild(descEl);
  meta.appendChild(main);
  const restDesc = restLines(t.description);
  if (restDesc) {
    const more = document.createElement('div');
    more.className = 'task-description-extra';
    more.textContent = restDesc;
    meta.appendChild(more);
  }
  row.appendChild(meta);

  const startCell = document.createElement('div');
  startCell.className = 'date-cell';
  const start = document.createElement('input');
  start.type = 'date';
  start.value = t.start || '';
  start.title = 'start';
  startCell.appendChild(start);
  row.appendChild(startCell);

  const endCell = document.createElement('div');
  endCell.className = 'date-cell';
  const end = document.createElement('input');
  end.type = 'date';
  end.value = t.end || '';
  end.title = 'end';
  endCell.appendChild(end);
  row.appendChild(endCell);

  // Open modal when clicking on the row (but not on interactive controls).
  row.addEventListener('click', (e) => {
    const tag = (e.target.tagName || '').toLowerCase();
    if (e.target.closest('.task-check')) return;
    if (e.target.closest('.drag-handle')) return;
    if (e.target.closest('.date-cell')) return;
    if (tag === 'input' || tag === 'button' || tag === 'a') return;
    openTaskModal(t);
  });

  let prev = { start: t.start, end: t.end };
  const onChange = async () => {
    const newStart = start.value || null;
    const newEnd = end.value || null;
    if (newStart === prev.start && newEnd === prev.end) return;
    try {
      const result = await postDates(t.hash, newStart, newEnd);
      t.start = result.start;
      t.end = result.end;
      prev = { start: result.start, end: result.end };
      if (state.view === 'gantt') renderGantt();
      else renderCalendar();
    } catch (e) {
      start.value = prev.start || '';
      end.value = prev.end || '';
      toast(e.message, 'error');
    }
  };
  start.addEventListener('change', onChange);
  end.addEventListener('change', onChange);

  return row;
}

// ---------- drag-and-drop reorder ----------

let dragState = null;

function attachDragHandlers(handle, row, task) {
  handle.addEventListener('dragstart', (e) => {
    dragState = {
      hash: task.hash,
      project: task.project,
      parentHash: task.parent_hash || null,
      row,
    };
    row.classList.add('dragging');
    handle.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', task.hash);
  });
  handle.addEventListener('dragend', () => {
    row.classList.remove('dragging');
    handle.classList.remove('dragging');
    document.querySelectorAll('.drag-over-top, .drag-over-bottom')
      .forEach((el) => el.classList.remove('drag-over-top', 'drag-over-bottom'));
    dragState = null;
  });

  row.addEventListener('dragover', (e) => {
    if (!dragState) return;
    // Only allow within the same project + parent
    if (row.dataset.project !== dragState.project) return;
    if ((row.dataset.parent || null) !== (dragState.parentHash || null)) return;
    if (row.dataset.hash === dragState.hash) return;
    e.preventDefault();
    const rect = row.getBoundingClientRect();
    const before = e.clientY < rect.top + rect.height / 2;
    row.classList.toggle('drag-over-top', before);
    row.classList.toggle('drag-over-bottom', !before);
  });

  row.addEventListener('dragleave', () => {
    row.classList.remove('drag-over-top', 'drag-over-bottom');
  });

  row.addEventListener('drop', async (e) => {
    if (!dragState) return;
    if (row.dataset.project !== dragState.project) return;
    if ((row.dataset.parent || null) !== (dragState.parentHash || null)) return;
    if (row.dataset.hash === dragState.hash) return;
    e.preventDefault();
    const rect = row.getBoundingClientRect();
    const before = e.clientY < rect.top + rect.height / 2;
    const newOrder = computeReorder(
      dragState.project,
      dragState.parentHash,
      dragState.hash,
      row.dataset.hash,
      before,
    );
    row.classList.remove('drag-over-top', 'drag-over-bottom');
    if (!newOrder) return;
    try {
      const data = await postReorder(dragState.project, dragState.parentHash, newOrder);
      applyData(data);
      render();
    } catch (err) {
      toast(err.message, 'error');
    }
  });
}

function computeReorder(project, parentHash, movedHash, targetHash, before) {
  // Build the current sibling list of (movedHash, ...siblings) under parentHash in project.
  const proj = state.projects.find((p) => p.name === project);
  if (!proj) return null;
  let siblings;
  if (parentHash) {
    const parent = proj.tasks.find((t) => t.hash === parentHash);
    if (!parent) return null;
    siblings = parent.subtasks || [];
  } else {
    siblings = proj.tasks;
  }
  const order = siblings.map((t) => t.hash);
  const fromIdx = order.indexOf(movedHash);
  if (fromIdx < 0) return null;
  order.splice(fromIdx, 1);
  let targetIdx = order.indexOf(targetHash);
  if (targetIdx < 0) return null;
  if (!before) targetIdx += 1;
  order.splice(targetIdx, 0, movedHash);
  return order;
}

// ---------- splitter ----------

function initSplitter() {
  const splitter = $('#splitter');
  if (!splitter) return;
  let dragging = false;
  splitter.addEventListener('pointerdown', (e) => {
    dragging = true;
    splitter.setPointerCapture(e.pointerId);
    splitter.classList.add('dragging');
    document.body.style.userSelect = 'none';
  });
  splitter.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    const main = $('#main').getBoundingClientRect();
    let w = e.clientX - main.left;
    w = Math.max(240, Math.min(1200, w));
    state.leftPaneWidth = w;
    applyLeftPaneWidth();
    if (state.view === 'gantt') renderGantt();
  });
  splitter.addEventListener('pointerup', (e) => {
    dragging = false;
    splitter.classList.remove('dragging');
    document.body.style.userSelect = '';
    splitter.releasePointerCapture?.(e.pointerId);
    savePrefs();
  });
}

// ---------- modal ----------

function openTaskModal(task) {
  const host = $('#modal-host');
  host.hidden = false;
  host.innerHTML = '';
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.addEventListener('click', (e) => e.stopPropagation());

  const header = document.createElement('div');
  header.className = 'modal-header';

  if (task.tag) {
    const tagEl = document.createElement('span');
    tagEl.className = 'task-tag';
    tagEl.textContent = task.tag;
    const c = colorFor(task.tag);
    tagEl.style.color = c;
    tagEl.style.background = withAlpha(c, 0.18);
    header.appendChild(tagEl);
  }

  const closeBtn = document.createElement('button');
  closeBtn.className = 'modal-close';
  closeBtn.textContent = '✕';
  closeBtn.title = 'Close (Esc)';
  closeBtn.addEventListener('click', closeModal);
  header.appendChild(closeBtn);
  modal.appendChild(header);

  const meta = document.createElement('div');
  meta.className = 'modal-meta';
  meta.innerHTML =
    `<span><b>project</b> ${escapeHtml(task.project)}</span>` +
    `<span><b>hash</b> ${escapeHtml(task.hash)}</span>` +
    `<span><b>status</b> ${task.done ? 'done' : 'open'}</span>` +
    (task.start ? `<span><b>start</b> ${task.start}</span>` : '') +
    (task.end ? `<span><b>end</b> ${task.end}</span>` : '') +
    (task.created ? `<span><b>created</b> ${task.created}</span>` : '');
  modal.appendChild(meta);

  const body = document.createElement('div');
  body.className = 'modal-body';
  body.innerHTML = renderMarkdown(task.description || '');
  modal.appendChild(body);

  const actions = document.createElement('div');
  actions.className = 'modal-actions';
  const editBtn = document.createElement('button');
  editBtn.type = 'button';
  editBtn.className = 'modal-edit';
  editBtn.textContent = 'Edit';
  actions.appendChild(editBtn);
  modal.appendChild(actions);

  let editing = false;
  let textarea = null;
  let saveBtn = null;
  let cancelBtn = null;

  const renderView = (t) => {
    body.innerHTML = renderMarkdown(t.description || '');
  };

  const enterEdit = () => {
    if (editing) return;
    editing = true;
    actions.innerHTML = '';
    textarea = document.createElement('textarea');
    textarea.className = 'modal-editor';
    textarea.value = task.description || '';
    body.innerHTML = '';
    body.appendChild(textarea);
    textarea.focus();

    cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'modal-cancel';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.addEventListener('click', () => {
      editing = false;
      body.innerHTML = '';
      renderView(task);
      actions.innerHTML = '';
      actions.appendChild(editBtn);
    });

    saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'modal-save';
    saveBtn.textContent = 'Save';
    saveBtn.addEventListener('click', async () => {
      if (saveBtn.dataset.busy === '1') return;
      saveBtn.dataset.busy = '1';
      saveBtn.disabled = true;
      cancelBtn.disabled = true;
      try {
        const data = await postDescription(task.hash, textarea.value || '');
        applyData(data);
        render();
        const updated = findTaskByHash(task.hash) || task;
        task = updated;
        editing = false;
        toast('Saved', 'ok');
        // Re-render modal with the updated description.
        body.innerHTML = '';
        renderView(task);
        actions.innerHTML = '';
        actions.appendChild(editBtn);
      } catch (e) {
        toast(e.message, 'error');
      } finally {
        delete saveBtn.dataset.busy;
        saveBtn.disabled = false;
        cancelBtn.disabled = false;
      }
    });

    actions.appendChild(cancelBtn);
    actions.appendChild(saveBtn);
  };

  editBtn.addEventListener('click', enterEdit);

  if ((task.subtasks || []).length) {
    const subhead = document.createElement('h3');
    subhead.textContent = 'Subtasks';
    body.appendChild(subhead);
    const ul = document.createElement('ul');
    for (const c of task.subtasks) {
      const li = document.createElement('li');
      li.textContent = (c.done ? '✓ ' : '○ ') + (c.tag ? `${c.tag} ` : '') + firstLine(c.description);
      ul.appendChild(li);
    }
    body.appendChild(ul);
  }

  host.appendChild(modal);
  host.addEventListener('click', closeModal, { once: true });
}

function closeModal() {
  const host = $('#modal-host');
  host.hidden = true;
  host.innerHTML = '';
}

function openNoteModal(note, projectName) {
  const host = $('#modal-host');
  host.hidden = false;
  host.innerHTML = '';
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.addEventListener('click', (e) => e.stopPropagation());

  const header = document.createElement('div');
  header.className = 'modal-header';

  const closeBtn = document.createElement('button');
  closeBtn.className = 'modal-close';
  closeBtn.textContent = '✕';
  closeBtn.title = 'Close (Esc)';
  closeBtn.addEventListener('click', closeModal);
  header.appendChild(closeBtn);
  modal.appendChild(header);

  const meta = document.createElement('div');
  meta.className = 'modal-meta';
  meta.innerHTML =
    `<span><b>project</b> ${escapeHtml(projectName)}</span>` +
    `<span><b>note</b> ${escapeHtml(note.hash || '')}</span>`;
  modal.appendChild(meta);

  const body = document.createElement('div');
  body.className = 'modal-body';
  body.innerHTML = renderMarkdown(note.content || '');
  modal.appendChild(body);

  const actions = document.createElement('div');
  actions.className = 'modal-actions';
  const editBtn = document.createElement('button');
  editBtn.type = 'button';
  editBtn.className = 'modal-edit';
  editBtn.textContent = 'Edit';
  actions.appendChild(editBtn);
  modal.appendChild(actions);

  let editing = false;
  let textarea = null;
  let saveBtn = null;
  let cancelBtn = null;

  const renderView = (n) => {
    body.innerHTML = renderMarkdown(n.content || '');
  };

  const enterEdit = () => {
    if (editing) return;
    editing = true;
    actions.innerHTML = '';
    textarea = document.createElement('textarea');
    textarea.className = 'modal-editor';
    textarea.value = note.content || '';
    body.innerHTML = '';
    body.appendChild(textarea);
    textarea.focus();

    cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'modal-cancel';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.addEventListener('click', () => {
      editing = false;
      body.innerHTML = '';
      renderView(note);
      actions.innerHTML = '';
      actions.appendChild(editBtn);
    });

    saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'modal-save';
    saveBtn.textContent = 'Save';
    saveBtn.addEventListener('click', async () => {
      if (saveBtn.dataset.busy === '1') return;
      if (!note.hash) {
        toast('Note has no id yet. Refresh and try again.', 'error');
        return;
      }
      saveBtn.dataset.busy = '1';
      saveBtn.disabled = true;
      cancelBtn.disabled = true;
      try {
        const data = await postNoteContent(note.hash, textarea.value || '');
        applyData(data);
        render();
        const proj = state.projects.find((p) => p.name === projectName);
        const updated = proj?.notes?.find((n) => n.hash === note.hash);
        if (updated) note = updated;
        editing = false;
        toast('Saved', 'ok');
        body.innerHTML = '';
        renderView(note);
        actions.innerHTML = '';
        actions.appendChild(editBtn);
      } catch (e) {
        toast(e.message, 'error');
      } finally {
        delete saveBtn.dataset.busy;
        saveBtn.disabled = false;
        cancelBtn.disabled = false;
      }
    });

    actions.appendChild(cancelBtn);
    actions.appendChild(saveBtn);
  };

  editBtn.addEventListener('click', enterEdit);

  host.appendChild(modal);
  host.addEventListener('click', closeModal, { once: true });
}

// ---------- markdown renderer (minimal subset) ----------

function renderMarkdown(text) {
  // Escape first.
  let src = text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
  const lines = src.split('\n');
  const out = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Code fence
    if (/^```/.test(line)) {
      const code = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) {
        code.push(lines[i]);
        i++;
      }
      i++;
      out.push('<pre><code>' + code.join('\n') + '</code></pre>');
      continue;
    }

    // Headings
    const h = line.match(/^(#{1,3})\s+(.*)$/);
    if (h) {
      const level = h[1].length;
      out.push(`<h${level}>${inlineMd(h[2])}</h${level}>`);
      i++;
      continue;
    }

    // List
    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ''));
        i++;
      }
      out.push('<ul>' + items.map((it) => `<li>${inlineMd(it)}</li>`).join('') + '</ul>');
      continue;
    }

    // Blank line
    if (line.trim() === '') {
      i++;
      continue;
    }

    // Paragraph (collect until blank line, heading, or list)
    const para = [];
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !/^(#{1,3})\s+/.test(lines[i]) &&
      !/^\s*[-*]\s+/.test(lines[i]) &&
      !/^```/.test(lines[i])
    ) {
      para.push(lines[i]);
      i++;
    }
    out.push('<p>' + inlineMd(para.join('\n').replace(/\n/g, '<br>')) + '</p>');
  }

  return out.join('');
}

function inlineMd(s) {
  // bold, italic, code, links — applied in order
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, txt, url) => {
    // basic URL validation
    if (!/^https?:|^mailto:|^#/i.test(url)) return m;
    return `<a href="${url}" target="_blank" rel="noopener">${txt}</a>`;
  });
  return s;
}

function truncate(s, n) {
  if (!s) return '';
  if (s.length <= n) return s;
  return s.slice(0, Math.max(0, n - 1)) + '…';
}

function firstLine(s) {
  if (!s) return '';
  const i = s.indexOf('\n');
  return i < 0 ? s : s.slice(0, i);
}

function restLines(s) {
  if (!s) return '';
  const i = s.indexOf('\n');
  return i < 0 ? '' : s.slice(i + 1).trim();
}

// ---------- Gantt ----------

function renderGantt() {
  const host = $('#gantt-view');
  host.innerHTML = '';

  const tasks = visibleTasks();
  const today = todayUTC();
  let minD = null;
  let maxD = null;
  for (const t of tasks) {
    const s = parseDate(t.start);
    const e = parseDate(t.end);
    if (s && (!minD || s < minD)) minD = s;
    if (e && (!maxD || e > maxD)) maxD = e;
    if (s && (!maxD || s > maxD)) maxD = s;
    if (e && (!minD || e < minD)) minD = e;
  }
  if (!minD) minD = today;
  if (!maxD) maxD = addDays(today, 14);
  minD = addDays(minD, -2);
  maxD = addDays(maxD, 2);
  const days = dayDiff(minD, maxD) + 1;
  const dayWidth = Math.max(28, Math.floor(900 / days));

  const wrap = document.createElement('div');
  wrap.className = 'gantt';
  wrap.style.minWidth = days * dayWidth + 'px';

  const header = document.createElement('div');
  header.className = 'gantt-header';
  for (let i = 0; i < days; i++) {
    const d = addDays(minD, i);
    const lbl = document.createElement('div');
    lbl.className = 'gantt-day-label';
    const dow = d.getUTCDay();
    if (dow === 0 || dow === 6) lbl.classList.add('weekend');
    if (d.getTime() === today.getTime()) lbl.classList.add('today');
    lbl.style.width = dayWidth + 'px';
    lbl.textContent = d.getUTCDate();
    lbl.title = fmtDate(d);
    header.appendChild(lbl);
  }
  wrap.appendChild(header);

  const body = document.createElement('div');
  body.className = 'gantt-body';

  for (const t of tasks) {
    const row = document.createElement('div');
    row.className = 'gantt-row';
    const s = parseDate(t.start);
    const e = parseDate(t.end);
    if (s || e) {
      const start = s || e;
      const end = e || s;
      const x0 = dayDiff(minD, start) * dayWidth;
      const w = Math.max((dayDiff(start, end) + 1) * dayWidth - 4, 6);
      const bar = document.createElement('div');
      bar.className = 'gantt-bar' + (t.done ? ' done' : '');
      bar.style.left = x0 + 2 + 'px';
      bar.style.width = w + 'px';
      if (!t.done) {
        const c = colorFor(t.tag);
        bar.style.background = withAlpha(c, 0.4);
        bar.style.borderColor = c;
      }
      bar.title = `${t.hash} ${t.description}${t.start ? `\nstart: ${t.start}` : ''}${t.end ? `\nend: ${t.end}` : ''}`;
      bar.textContent = (t.tag ? `${t.tag} ` : '') + firstLine(t.description);
      row.appendChild(bar);
    }
    body.appendChild(row);
  }

  // today line
  if (today >= minD && today <= maxD) {
    const x = dayDiff(minD, today) * dayWidth + dayWidth / 2;
    const line = document.createElement('div');
    line.className = 'gantt-today-line';
    line.style.left = x + 'px';
    body.appendChild(line);
  }

  wrap.appendChild(body);
  host.appendChild(wrap);
}

// ---------- Calendar ----------

function renderCalendar() {
  const host = $('#calendar-view');
  host.innerHTML = '';

  const tasks = visibleTasks();
  let referenceMonth = state.calendarMonth;
  if (!referenceMonth) {
    let earliest = null;
    for (const t of tasks) {
      const s = parseDate(t.start);
      if (s && (!earliest || s < earliest)) earliest = s;
    }
    referenceMonth = earliest || todayUTC();
    state.calendarMonth = new Date(Date.UTC(referenceMonth.getUTCFullYear(), referenceMonth.getUTCMonth(), 1));
  }

  const header = document.createElement('div');
  header.className = 'calendar-header';
  const prev = document.createElement('button');
  prev.textContent = '‹';
  prev.addEventListener('click', () => {
    state.calendarMonth = new Date(Date.UTC(state.calendarMonth.getUTCFullYear(), state.calendarMonth.getUTCMonth() - 1, 1));
    renderCalendar();
  });
  const next = document.createElement('button');
  next.textContent = '›';
  next.addEventListener('click', () => {
    state.calendarMonth = new Date(Date.UTC(state.calendarMonth.getUTCFullYear(), state.calendarMonth.getUTCMonth() + 1, 1));
    renderCalendar();
  });
  const label = document.createElement('div');
  const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  label.textContent = `${monthNames[state.calendarMonth.getUTCMonth()]} ${state.calendarMonth.getUTCFullYear()}`;
  header.appendChild(prev);
  header.appendChild(label);
  header.appendChild(next);
  host.appendChild(header);

  const grid = document.createElement('div');
  grid.className = 'calendar-grid';

  const weekdays = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  for (const w of weekdays) {
    const c = document.createElement('div');
    c.className = 'calendar-weekday';
    c.textContent = w;
    grid.appendChild(c);
  }

  // First day of month, ISO weekday (1=Mon..7=Sun)
  const monthStart = state.calendarMonth;
  const monthEnd = new Date(Date.UTC(monthStart.getUTCFullYear(), monthStart.getUTCMonth() + 1, 0));
  const firstDow = (monthStart.getUTCDay() + 6) % 7; // shift so Monday=0
  const gridStart = addDays(monthStart, -firstDow);
  const totalCells = Math.ceil((firstDow + monthEnd.getUTCDate()) / 7) * 7;
  const today = todayUTC();

  for (let i = 0; i < totalCells; i++) {
    const day = addDays(gridStart, i);
    const cell = document.createElement('div');
    cell.className = 'calendar-day';
    if (day.getUTCMonth() !== monthStart.getUTCMonth()) cell.classList.add('other-month');
    if (day.getTime() === today.getTime()) cell.classList.add('today');
    const num = document.createElement('div');
    num.className = 'day-num';
    num.textContent = day.getUTCDate();
    cell.appendChild(num);

    for (const t of tasks) {
      const s = parseDate(t.start);
      const e = parseDate(t.end) || s;
      if (!s) continue;
      if (day >= s && day <= e) {
        const pill = document.createElement('div');
        pill.className = 'calendar-pill' + (t.done ? ' done' : '');
        const desc = truncate(firstLine(t.description), 14);
        pill.textContent = (t.tag ? `${t.tag} ` : '') + desc;
        pill.title = `${t.hash} — ${t.description}`;
        if (!t.done) {
          const c = colorFor(t.tag);
          pill.style.background = withAlpha(c, 0.25);
          pill.style.borderLeftColor = c;
        }
        pill.addEventListener('click', () => {
          const row = document.querySelector(`.task-row[data-hash="${t.hash}"]`);
          if (row) row.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
        cell.appendChild(pill);
      }
    }
    grid.appendChild(cell);
  }
  host.appendChild(grid);
}

// ---------- toasts ----------

function toast(message, kind) {
  const host = $('#toast-host');
  const el = document.createElement('div');
  el.className = 'toast ' + (kind || '');
  el.textContent = message;
  host.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ---------- init ----------

async function init() {
  $('#refresh-btn').addEventListener('click', refresh);
  $('#view-gantt').addEventListener('click', () => {
    state.view = 'gantt';
    savePrefs();
    render();
  });
  $('#view-calendar').addEventListener('click', () => {
    state.view = 'calendar';
    savePrefs();
    render();
  });
  $('#show-completed').addEventListener('change', (e) => {
    state.showCompleted = e.target.checked;
    savePrefs();
    render();
  });
  $('#show-dates').addEventListener('change', (e) => {
    state.showDates = e.target.checked;
    applyDatesAttr();
    savePrefs();
  });
  document.addEventListener('keydown', (e) => {
    if ((e.key === 'Escape' || e.key === 'Esc') && !$('#modal-host').hidden) {
      e.preventDefault();
      closeModal();
    }
  });
  $('#theme-btn').addEventListener('click', () => {
    state.theme = state.theme === 'dark' ? 'light' : 'dark';
    applyTheme();
    savePrefs();
  });

  try {
    const data = await fetchTasks();
    state.todoPath = data.todo_path || '';
    if (data.theme === 'light' || data.theme === 'dark') state.theme = data.theme;
    if (typeof data.show_dates === 'boolean') state.showDates = data.show_dates;
    if (['small', 'medium', 'big'].includes(data.text_size)) state.textSize = data.text_size;
    loadPrefs();
    applyTheme();
    applyDatesAttr();
    applyTextSize();
    applyLeftPaneWidth();
    $('#show-dates').checked = state.showDates;
    initSplitter();
    applyData(data);
    render();
    ensureAutoRefresh();
  } catch (e) {
    toast(e.message, 'error');
  }
}

init();
