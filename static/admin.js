const TOKEN_KEY = 'gpm_token';
const USER_KEY = 'gpm_user';

function getToken() { return localStorage.getItem(TOKEN_KEY); }
function authHeaders() { return { 'Authorization': 'Bearer ' + getToken() }; }
function logout() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); location.href = '/login'; }

// 后端错误体格式：{"error":{"code":..,"message":..,"details":..}}，提取可读消息
function errMsg(data, fallback) {
  if (!data) return fallback;
  const e = data.error;
  if (typeof e === 'string') return e;
  if (e && typeof e === 'object') return e.message || e.code || fallback;
  return data.detail || data.message || fallback;
}

if (!getToken()) { location.href = '/login'; }
else {
  document.getElementById('userBadge').textContent = localStorage.getItem(USER_KEY) || 'admin';
  document.getElementById('logoutBtn').addEventListener('click', logout);
}

// Tab 切换
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.style.display = 'none');
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).style.display = '';
    if (btn.dataset.tab === 'users') loadUsers();
    if (btn.dataset.tab === 'config') loadConfig();
  });
});

// ---------- 配置 ----------
async function loadConfig() {
  try {
    const res = await api('/api/v1/config');
    if (!res) return;
    const d = await res.json();
    document.getElementById('cfgAdminUrl').value = d.admin_url || '';
    document.getElementById('cfgPublicBaseUrl').value = d.public_base_url || '';
    document.getElementById('cfgServerName').value = d.server_name || '';
    document.getElementById('cfgInterval').value = d.reporter_interval || 10;
  } catch (e) { console.error(e); }
}
document.getElementById('saveConfigBtn').addEventListener('click', async () => {
  const btn = document.getElementById('saveConfigBtn');
  const msg = document.getElementById('configMsg');
  btn.disabled = true; btn.textContent = '保存中…'; msg.className = 'form-msg'; msg.textContent = '';
  const body = {
    admin_url: document.getElementById('cfgAdminUrl').value.trim(),
    public_base_url: document.getElementById('cfgPublicBaseUrl').value.trim(),
    server_name: document.getElementById('cfgServerName').value.trim(),
    reporter_interval: parseFloat(document.getElementById('cfgInterval').value) || 10,
  };
  try {
    const res = await api('/api/v1/config', { method: 'PUT', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await res.json();
    if (res.ok) { msg.className = 'form-msg ok'; msg.textContent = '已保存并热生效'; loadStatus(); }
    else { msg.className = 'form-msg err'; msg.textContent = errMsg(data, '保存失败'); }
  } catch (err) { msg.className = 'form-msg err'; msg.textContent = '网络错误：' + err; }
  btn.disabled = false; btn.textContent = '保存配置';
});

function fmtBytes(n) {
  if (n == null) return '—';
  const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0, v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return v.toFixed(v < 10 ? 1 : 0) + ' ' + u[i];
}
function fmtDuration(sec) {
  if (sec == null) return '—';
  const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60);
  if (d > 0) return d + '天 ' + h + '时';
  if (h > 0) return h + '时 ' + m + '分';
  return m + '分';
}
function shortId(id) { return id ? id.slice(0, 8) : ''; }

async function api(url, opts) {
  const res = await fetch(url, opts);
  if (res.status === 401) { logout(); return null; }
  return res;
}

// 带进度回调的上传（XMLHttpRequest 支持 upload.onprogress，fetch 不支持）
// onProgress(pct) 中 pct 为 0~100
function uploadWithProgress(url, formData, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    const tok = getToken();
    if (tok) xhr.setRequestHeader('Authorization', 'Bearer ' + tok);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress((e.loaded / e.total) * 100);
      }
    };
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch (_) { /* 空 body 兜底 */ }
      if (xhr.status === 401) { logout(); reject(new Error('未授权')); return; }
      resolve({ res: { ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status }, data });
    };
    xhr.onerror = () => reject(new Error('网络错误'));
    xhr.send(formData);
  });
}

// ---------- 状态 ----------
async function loadStatus() {
  try {
    const res = await api('/api/v1/status');
    if (!res) return;
    const d = await res.json();
    document.getElementById('statName').textContent = d.server_name;
    document.getElementById('statUptime').textContent = fmtDuration(d.uptime_seconds);
    document.getElementById('statModpacks').textContent = d.modpack_count;
    document.getElementById('statMods').textContent = d.mod_count;
    document.getElementById('statStorage').textContent = fmtBytes(d.storage_used_bytes);
    document.getElementById('serverKind').textContent = d.server_kind;
  } catch (e) { console.error(e); }
}

// ---------- 整合包 ----------
async function loadModpacks() {
  try {
    const res = await api('/api/v1/modpacks');
    if (!res) return;
    const d = await res.json();
    const tbody = document.getElementById('modpackTbody');
    const items = d.modpacks || [];
    if (!items.length) { tbody.innerHTML = '<tr><td colspan="9" class="empty-row">暂无整合包</td></tr>'; return; }
    tbody.innerHTML = items.map(m => `
      <tr>
        <td title="${m.id}">${shortId(m.id)}</td>
        <td>${m.name}</td>
        <td>${m.version}</td>
        <td>${m.game}</td>
        <td>${m.game_version}</td>
        <td>${m.mod_loader}</td>
        <td>${fmtBytes(m.file_size)}</td>
        <td>${m.enabled ? '<span class="badge-on">上架</span>' : '<span class="badge-off">下架</span>'}</td>
        <td>
          <button class="btn-dl" onclick="dlModpack('${m.id}')">下载</button>
          <button class="btn-edit" onclick="editModpack(${JSON.stringify(m).replace(/"/g,'&quot;')})">编辑</button>
          <button class="btn-toggle" onclick="toggleModpack('${m.id}', ${!m.enabled})">${m.enabled ? '下架' : '上架'}</button>
          <button class="btn-del" onclick="delModpack('${m.id}')">删除</button>
        </td>
      </tr>`).join('');
  } catch (e) { console.error(e); }
}
function dlModpack(id) { window.open('/api/v1/modpacks/' + id + '/download', '_blank'); }
async function toggleModpack(id, enabled) {
  const res = await api('/api/v1/modpacks/' + id, { method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }) });
  if (res && res.ok) loadModpacks();
  else { const e = await res.json().catch(() => ({})); alert('操作失败: ' + errMsg(e, res.status)); }
}
async function delModpack(id) {
  if (!confirm('确定删除该整合包？')) return;
  const res = await api('/api/v1/modpacks/' + id, { method: 'DELETE', headers: authHeaders() });
  if (res && res.ok) { loadModpacks(); loadStatus(); } else { alert('删除失败'); }
}

document.getElementById('modpackForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('modpackUploadBtn');
  const msg = document.getElementById('modpackMsg');
  const prog = document.getElementById('modpackProgress');
  const bar = document.getElementById('modpackProgressBar');
  const ptxt = document.getElementById('modpackProgressText');
  btn.disabled = true; btn.textContent = '上传中…'; msg.className = 'form-msg'; msg.textContent = '';
  prog.style.display = 'flex'; bar.style.width = '0%'; ptxt.textContent = '0%';
  const fd = new FormData(e.target);
  try {
    const { res, data } = await uploadWithProgress('/api/v1/modpacks', fd, (pct) => {
      bar.style.width = pct + '%'; ptxt.textContent = Math.round(pct) + '%';
    });
    if (res.ok) {
      const tip = data.auto_detected ? '上传成功（已自动识别加载器/版本）' : '上传成功';
      msg.className = 'form-msg ok'; msg.textContent = tip;
      e.target.reset(); loadModpacks(); loadStatus();
    } else { msg.className = 'form-msg err'; msg.textContent = errMsg(data, '上传失败'); }
  } catch (err) { msg.className = 'form-msg err'; msg.textContent = '网络错误：' + err; }
  prog.style.display = 'none';
  btn.disabled = false; btn.textContent = '上传整合包';
});

// ---------- 模组 ----------
async function loadMods() {
  try {
    const res = await api('/api/v1/mods');
    if (!res) return;
    const d = await res.json();
    const tbody = document.getElementById('modTbody');
    const items = d.mods || [];
    if (!items.length) { tbody.innerHTML = '<tr><td colspan="9" class="empty-row">暂无模组</td></tr>'; return; }
    tbody.innerHTML = items.map(m => `
      <tr>
        <td title="${m.id}">${shortId(m.id)}</td>
        <td>${m.name}</td>
        <td>${m.version}</td>
        <td>${m.game}</td>
        <td>${m.game_version || '—'}</td>
        <td>${m.mod_loader || '—'}</td>
        <td>${fmtBytes(m.file_size)}</td>
        <td>${m.enabled ? '<span class="badge-on">上架</span>' : '<span class="badge-off">下架</span>'}</td>
        <td>
          <button class="btn-dl" onclick="dlMod('${m.id}')">下载</button>
          <button class="btn-edit" onclick="editMod(${JSON.stringify(m).replace(/"/g,'&quot;')})">编辑</button>
          <button class="btn-toggle" onclick="toggleMod('${m.id}', ${!m.enabled})">${m.enabled ? '下架' : '上架'}</button>
          <button class="btn-del" onclick="delMod('${m.id}')">删除</button>
        </td>
      </tr>`).join('');
  } catch (e) { console.error(e); }
}
function dlMod(id) { window.open('/api/v1/mods/' + id + '/download', '_blank'); }
async function toggleMod(id, enabled) {
  const res = await api('/api/v1/mods/' + id, { method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }) });
  if (res && res.ok) loadMods();
  else { const e = await res.json().catch(() => ({})); alert('操作失败: ' + errMsg(e, res.status)); }
}
async function delMod(id) {
  if (!confirm('确定删除该模组？')) return;
  const res = await api('/api/v1/mods/' + id, { method: 'DELETE', headers: authHeaders() });
  if (res && res.ok) { loadMods(); loadStatus(); } else { alert('删除失败'); }
}

document.getElementById('modForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('modUploadBtn');
  const msg = document.getElementById('modMsg');
  const prog = document.getElementById('modProgress');
  const bar = document.getElementById('modProgressBar');
  const ptxt = document.getElementById('modProgressText');
  btn.disabled = true; btn.textContent = '上传中…'; msg.className = 'form-msg'; msg.textContent = '';
  prog.style.display = 'flex'; bar.style.width = '0%'; ptxt.textContent = '0%';
  const fd = new FormData(e.target);
  try {
    const { res, data } = await uploadWithProgress('/api/v1/mods', fd, (pct) => {
      bar.style.width = pct + '%'; ptxt.textContent = Math.round(pct) + '%';
    });
    if (res.ok) {
      const tip = data.auto_detected ? '上传成功（已自动识别加载器/版本）' : '上传成功';
      msg.className = 'form-msg ok'; msg.textContent = tip;
      e.target.reset(); loadMods(); loadStatus();
    }
    else { msg.className = 'form-msg err'; msg.textContent = errMsg(data, '上传失败'); }
  } catch (err) { msg.className = 'form-msg err'; msg.textContent = '网络错误：' + err; }
  prog.style.display = 'none';
  btn.disabled = false; btn.textContent = '上传模组';
});

// ---------- 游戏列表（填充上传表单的下拉选项）----------
async function loadGames() {
  try {
    const res = await api('/api/v1/games');
    if (!res) return;
    const d = await res.json();
    const games = d.games || [];
    const items = games.length ? games : [{ name: 'minecraft', display_name: 'Minecraft' }];
    const opts = items.map(g => `<option value="${g.name}">${g.display_name || g.name}</option>`).join('');
    const mpSel = document.getElementById('modpackGame');
    const modSel = document.getElementById('modGame');
    if (mpSel) mpSel.innerHTML = opts;
    if (modSel) modSel.innerHTML = opts;
  } catch (e) { console.error(e); }
}

// ---------- 编辑对话框 ----------
let _editKind = '', _editId = '';
function editModpack(m) {
  _editKind = 'modpacks'; _editId = m.id;
  openEditModal('编辑整合包', [
    { k: 'name', label: '名称', v: m.name },
    { k: 'version', label: '版本', v: m.version },
    { k: 'game', label: '游戏', v: m.game },
    { k: 'game_version', label: '游戏版本', v: m.game_version },
    { k: 'mod_loader', label: '加载器', v: m.mod_loader, select: ['vanilla','forge','fabric','quilt'] },
    { k: 'mod_loader_version', label: '加载器版本', v: m.mod_loader_version || '' },
    { k: 'description', label: '描述', v: m.description },
    { k: 'enabled', label: '上架', v: m.enabled, bool: true },
  ]);
}
function editMod(m) {
  _editKind = 'mods'; _editId = m.id;
  openEditModal('编辑模组', [
    { k: 'name', label: '名称', v: m.name },
    { k: 'version', label: '版本', v: m.version },
    { k: 'game', label: '游戏', v: m.game },
    { k: 'description', label: '描述', v: m.description },
    { k: 'enabled', label: '上架', v: m.enabled, bool: true },
  ]);
}
function openEditModal(title, fields) {
  document.getElementById('editModalTitle').textContent = title;
  const form = document.getElementById('editForm');
  form.className = 'upload-form';
  form.innerHTML = fields.map(f => {
    if (f.bool) {
      return `<div class="form-row"><label class="full">${f.label}<input type="checkbox" name="${f.k}" ${f.v ? 'checked' : ''} /></label></div>`;
    }
    if (f.select) {
      return `<div class="form-row"><label class="full">${f.label}<select name="${f.k}">${f.select.map(o => `<option value="${o}" ${o === f.v ? 'selected' : ''}>${o}</option>`).join('')}</select></label></div>`;
    }
    return `<div class="form-row"><label class="full">${f.label}<input type="text" name="${f.k}" value="${(f.v ?? '').toString().replace(/"/g, '&quot;')}" /></label></div>`;
  }).join('');
  document.getElementById('editModal').style.display = 'flex';
}
function closeEditModal() { document.getElementById('editModal').style.display = 'none'; }

document.getElementById('editSaveBtn').addEventListener('click', async () => {
  const form = document.getElementById('editForm');
  const fd = new FormData(form);
  const body = {};
  fd.forEach((v, k) => { body[k] = k === 'enabled' ? (fd.get(k) === 'on') : v; });
  const res = await api('/api/v1/' + _editKind + '/' + _editId, { method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (res && res.ok) { closeEditModal(); if (_editKind === 'modpacks') loadModpacks(); else loadMods(); loadStatus(); }
  else { const e = await res.json().catch(() => ({})); alert('保存失败: ' + errMsg(e, res.status)); }
});

// ---------- 用户管理 ----------
async function loadUsers() {
  try {
    const res = await api('/api/v1/users', { headers: authHeaders() });
    if (!res) return;
    const d = await res.json();
    const tbody = document.getElementById('userTbody');
    const users = d.users || [];
    const me = localStorage.getItem(USER_KEY);
    tbody.innerHTML = users.map(u => {
      const isAdmin = u.role === 'admin';
      const roleBadge = isAdmin ? '<span class="badge-on">管理员</span>' : '<span class="badge-off">普通</span>';
      const toggleBtn = `<button class="btn-toggle" onclick="toggleRole('${u.username}', '${isAdmin ? 'user' : 'admin'}')">${isAdmin ? '降为普通' : '升为管理员'}</button>`;
      const delBtn = `<button class="btn-del" onclick="delUser('${u.username}')" ${u.username === me ? 'disabled' : ''}>删除</button>`;
      return `<tr>
        <td>${u.username}${u.username === me ? ' <span class="badge-on">当前</span>' : ''}</td>
        <td>${roleBadge}</td>
        <td>${toggleBtn} ${delBtn}</td>
      </tr>`;
    }).join('');
  } catch (e) { console.error(e); }
}
async function toggleRole(u, role) {
  const res = await api('/api/v1/users/' + u, { method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ role }) });
  if (res && res.ok) loadUsers();
  else { const e = await res.json().catch(() => ({})); alert('操作失败: ' + errMsg(e, res.status)); }
}
async function delUser(id) {
  if (!confirm('确定删除用户 ' + id + '？')) return;
  const res = await api('/api/v1/users/' + id, { method: 'DELETE', headers: authHeaders() });
  if (res && res.ok) loadUsers(); else { const e = await res.json().catch(() => ({})); alert('删除失败: ' + errMsg(e, res.status)); }
}
document.getElementById('addUserForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('addUserBtn');
  const msg = document.getElementById('userMsg');
  btn.disabled = true; msg.className = 'form-msg'; msg.textContent = '';
  const fd = new FormData(e.target);
  const body = { username: fd.get('username'), password: fd.get('password'), is_admin: fd.get('is_admin') === 'on' };
  try {
    const res = await api('/api/v1/users', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await res.json();
    if (res.ok) { msg.className = 'form-msg ok'; msg.textContent = '已添加' + (data.role === 'admin' ? '（管理员）' : ''); e.target.reset(); loadUsers(); }
    else { msg.className = 'form-msg err'; msg.textContent = errMsg(data, '添加失败'); }
  } catch (err) { msg.className = 'form-msg err'; msg.textContent = '网络错误：' + err; }
  btn.disabled = false;
});

// ---------- 改密码 ----------
document.getElementById('changePwdBtn').addEventListener('click', () => {
  document.getElementById('pwdForm').reset();
  document.getElementById('pwdMsg').textContent = '';
  document.getElementById('pwdModal').style.display = 'flex';
});
document.getElementById('pwdSaveBtn').addEventListener('click', async () => {
  const form = document.getElementById('pwdForm');
  const fd = new FormData(form);
  const msg = document.getElementById('pwdMsg');
  if (fd.get('new_password') !== fd.get('confirm')) { msg.className = 'form-msg err'; msg.textContent = '两次新密码不一致'; return; }
  msg.className = 'form-msg'; msg.textContent = '';
  try {
    const res = await api('/api/v1/auth/password', { method: 'PUT', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ old_password: fd.get('old_password'), new_password: fd.get('new_password') }) });
    const data = await res.json();
    if (res.ok) { document.getElementById('pwdModal').style.display = 'none'; alert('密码已修改'); logout(); }
    else { msg.className = 'form-msg err'; msg.textContent = errMsg(data, '修改失败'); }
  } catch (err) { msg.className = 'form-msg err'; msg.textContent = '网络错误：' + err; }
});

// 首次加载 + 定时刷新
loadStatus(); loadModpacks(); loadMods(); loadGames();
setInterval(loadStatus, 10000);
