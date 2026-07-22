const API = '/api/v1/dashboard';

const LIGHT_LABEL = { green: '健康', yellow: '降级', red: '异常', off: '未知' };

function fmtBytes(n) {
  if (n == null) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0, v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return v.toFixed(v < 10 ? 1 : 0) + ' ' + units[i];
}

function fmtTime(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('zh-CN'); } catch { return iso; }
}

function fmtDuration(sec) {
  if (sec == null) return '—';
  const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60);
  if (d > 0) return `${d}天 ${h}时`;
  if (h > 0) return `${h}时 ${m}分`;
  return `${m}分`;
}

function lightDot(level) {
  return `<span class="light-dot ${level || 'off'}"></span>`;
}

function renderOverall(data) {
  const level = data.overall_light || 'off';
  document.getElementById('overallDot').className = `light-dot ${level}`;
  document.getElementById('overallText').textContent =
    LIGHT_LABEL[level] + (level === 'off' ? '（无上报端）' : '');
}

function renderSummary(data) {
  document.getElementById('reportersOnline').textContent = `${data.reporters_online} / ${data.reporters_total}`;
  let totalMp = 0, totalMod = 0;
  Object.values(data.games || {}).forEach(g => {
    totalMp += (g.modpacks || []).length;
    totalMod += (g.mods || []).length;
  });
  document.getElementById('totalModpacks').textContent = totalMp;
  document.getElementById('totalMods').textContent = totalMod;
  document.getElementById('generatedAt').textContent = '生成于 ' + fmtTime(data.generated_at);
}

function renderReporter(card, r) {
  const cls = r.online ? 'online' : 'offline';
  const badge = r.online
    ? '<span class="badge online">在线</span>'
    : '<span class="badge offline">离线</span>';
  const kindBadge = `<span class="badge kind">${r.kind}</span>`;
  const light = r.light || { level: 'off', reason: '' };
  const m = r.metrics || {};
  let rows = '';
  if (r.kind === 'client') {
    const installed = (m.installed_modpacks || []).map(i => `<span class="chip">${i.name || i.id}</span>`).join('');
    rows = `
      <div><span class="k">灯色原因</span><span title="${light.reason}">${light.reason || '—'}</span></div>
      <div><span class="k">协议版本</span><span>${r.protocol_version}</span></div>
      <div><span class="k">已安装整合包</span><span>${(m.installed_modpacks || []).length}</span></div>
      <div><span class="k">上次同步</span><span>${fmtTime(m.last_sync_at)}</span></div>
      <div><span class="k">距上次上报</span><span>${r.seconds_since_seen}s</span></div>
      <div><span class="k">上报次数</span><span>${r.received_count}</span></div>
      ${installed ? `<div class="installed-list">${installed}</div>` : ''}
    `;
  } else {
    rows = `
      <div><span class="k">灯色原因</span><span title="${light.reason}">${light.reason || '—'}</span></div>
      <div><span class="k">协议版本</span><span>${r.protocol_version}</span></div>
      <div><span class="k">整合包</span><span>${m.modpack_count ?? 0}</span></div>
      <div><span class="k">模组</span><span>${m.mod_count ?? 0}</span></div>
      <div><span class="k">存储占用</span><span>${fmtBytes(m.storage_used_bytes)}</span></div>
      <div><span class="k">累计错误</span><span>${m.error_count ?? 0}</span></div>
      <div><span class="k">运行时长</span><span>${fmtDuration(m.uptime_seconds)}</span></div>
      <div><span class="k">地址</span><span>${r.base_url || '—'}</span></div>
      <div><span class="k">距上次上报</span><span>${r.seconds_since_seen}s</span></div>
      <div><span class="k">上报次数</span><span>${r.received_count}</span></div>
    `;
  }
  card.innerHTML = `<div class="card reporter-card ${cls}" style="border-left-color: ${lightColor(light.level)}">
    <div class="reporter-head">
      <span class="reporter-name">${lightDot(light.level)} ${r.name}</span>
      <span>${badge}${kindBadge}</span>
    </div>
    <div class="reporter-rows">${rows}</div>
  </div>`;
}

function lightColor(level) {
  return { green: '#22c55e', yellow: '#eab308', red: '#ef4444', off: '#cbd5e1' }[level] || '#cbd5e1';
}

function renderGroup(containerId, byKind, kinds) {
  const wrap = document.getElementById(containerId);
  const items = [];
  kinds.forEach(k => {
    const group = byKind[k];
    if (group) items.push(...group.items);
  });
  if (!items.length) { wrap.innerHTML = '<div class="empty">暂无上报</div>'; return; }
  wrap.innerHTML = '';
  items.forEach(r => {
    const card = document.createElement('div');
    renderReporter(card, r);
    wrap.appendChild(card);
  });
}

function renderServers(data) {
  renderGroup('serverList', data.by_kind || {}, ['windows-server', 'web-server']);
}

function renderClients(data) {
  renderGroup('clientList', data.by_kind || {}, ['client']);
}

function renderGames(games) {
  const wrap = document.getElementById('gameList');
  const keys = Object.keys(games || {});
  if (!keys.length) { wrap.innerHTML = '<div class="empty">暂无推送条目</div>'; return; }
  wrap.innerHTML = keys.map(g => {
    const block = games[g];
    const mpRows = (block.modpacks || []).map(mp => `
      <tr>
        <td>${mp.name}</td><td>${mp.version}</td>
        <td>${mp.game_version}</td><td>${mp.mod_loader}</td>
        <td><span class="tag">${mp.source}</span></td>
        <td>${fmtBytes(mp.file_size)}</td>
      </tr>`).join('');
    const modRows = (block.mods || []).map(m => `
      <tr>
        <td>${m.name}</td><td>${m.version}</td>
        <td>${m.game_version || '—'}</td><td>—</td>
        <td><span class="tag">${m.source}</span></td>
        <td>${fmtBytes(m.file_size)}</td>
      </tr>`).join('');
    return `<div class="game-block">
      <div class="game-title">${g}</div>
      <table class="item-table">
        <thead><tr><th>名称</th><th>版本</th><th>游戏版本</th><th>加载器</th><th>来源</th><th>大小</th></tr></thead>
        <tbody>${mpRows}${modRows}</tbody>
      </table>
    </div>`;
  }).join('');
}

async function load() {
  try {
    const res = await fetch(API);
    const data = await res.json();
    renderOverall(data);
    renderSummary(data);
    renderServers(data);
    renderClients(data);
    renderGames(data.games);
  } catch (e) {
    document.getElementById('generatedAt').textContent = '加载失败: ' + e;
  }
}

load();
setInterval(load, 5000);
