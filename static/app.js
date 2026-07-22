const API = '/api/v1/dashboard';

function fmtBytes(n) {
  if (!n && n !== 0) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0, v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return v.toFixed(v < 10 ? 1 : 0) + ' ' + units[i];
}

function fmtDuration(sec) {
  if (sec == null) return '—';
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d > 0) return `${d}天 ${h}时`;
  if (h > 0) return `${h}时 ${m}分`;
  return `${m}分`;
}

function fmtTime(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('zh-CN'); } catch { return iso; }
}

function renderSummary(data) {
  document.getElementById('serversOnline').textContent = `${data.servers_online} / ${data.servers_total}`;
  document.getElementById('totalModpacks').textContent = data.total_modpacks;
  document.getElementById('totalMods').textContent = data.total_mods;
  document.getElementById('generatedAt').textContent = '生成于 ' + fmtTime(data.generated_at);
}

function renderServers(servers) {
  const wrap = document.getElementById('serverList');
  if (!servers || !servers.length) { wrap.innerHTML = '<div class="empty">未配置监测目标</div>'; return; }
  wrap.innerHTML = servers.map(s => {
    const status = s.status || {};
    const cls = s.online ? 'online' : 'offline';
    const badge = s.online ? '<span class="badge online">在线</span>' : '<span class="badge offline">离线</span>';
    const rows = s.online ? `
      <div><span class="k">协议版本</span><span>${status.protocol_version || '—'}</span></div>
      <div><span class="k">运行时长</span><span>${fmtDuration(status.uptime_seconds)}</span></div>
      <div><span class="k">整合包</span><span>${status.modpack_count ?? 0}</span></div>
      <div><span class="k">模组</span><span>${status.mod_count ?? 0}</span></div>
      <div><span class="k">存储占用</span><span>${fmtBytes(status.storage_used_bytes)}</span></div>
      <div><span class="k">延迟</span><span>${s.latency_ms ?? '—'} ms</span></div>
      <div><span class="k">地址</span><span>${s.base_url}</span></div>
    ` : `<div><span class="k">地址</span><span>${s.base_url}</span></div>`;
    const err = s.last_error ? `<div class="server-error">${s.last_error}</div>` : '';
    return `<div class="card server-card ${cls}">
      <div class="server-head"><span class="server-name">${s.name}</span>${badge}</div>
      <div class="server-rows">${rows}</div>
      ${err}
    </div>`;
  }).join('');
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
    renderSummary(data);
    renderServers(data.servers);
    renderGames(data.games);
  } catch (e) {
    document.getElementById('generatedAt').textContent = '加载失败: ' + e;
  }
}

document.getElementById('refreshBtn').addEventListener('click', async () => {
  const btn = document.getElementById('refreshBtn');
  btn.disabled = true; btn.textContent = '刷新中…';
  try { await fetch(API + '/refresh'); } catch {}
  await load();
  btn.disabled = false; btn.textContent = '立即刷新';
});

load();
setInterval(load, 10000);
