/* ══ NTT DATA · OT Red Team · Command Center JS ══════════════════════ */

const app = { user: null, netBlocked: false, sseSource: null, logEntries: [] };

/* ── Helpers ────────────────────────────────────────────────────────── */
const el  = id => document.getElementById(id);
const qs  = s  => document.querySelector(s);

function toast(msg, type = 'info') {
  const c = el('toastContainer');
  const t = document.createElement('div');
  t.className = `toast-item ${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 4500);
}

async function api(path, opts = {}) {
  const defaults = { headers: { 'Content-Type': 'application/json' } };
  const res = await fetch(path, { ...defaults, ...opts });
  if (res.status === 401) { window.location.href = '/'; return null; }
  return res.json();
}

/* ── Clock ──────────────────────────────────────────────────────────── */
setInterval(() => {
  const d = new Date();
  el('clock').textContent = d.toTimeString().substr(0, 8);
}, 1000);

/* ── Auth ───────────────────────────────────────────────────────────── */
async function initAuth() {
  const data = await api('/api/user');
  if (!data || !data.authenticated) { window.location.href = '/'; return false; }
  app.user = data.user;
  el('topbarUser').textContent = data.user.username.toUpperCase();
  return true;
}

/* ── Navigation ─────────────────────────────────────────────────────── */
const VIEW_LABELS = {
  'command-center': 'Command Center',
  history: 'Historial',
  logs: 'Log Viewer',
  status: 'Estado del Sistema',
};

document.querySelectorAll('.nav-item[data-view]').forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    switchView(link.dataset.view);
  });
});

function switchView(view) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const nav = qs(`.nav-item[data-view="${view}"]`);
  if (nav) nav.classList.add('active');
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  const vEl = el(`view-${view}`);
  if (vEl) vEl.classList.add('active');
  el('topbarPage').textContent = VIEW_LABELS[view] || view;
  if (view === 'history')   loadHistory();
  if (view === 'status')    loadStatus();
}

/* ── Sidebar toggle ─────────────────────────────────────────────────── */
el('sidebarToggle').addEventListener('click', () => el('sidebar').classList.toggle('collapsed'));
el('menuBtn').addEventListener('click', () => el('sidebar').classList.toggle('open'));

/* ── Logout ─────────────────────────────────────────────────────────── */
el('logoutBtn').addEventListener('click', async () => {
  await api('/api/logout', { method: 'POST' });
  window.location.href = '/';
});

/* ── Stop All ───────────────────────────────────────────────────────── */
el('btnStopAll').addEventListener('click', async () => {
  const btn = el('btnStopAll');
  btn.disabled = true;
  btn.textContent = '⏳ Deteniendo…';
  try {
    const r = await api('/api/commands/ctrl_stop_all/execute', { method: 'POST', body: JSON.stringify({ params: {} }) });
    if (r) toast(r.message || 'Stop All ejecutado.', 'info');
  } finally {
    btn.disabled = false;
    btn.textContent = '⬛ Stop All';
  }
  // Refrescar inmediatamente y de nuevo tras 1.5s para que los monitores
  // hayan tenido tiempo de desregistrarse y actualizar el historial
  await pollActiveOps();
  await loadStats();
  setTimeout(async () => { await pollActiveOps(); await loadStats(); loadHistory(); }, 1500);
});

/* ═══════════════════════════════════════════════════════════════════════
   NETWORK STATUS
═══════════════════════════════════════════════════════════════════════ */
async function checkNetwork() {
  const data = await api('/api/network');
  if (!data) return;
  const dot    = el('netDot');
  const label  = el('netLabel');
  const widget = el('netWidget');
  const banner = el('netBanner');
  const banMsg = el('netBannerMsg');

  widget.className = 'net-widget';

  if (data.status === 'ok') {
    widget.classList.add('ok');
    label.textContent = data.current || 'OK';
    banner.classList.add('hidden');
    app.netBlocked = false;
    setCommandsBlocked(false);
  } else if (data.status === 'unconfigured') {
    widget.classList.add('ok');
    label.textContent = 'Sin filtro';
    banner.classList.add('hidden');
    app.netBlocked = false;
    setCommandsBlocked(false);
  } else if (data.status === 'wrong_network') {
    widget.classList.add('wrong');
    label.textContent = data.current || 'Desconocida';
    banMsg.textContent = `Red incorrecta. Actual: "${data.current}" · Esperada: "${data.expected}"`;
    banner.classList.remove('hidden');
    app.netBlocked = true;
    setCommandsBlocked(true);
  } else {
    widget.classList.add('none');
    label.textContent = 'Sin conexión';
    banMsg.textContent = 'Sin conexión Wi-Fi detectada. Conecte a la red requerida.';
    banner.classList.remove('hidden');
    app.netBlocked = true;
    setCommandsBlocked(true);
  }

  // Status view
  const netJson = el('networkJson');
  if (netJson) netJson.textContent = JSON.stringify(data, null, 2);
  const dot2 = el('netStatusDot');
  if (dot2) {
    dot2.className = 'panel-dot ' + (data.status === 'ok' || data.status === 'unconfigured' ? 'success' : 'danger');
  }
}

function setCommandsBlocked(blocked) {
  document.querySelectorAll('.cmd-btn.execute').forEach(btn => {
    btn.disabled = blocked;
    btn.title = blocked ? 'Conecte a la red requerida.' : '';
  });
}

el('netRetryBtn').addEventListener('click', () => checkNetwork());

/* ═══════════════════════════════════════════════════════════════════════
   COMMAND CENTER
═══════════════════════════════════════════════════════════════════════ */
async function loadCommandCenter() {
  const data = await api('/api/commands/by-category');
  if (!data) return;

  const container = el('commandCenter');
  container.innerHTML = '';
  const cats = data.categories || {};
  let totalCmds = 0;

  for (const [cat, cmds] of Object.entries(cats)) {
    totalCmds += cmds.length;
    const section = document.createElement('div');
    section.className = 'cmd-category';
    section.innerHTML = `
      <div class="cmd-category-header">
        <span class="cmd-category-title">${cat}</span>
        <span class="cmd-category-count">${cmds.length} comandos</span>
      </div>
      <div class="cmd-grid" id="grid-${cat.replace(/[^a-z0-9]/gi,'_')}"></div>
    `;
    container.appendChild(section);

    const grid = section.querySelector('.cmd-grid');
    for (const cmd of cmds) {
      grid.appendChild(buildCmdCard(cmd));
    }
  }

  el('kpiCmds').textContent = totalCmds;
}

function buildCmdCard(cmd) {
  const card = document.createElement('div');
  card.className = `cmd-card danger-${cmd.danger_level}`;
  card.innerHTML = `
    <div class="cmd-card-key">${cmd.category} · [${cmd.key || '–'}]</div>
    <div class="cmd-card-label">${cmd.label}</div>
    <div class="cmd-card-desc">${cmd.description}</div>
    <span class="cmd-card-danger ${cmd.danger_level}">${cmd.danger_level.toUpperCase()}</span>
    <div class="cmd-card-actions">
      <button class="cmd-btn execute" data-id="${cmd.id}" ${app.netBlocked ? 'disabled' : ''}>
        ▶ Ejecutar
      </button>
      ${cmd.background ? `<button class="cmd-btn secondary" data-cancel data-id="${cmd.id}" style="display:none">⬛ Detener</button>` : ''}
      <button class="cmd-btn secondary" data-history data-id="${cmd.id}">Historial</button>
    </div>
  `;

  card.querySelector('.cmd-btn.execute').addEventListener('click', () => {
    openExecuteModal(cmd);
  });

  const histBtn = card.querySelector('[data-history]');
  if (histBtn) histBtn.addEventListener('click', () => {
    switchView('history');
  });

  return card;
}

/* ═══════════════════════════════════════════════════════════════════════
   MODAL
═══════════════════════════════════════════════════════════════════════ */
let _modalCmd = null;

function openExecuteModal(cmd) {
  _modalCmd = cmd;
  el('modalTitle').textContent = cmd.label;
  const body = el('modalBody');

  let html = `<p class="modal-cmd-desc">${cmd.description}</p>`;

  if (cmd.danger_level === 'critical' || cmd.danger_level === 'high') {
    html += `
      <div class="modal-danger-warn ${cmd.danger_level}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px;flex-shrink:0">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        Nivel de riesgo: <strong>${cmd.danger_level.toUpperCase()}</strong>. Esta acción afecta sistemas OT reales.
      </div>`;
  }

  if (cmd.params && cmd.params.length) {
    for (const p of cmd.params) {
      html += `
        <div class="mb-3">
          <label class="form-label-dark">${p.label}${p.required ? ' *' : ''}</label>
          <input type="${p.type === 'number' ? 'number' : 'text'}"
                 class="input-dark" style="width:100%;"
                 id="param_${p.name}" value="${p.default ?? ''}"
                 placeholder="${p.label}" ${p.required ? 'required' : ''}>
        </div>`;
    }
  }

  if (cmd.background) {
    html += `<p style="font-size:12px;color:#7A8190;margin-top:8px;">⚙ Operación background. Puede detenerla con "Stop All".</p>`;
  }

  body.innerHTML = html;
  el('modalOverlay').classList.remove('hidden');
}

el('modalClose').addEventListener('click',  () => el('modalOverlay').classList.add('hidden'));
el('modalCancel').addEventListener('click', () => el('modalOverlay').classList.add('hidden'));
el('modalOverlay').addEventListener('click', e => { if (e.target === el('modalOverlay')) el('modalOverlay').classList.add('hidden'); });

el('modalConfirm').addEventListener('click', async () => {
  if (!_modalCmd) return;
  const cmd = _modalCmd;
  el('modalOverlay').classList.add('hidden');

  const params = {};
  if (cmd.params) {
    for (const p of cmd.params) {
      const inp = el(`param_${p.name}`);
      if (inp) params[p.name] = p.type === 'number' ? Number(inp.value) : inp.value;
    }
  }

  const btn = qs(`.cmd-btn.execute[data-id="${cmd.id}"]`);
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Ejecutando…'; }

  const r = await api(`/api/commands/${cmd.id}/execute`, {
    method: 'POST',
    body: JSON.stringify({ params }),
  });

  if (btn) { btn.disabled = app.netBlocked; btn.textContent = '▶ Ejecutar'; }

  if (!r) return;
  const type = r.ok ? (cmd.danger_level === 'critical' ? 'warn' : 'success') : 'danger';
  toast(r.message || (r.ok ? `${cmd.label} ejecutado.` : r.error), type);

  // Log in console
  addLogLine(r.ok ? 'success' : 'error', `[${cmd.label}] ${r.message || r.error || ''}`, r.exec_id);

  // Refresh KPIs
  setTimeout(() => { loadStats(); pollActiveOps(); }, 600);
});

/* ═══════════════════════════════════════════════════════════════════════
   KPI STATS
═══════════════════════════════════════════════════════════════════════ */
async function loadStats() {
  const data = await api('/api/history/stats');
  if (!data) return;
  const s = data.stats || {};
  el('kpiTotal').textContent   = s.total   ?? '—';
  el('kpiSuccess').textContent = s.success ?? '—';
}

async function pollActiveOps() {
  const data = await api('/api/operations/active');
  if (!data) return;
  const ops = data.operations || [];
  const count = ops.length;
  el('kpiActive').textContent = count;
  const badge = el('kpiActiveBadge');
  badge.className = 'kpi-badge ' + (count > 0 ? 'warn' : 'info');
  badge.textContent = count > 0 ? 'En ejecución' : 'Background';
  const opsEl = el('topbarOps');
  if (count > 0) {
    opsEl.textContent = `${count} activo${count > 1 ? 's' : ''}`;
    opsEl.classList.add('visible');
  } else {
    opsEl.classList.remove('visible');
  }
}

/* ═══════════════════════════════════════════════════════════════════════
   HISTORY
═══════════════════════════════════════════════════════════════════════ */
function _formatDuration(r) {
  // Para operaciones aun en ejecucion: calcular tiempo transcurrido desde started_at
  if (r.status === 'running' && r.started_at) {
    try {
      const startMs = new Date(r.started_at).getTime();
      const elapsedMs = Date.now() - startMs;
      if (elapsedMs < 0) return '—';
      if (elapsedMs < 1000) return `${elapsedMs}ms`;
      const s = elapsedMs / 1000;
      if (s < 60) return `${s.toFixed(1)}s ⏳`;
      const m = Math.floor(s / 60);
      const rem = Math.floor(s % 60);
      return `${m}m${rem.toString().padStart(2,'0')}s ⏳`;
    } catch (_) { return '⏳'; }
  }
  // Para operaciones finalizadas: usar duration_ms registrado por el backend
  if (r.duration_ms != null) {
    return r.duration_ms < 1000 ? `${r.duration_ms}ms` : `${(r.duration_ms/1000).toFixed(1)}s`;
  }
  return '—';
}

async function loadHistory() {
  const data = await api('/api/history?limit=80');
  if (!data) return;
  const rows = data.history || [];
  const body = el('historyBody');
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="7" class="text-center text-muted-custom p-4">Sin registros.</td></tr>';
    return;
  }
  const hasRunning = rows.some(r => r.status === 'running');
  body.innerHTML = rows.map(r => {
    const started = r.started_at ? r.started_at.replace('T',' ').replace('Z','').substr(0,19) : '—';
    const dur = _formatDuration(r);
    const st  = r.status || 'unknown';
    return `<tr>
      <td><span style="color:#4A8FC7;font-family:monospace;">#${r.id}</span></td>
      <td>${r.label || r.command_id}</td>
      <td><span style="color:#7A8190;font-size:12px;">${r.category || ''}</span></td>
      <td>${r.username || '—'}</td>
      <td style="font-family:monospace;font-size:12px;">${started}</td>
      <td style="font-family:monospace;font-size:12px;">${dur}</td>
      <td><span class="status-badge ${st}">${st.toUpperCase()}</span></td>
    </tr>`;
  }).join('');
  // Si hay operaciones corriendo, refrescar el historial cada 5s para actualizar duracion
  if (hasRunning) {
    clearTimeout(app._historyRefreshTimer);
    app._historyRefreshTimer = setTimeout(() => {
      if (document.querySelector('#view-history.active')) loadHistory();
    }, 5000);
  }
}

el('btnRefreshHistory').addEventListener('click', loadHistory);
el('btnClearHistory').addEventListener('click', async () => {
  if (!confirm('¿Vaciar todo el historial? Esta acción no se puede deshacer.')) return;
  const r = await api('/api/history', { method: 'DELETE' });
  if (r?.ok) { toast('Historial vaciado.', 'info'); loadHistory(); loadStats(); }
  else toast(r?.message || 'Error al vaciar historial.', 'danger');
});

/* ═══════════════════════════════════════════════════════════════════════
   LOG VIEWER — SSE streaming
═══════════════════════════════════════════════════════════════════════ */
function addLogLine(level, message, execId) {
  const box = el('logConsole');
  if (!box) return;
  const ts = new Date().toTimeString().substr(0, 8);
  const line = document.createElement('div');
  line.className = 'log-line';
  const execTag = execId ? `<span class="log-exec-id">[#${execId}]</span>` : '';
  line.innerHTML = `<span class="log-ts">${ts}</span><span class="log-level-${level}">[${level.toUpperCase()}]</span>${execTag}<span class="log-msg">${message}</span>`;
  line.dataset.level = level;
  line.dataset.msg = message.toLowerCase();
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
  app.logEntries.push(line);
  applyLogFilter();
}

function applyLogFilter() {
  const text  = (el('logFilter')?.value || '').toLowerCase();
  const level = el('logLevelFilter')?.value || '';
  const box   = el('logConsole');
  if (!box) return;
  Array.from(box.querySelectorAll('.log-line')).forEach(line => {
    const matchText  = !text  || (line.dataset.msg || '').includes(text);
    const matchLevel = !level || (line.dataset.level || '') === level;
    line.style.display = (matchText && matchLevel) ? '' : 'none';
  });
}

el('logFilter')?.addEventListener('input',  applyLogFilter);
el('logLevelFilter')?.addEventListener('change', applyLogFilter);
el('btnClearLogs')?.addEventListener('click', () => {
  const box = el('logConsole');
  if (box) { box.innerHTML = ''; app.logEntries = []; }
});

function startSSE() {
  if (app.sseSource) return;
  const src = new EventSource('/api/logs/stream');
  app.sseSource = src;
  src.onmessage = e => {
    try {
      const d = JSON.parse(e.data);
      if (d.type === 'connected') return;
      addLogLine(d.level || 'info', d.message || '', d.exec_id);
    } catch {}
  };
  src.onerror = () => {
    src.close();
    app.sseSource = null;
    setTimeout(startSSE, 3000);
  };
}

/* ═══════════════════════════════════════════════════════════════════════
   STATUS VIEW
═══════════════════════════════════════════════════════════════════════ */
async function loadStatus() {
  const data = await api('/api/status');
  if (data) el('statusJson').textContent = JSON.stringify(data, null, 2);
  await checkNetwork();
}

/* ═══════════════════════════════════════════════════════════════════════
   HEARTBEAT — mantiene vivo el proceso backend mientras el front está abierto
   Si la pestaña se cierra o queda inactiva, el backend se auto-cierra
   tras INACTIVITY_TIMEOUT segundos (por defecto 5 min, configurable en .env)
═══════════════════════════════════════════════════════════════════════ */
async function sendHeartbeat() {
  try {
    await fetch('/api/heartbeat', { method: 'POST' });
  } catch (_) {}
}

// Enviar latido inmediatamente y luego cada 30 segundos
sendHeartbeat();
setInterval(sendHeartbeat, 30000);

// También enviar latido en cada interacción del usuario
['click', 'keydown', 'mousemove', 'scroll'].forEach(evt =>
  document.addEventListener(evt, () => sendHeartbeat(), { passive: true })
);

/* ═══════════════════════════════════════════════════════════════════════
   PERIODIC REFRESH
═══════════════════════════════════════════════════════════════════════ */
setInterval(() => { pollActiveOps(); }, 5000);
setInterval(() => { checkNetwork(); }, 30000);
// Auto-refrescar historial si hay operaciones activas
setInterval(async () => {
  const data = await api('/api/operations/active');
  if (data && (data.operations || []).length > 0) {
    if (document.querySelector('#view-history.active')) loadHistory();
    loadStats();
  }
}, 8000);

/* ═══════════════════════════════════════════════════════════════════════
   INIT
═══════════════════════════════════════════════════════════════════════ */
(async () => {
  const ok = await initAuth();
  if (!ok) return;
  await checkNetwork();
  await loadCommandCenter();
  await loadStats();
  await pollActiveOps();
  startSSE();
  addLogLine('info', `Sesión iniciada como ${app.user?.username || '?'}`);
})();
