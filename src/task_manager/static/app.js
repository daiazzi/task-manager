// task-manager frontend — vanilla ES modules, no build step.

const state = {
  todoPath: '',
  projects: [],
  warnings: [],
  activeProjects: new Set(),
  view: 'gantt',
  showCompleted: true,
  calendarMonth: null,
};

// ---------- helpers ----------

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function storageKey(suffix) {
  return `task-manager:${state.todoPath}:${suffix}`;
}

function loadPrefs() {
  try {
    const v = localStorage.getItem(storageKey('view'));
    if (v === 'gantt' || v === 'calendar') state.view = v;
    const sc = localStorage.getItem(storageKey('show-completed'));
    if (sc !== null) state.showCompleted = sc === '1';
  } catch (e) {
    /* localStorage unavailable */
  }
}

function savePrefs() {
  try {
    localStorage.setItem(storageKey('view'), state.view);
    localStorage.setItem(storageKey('show-completed'), state.showCompleted ? '1' : '0');
  } catch (e) {}
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
  state.projects = data.projects || [];
  state.warnings = data.warnings || [];
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

function renderTodoPath() {
  $('#todo-path').textContent = state.todoPath;
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

function renderList() {
  const host = $('#task-list');
  host.innerHTML = '';

  let anyVisible = false;
  for (const p of state.projects) {
    if (!state.activeProjects.has(p.name)) continue;
    const tasks = p.tasks.filter((t) => state.showCompleted || !t.done);
    if (tasks.length === 0) continue;
    anyVisible = true;
    const section = document.createElement('div');
    section.className = 'project-section';
    const header = document.createElement('div');
    header.className = 'project-header';
    header.textContent = p.name;
    section.appendChild(header);

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

  const check = document.createElement('div');
  check.className = 'task-check' + (t.done ? ' done' : '');
  check.textContent = t.done ? '[x]' : '[ ]';
  row.appendChild(check);

  const meta = document.createElement('div');
  meta.className = 'task-meta';
  const main = document.createElement('div');
  main.className = 'task-desc';
  let extras = '';
  if (t.tag) extras += `<span class="task-tag">${escapeHtml(t.tag)}</span>`;
  extras += `<span class="task-hash">${escapeHtml(t.hash)}</span>`;
  main.innerHTML = extras + escapeHtml(firstLine(t.description));
  meta.appendChild(main);
  const restDesc = restLines(t.description);
  if (restDesc) {
    const more = document.createElement('div');
    more.className = 'task-description-extra';
    more.textContent = restDesc;
    meta.appendChild(more);
  }
  row.appendChild(meta);

  const dates = document.createElement('div');
  dates.className = 'date-inputs';
  const start = document.createElement('input');
  start.type = 'date';
  start.value = t.start || '';
  start.title = 'start';
  const end = document.createElement('input');
  end.type = 'date';
  end.value = t.end || '';
  end.title = 'end';
  dates.appendChild(start);
  dates.appendChild(end);
  row.appendChild(dates);

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
        pill.textContent = (t.tag ? `${t.tag} ` : '') + firstLine(t.description);
        pill.title = `${t.hash} — ${t.description}`;
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

  try {
    const data = await fetchTasks();
    state.todoPath = data.todo_path || '';
    loadPrefs();
    applyData(data);
    render();
  } catch (e) {
    toast(e.message, 'error');
  }
}

init();
