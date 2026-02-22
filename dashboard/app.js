// ── 数据层 ──────────────────────────────────────────
const DB = {
  get: (key, def=[]) => { try { return JSON.parse(localStorage.getItem(key)) || def; } catch { return def; } },
  set: (key, val) => localStorage.setItem(key, JSON.stringify(val)),
  signals:  () => DB.get('signals'),
  history:  () => DB.get('push_history'),
  positions:() => DB.get('positions'),
  saveSignals:  (v) => DB.set('signals', v),
  saveHistory:  (v) => DB.set('push_history', v),
  savePositions:(v) => DB.set('positions', v),
};

// ── 工具函数 ─────────────────────────────────────────
const fmt = (v, d=2) => (v>=0?'+':'')+v.toFixed(d)+'%';
const arr = v => v>1?'🚀':v>0.3?'📈':v>0?'↗️':v>-0.3?'↘️':v>-1?'📉':'🔻';
const uid = () => 'id_'+Date.now()+'_'+Math.random().toString(36).slice(2,6);
const today = () => new Date().toISOString().slice(0,10);

// ── 推送历史记录 ─────────────────────────────────────
function pushHistory(type, title, content) {
  const hist = DB.history();
  hist.unshift({ id: uid(), type, title, content,
    time: new Date().toLocaleString('zh-CN', {hour12:false}) });
  if (hist.length > 500) hist.pop();
  DB.saveHistory(hist);
}

// ── Tab 切换 ─────────────────────────────────────────
function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.style.display='none');
      btn.classList.add('active');
      document.getElementById('panel-'+btn.dataset.tab).style.display='block';
      renderTab(btn.dataset.tab);
    });
  });
}

function renderTab(tab) {
  if (tab==='overview')  renderOverview();
  if (tab==='signals')   renderSignals();
  if (tab==='positions') renderPositions();
  if (tab==='history')   renderHistory();
  if (tab==='settings')  renderSettings();
}

// ── Tab 1: 今日概览 ───────────────────────────────────
function renderOverview() {
  const signals   = DB.signals();
  const positions = DB.positions();
  const hist      = DB.history();

  // 统计
  const todaySigs  = signals.filter(s=>s.time&&s.time.startsWith(today())).length;
  const activePosi = positions.filter(p=>!p.closed).length;
  const closed     = positions.filter(p=>p.closed);
  const winRate    = closed.length ? Math.round(closed.filter(p=>p.exit_type==='win').length/closed.length*100)+'%' : '--';

  document.getElementById('stat-signals').textContent  = todaySigs;
  document.getElementById('stat-positions').textContent = activePosi;
  document.getElementById('stat-winrate').textContent   = winRate;

  // 核心持仓动态（从最近信号里找，没有就占位）
  const cores = ['TSLA','GOOGL','NVDA','META'];
  const coreHtml = cores.map(t => {
    const sig = signals.find(s=>s.ticker===t);
    return `<div class="core-card">
      <div class="core-ticker">${t}</div>
      ${sig ? `<div class="core-price">$${sig.price}</div><div class="core-score">评分 ${sig.score}</div>` : '<div class="core-placeholder">等待信号</div>'}
    </div>`;
  }).join('');
  document.getElementById('core-holdings').innerHTML = coreHtml;

  // 今日推送时间线
  const todayHist = hist.filter(h=>h.time&&h.time.startsWith(today().replace(/-/g,'/')||today()));
  const typeIcon = {morning_brief:'🌅',deep_analysis:'📊',buy_signal:'🎯',evening_review:'🌙',exit_alert:'🛡️'};
  const timelineHtml = todayHist.length
    ? todayHist.map(h=>`
      <div class="timeline-item" onclick="toggleExpand(this)">
        <div class="timeline-dot ${h.type}"></div>
        <div class="timeline-body">
          <div class="timeline-header">
            <span>${typeIcon[h.type]||'📌'} ${h.title}</span>
            <span class="timeline-time">${h.time.slice(-5)||''}</span>
          </div>
          <div class="timeline-preview">${h.content.slice(0,80)}...</div>
          <pre class="timeline-full" style="display:none">${h.content}</pre>
        </div>
      </div>`).join('')
    : '<div class="empty-msg">今日暂无推送记录</div>';
  document.getElementById('today-timeline').innerHTML = timelineHtml;
}

window.toggleExpand = function(el) {
  const full    = el.querySelector('.timeline-full');
  const preview = el.querySelector('.timeline-preview');
  if (!full) return;
  const open = full.style.display !== 'none';
  full.style.display    = open ? 'none' : 'block';
  preview.style.display = open ? 'block' : 'none';
};

// ── Tab 2: 信号列表 ───────────────────────────────────
function renderSignals(filter={}) {
  let sigs = DB.signals().filter(s=>!s.archived);

  if (filter.type && filter.type!=='all') sigs = sigs.filter(s=>s.type===filter.type);
  if (filter.score) sigs = sigs.filter(s=>s.score>=+filter.score);
  if (filter.q)     sigs = sigs.filter(s=>s.ticker.toLowerCase().includes(filter.q.toLowerCase()));

  const grid = document.getElementById('signals-grid');
  if (!sigs.length) { grid.innerHTML='<div class="empty-msg" style="grid-column:1/-1">暂无信号</div>'; return; }

  grid.innerHTML = sigs.map(s => {
    const scoreColor = s.score>=85?'#22c55e':s.score>=70?'#3b82f6':'#f59e0b';
    const ma = s.above_ma200 ? '<span class="badge green">MA200✅</span>' : '<span class="badge red">MA200❌</span>';
    const kbBadge = s.kb_tag ? `<span class="badge gold">${s.kb_tag}</span>` : '';
    return `<div class="sig-card">
      <div class="sig-header">
        <div>
          <span class="sig-ticker">${s.ticker}</span>
          <span class="score-badge" style="background:${scoreColor}">${s.score}</span>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">${kbBadge}${ma}</div>
      </div>
      <div class="sig-prices">
        <div class="price-item"><div class="price-label">当前价</div><div class="price-val">$${s.price}</div></div>
        ${s.suggest_price?`<div class="price-item"><div class="price-label">建议买入</div><div class="price-val green">$${s.suggest_price}</div></div>`:''}
        <div class="price-item"><div class="price-label">止盈</div><div class="price-val green">$${s.tp_price}</div></div>
        <div class="price-item"><div class="price-label">止损</div><div class="price-val red">$${s.sl_price}</div></div>
      </div>
      <div class="sig-indicators">
        RSI <b>${s.rsi14}</b> &nbsp;|&nbsp; BB% <b>${s.bb_pct}</b>
        ${s.suggest_note?`<div class="sig-note">${s.suggest_note}</div>`:''}
      </div>
      <div class="sig-time">🕐 ${s.time}</div>
      ${!s.position_taken?`
      <div class="sig-actions">
        <button class="btn-success" onclick="openTradeModal('${s.id}','${s.ticker}',${s.suggest_price||s.price},${s.tp_price},${s.sl_price})">✅ 已开仓</button>
        <button class="btn-outline" onclick="archiveSig('${s.id}')">忽略</button>
      </div>`:'<div class="sig-taken">✅ 已记录开仓</div>'}
    </div>`;
  }).join('');
}

// 过滤器绑定
function initSignalFilters() {
  ['filter-type','filter-score','filter-q'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', applySignalFilters);
  });
}
function applySignalFilters() {
  renderSignals({
    type:  document.getElementById('filter-type')?.value,
    score: document.getElementById('filter-score')?.value,
    q:     document.getElementById('filter-q')?.value,
  });
}

// ── Tab 3: 我的持仓 ───────────────────────────────────
function renderPositions() {
  const active = DB.positions().filter(p=>!p.closed);
  const closed = DB.positions().filter(p=>p.closed);
  const grid   = document.getElementById('positions-grid');
  const hgrid  = document.getElementById('closed-grid');

  // 活跃持仓
  grid.innerHTML = active.length ? active.map(p => {
    const ret = ((p.current_price-p.entry_price)/p.entry_price*100);
    const cls = ret>=0?'green':'red';
    return `<div class="sig-card">
      <div class="sig-header">
        <span class="sig-ticker">${p.ticker}</span>
        <span class="price-val ${cls} fs20">${fmt(ret)}</span>
      </div>
      <div class="sig-prices">
        <div class="price-item"><div class="price-label">开仓价</div><div class="price-val">$${p.entry_price}</div></div>
        <div class="price-item"><div class="price-label">当前价</div><div class="price-val">$${p.current_price}</div></div>
        <div class="price-item"><div class="price-label">止盈</div><div class="price-val green">$${p.tp}</div></div>
        <div class="price-item"><div class="price-label">止损</div><div class="price-val red">$${p.sl}</div></div>
      </div>
      <div class="sig-actions">
        <button class="btn-success" onclick="closePosition('${p.id}','win')">🎯 止盈出场</button>
        <button class="btn-danger"  onclick="closePosition('${p.id}','loss')">🛡️ 止损出场</button>
      </div>
      <div class="sig-time">🕐 开仓：${p.entry_time}</div>
    </div>`;
  }).join('') : '<div class="empty-msg" style="grid-column:1/-1">暂无持仓</div>';

  // 历史持仓
  hgrid.innerHTML = closed.length ? closed.slice(0,20).map(p => {
    const ret = ((p.exit_price-p.entry_price)/p.entry_price*100);
    const cls = ret>=0?'green':'red';
    return `<div class="sig-card" style="opacity:.8">
      <div class="sig-header">
        <span class="sig-ticker">${p.ticker}</span>
        <span class="price-val ${cls} fs20">${fmt(ret)}</span>
      </div>
      <div class="sig-prices">
        <div class="price-item"><div class="price-label">开仓价</div><div class="price-val">$${p.entry_price}</div></div>
        <div class="price-item"><div class="price-label">出场价</div><div class="price-val">$${p.exit_price}</div></div>
        <div class="price-item"><div class="price-label">结果</div><div class="price-val ${cls}">${p.exit_type==='win'?'🎯 止盈':'🛡️ 止损'}</div></div>
      </div>
      <div class="sig-time">🕐 ${p.exit_time}</div>
    </div>`;
  }).join('') : '<div class="empty-msg" style="grid-column:1/-1">暂无历史</div>';
}

// 平仓
window.closePosition = function(id, type) {
  const positions = DB.positions();
  const p = positions.find(x=>x.id===id);
  if (!p) return;
  const exitPrice = prompt(`输入出场价（参考：$${p.current_price}）:`, p.current_price);
  if (!exitPrice) return;
  p.closed    = true;
  p.exit_price= parseFloat(exitPrice);
  p.exit_type = type;
  p.exit_time = new Date().toLocaleString('zh-CN',{hour12:false});
  DB.savePositions(positions);
  const ret = ((p.exit_price-p.entry_price)/p.entry_price*100);
  pushHistory('exit_alert', `${type==='win'?'止盈':'止损'} ${p.ticker}`,
    `${p.ticker} ${type==='win'?'止盈':'止损'}出场 @$${p.exit_price}，盈亏：${fmt(ret)}`);
  renderPositions();
  updateStats();
};

// ── Tab 4: 推送历史 ───────────────────────────────────
function renderHistory() {
  const hist = DB.history();
  const container = document.getElementById('history-list');
  if (!hist.length) { container.innerHTML='<div class="empty-msg">暂无推送历史</div>'; return; }

  // 按日期分组
  const groups = {};
  hist.forEach(h => {
    const date = h.time ? h.time.slice(0,10) : '未知';
    if (!groups[date]) groups[date] = [];
    groups[date].push(h);
  });

  const typeIcon  = {morning_brief:'🌅',deep_analysis:'📊',buy_signal:'🎯',evening_review:'🌙',exit_alert:'🛡️'};
  const typeLabel = {morning_brief:'早盘摘要',deep_analysis:'深度早报',buy_signal:'买入信号',evening_review:'收盘复盘',exit_alert:'出场提醒'};

  container.innerHTML = Object.entries(groups).map(([date, items]) => `
    <div class="hist-group">
      <div class="hist-date">${date}</div>
      ${items.map(h=>`
        <div class="hist-item" onclick="toggleExpand(this)">
          <div class="hist-left">
            <span class="hist-icon">${typeIcon[h.type]||'📌'}</span>
            <div>
              <div class="hist-title">${typeLabel[h.type]||h.title}</div>
              <div class="timeline-preview">${h.content.slice(0,60)}...</div>
              <pre class="timeline-full" style="display:none;white-space:pre-wrap;font-family:inherit;font-size:13px;margin-top:8px;color:#cbd5e1">${h.content}</pre>
            </div>
          </div>
          <div class="hist-time">${h.time.slice(-8)||''}</div>
        </div>`).join('')}
    </div>`).join('');
}

// ── Tab 5: 设置 & 导入 ────────────────────────────────
function renderSettings() {}

window.parseAndImport = function() {
  const text   = document.getElementById('import-text').value.trim();
  const result = document.getElementById('import-result');
  if (!text) { result.textContent='请粘贴信号内容'; return; }

  const ticker  = (text.match(/\*\*([A-Z]{1,6})\*\*/) || [])[1];
  const score   = parseInt((text.match(/评分[：:]\s*(\d+)/) || [])[1]);
  const price   = parseFloat((text.match(/当前价[：:]\s*\$([\d.]+)/) || [])[1]);
  const suggest = parseFloat((text.match(/建议买入[：:]\s*\$([\d.]+)/) || [])[1]);
  const rsi     = parseFloat((text.match(/RSI14[：:]\s*([\d.]+)/) || [])[1]);
  const bb      = parseFloat((text.match(/BB%[：:]\s*([\d.]+)/) || [])[1]);
  const tp      = parseFloat((text.match(/止盈[：:]\s*\$([\d.]+)/) || [])[1]);
  const sl      = parseFloat((text.match(/止损[：:]\s*\$([\d.]+)/) || [])[1]);
  const kbTag   = (text.match(/(⭐ 核心持仓|🎯 重点关注)/) || [])[1] || '';

  if (!ticker || !score) { result.textContent='❌ 无法解析，请检查格式'; return; }

  const sigs = DB.signals();
  sigs.unshift({ id:uid(), type:'buy', ticker, score, kb_tag:kbTag,
    price:price||0, suggest_price:suggest||null, rsi14:rsi||0, bb_pct:bb||0,
    tp_price:tp||0, sl_price:sl||0,
    time: new Date().toLocaleString('zh-CN',{hour12:false}),
    archived:false, position_taken:false });
  DB.saveSignals(sigs);
  pushHistory('buy_signal', `买入信号 ${ticker}`, text);
  result.textContent = `✅ 已导入 ${ticker}（评分 ${score}）`;
  document.getElementById('import-text').value='';
  updateStats();
};

// ── 开仓弹窗 ─────────────────────────────────────────
window.openTradeModal = function(sigId, ticker, price, tp, sl) {
  document.getElementById('modal-ticker').value  = ticker;
  document.getElementById('modal-sigid').value   = sigId;
  document.getElementById('modal-ticker-show').textContent = ticker;
  document.getElementById('modal-price').value  = price;
  document.getElementById('modal-tp').value     = tp;
  document.getElementById('modal-sl').value     = sl;
  document.getElementById('modal').style.display='flex';
};
window.closeModal = () => document.getElementById('modal').style.display='none';
window.archiveSig = function(id) {
  const sigs = DB.signals();
  const s = sigs.find(x=>x.id===id);
  if (s) { s.archived=true; DB.saveSignals(sigs); renderSignals(); }
};

function initTradeForm() {
  document.getElementById('trade-form').addEventListener('submit', e => {
    e.preventDefault();
    const sigId  = document.getElementById('modal-sigid').value;
    const ticker = document.getElementById('modal-ticker').value;
    const pos = {
      id: uid(), ticker,
      entry_price: parseFloat(document.getElementById('modal-price').value),
      tp: parseFloat(document.getElementById('modal-tp').value),
      sl: parseFloat(document.getElementById('modal-sl').value),
      current_price: parseFloat(document.getElementById('modal-price').value),
      entry_time: new Date().toLocaleDateString('zh-CN'),
      note: document.getElementById('modal-note').value,
      closed: false,
    };
    const positions = DB.positions();
    positions.push(pos);
    DB.savePositions(positions);
    const sigs = DB.signals();
    const s = sigs.find(x=>x.id===sigId);
    if (s) { s.position_taken=true; DB.saveSignals(sigs); }
    pushHistory('buy_signal', `开仓 ${ticker}`,
      `已开仓 ${ticker} @$${pos.entry_price}，止盈$${pos.tp}，止损$${pos.sl}`);
    closeModal();
    updateStats();
    renderSignals();
    alert(`✅ ${ticker} 开仓记录已保存`);
  });
}

// ── 统计更新 ─────────────────────────────────────────
function updateStats() {
  const signals   = DB.signals();
  const positions = DB.positions();
  const todaySigs = signals.filter(s=>s.time&&s.time.startsWith(today())).length;
  const activePosi= positions.filter(p=>!p.closed).length;
  const closed    = positions.filter(p=>p.closed);
  const winRate   = closed.length ? Math.round(closed.filter(p=>p.exit_type==='win').length/closed.length*100)+'%' : '--';
  document.getElementById('stat-signals').textContent  = todaySigs;
  document.getElementById('stat-positions').textContent= activePosi;
  document.getElementById('stat-winrate').textContent  = winRate;
}

// ── 初始化 ────────────────────────────────────────────
function init() {
  initTabs();
  initSignalFilters();
  initTradeForm();
  renderOverview();
  updateStats();
}
document.addEventListener('DOMContentLoaded', init);
