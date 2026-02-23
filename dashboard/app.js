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
  if (tab==='weekly')    renderWeekly();
  if (tab==='settings')  renderSettings();
}

// ── Tab 1: 今日概览 ───────────────────────────────────
async function loadCoreHoldings() {
  // 从缓存或 JSON 文件获取核心持仓数据
  let snap = null;
  try {
    const cached = localStorage.getItem('core_holdings_cache');
    if (cached) {
      const obj = JSON.parse(cached);
      // 超过1小时才刷新（盘中数据变化快）
      if (Date.now() - obj._ts < 3600 * 1000) snap = obj;
    }
  } catch(e) {}

  if (!snap) {
    try {
      const res = await fetch('./core_holdings.json?_=' + Date.now());
      if (res.ok) {
        snap = await res.json();
        snap._ts = Date.now();
        localStorage.setItem('core_holdings_cache', JSON.stringify(snap));
      }
    } catch(e) {}
  }

  // 日历数据里找财报日期
  let earnMap = {};
  try {
    const calCached = localStorage.getItem('calendar_cache');
    if (calCached) {
      const cal = JSON.parse(calCached);
      (cal.core_earnings||[]).forEach(ev => { earnMap[ev.ticker] = ev.date; });
    }
  } catch(e) {}

  const cores = ['TSLA','GOOGL','NVDA','META'];
  cores.forEach(t => {
    const card = document.getElementById(`core-card-${t}`);
    if (!card) return;

    const d = snap?.tickers?.[t];
    const earnDate = earnMap[t];
    const earnLabel = earnDate ? `📋 财报 ${earnDate.slice(5)}` : '';

    if (!d) {
      card.innerHTML = `
        <div class="core-ticker">${t}</div>
        <div class="core-placeholder">数据加载中</div>
        ${earnLabel ? `<div class="core-earn">${earnLabel}</div>` : ''}`;
      return;
    }

    const isUp  = d.change_pct >= 0;
    const color = isUp ? 'var(--green)' : 'var(--red)';
    const arrow = isUp ? '▲' : '▼';
    const sign  = isUp ? '+' : '';

    // 距 52 周高点
    const offHtml = d.off_high
      ? `<div class="core-meta">距52W高 ${d.off_high > 0 ? '+' : ''}${d.off_high}%</div>`
      : '';

    card.innerHTML = `
      <div class="core-ticker-row">
        <span class="core-ticker">${t}</span>
        <span class="core-date">${d.date?.slice(5)||''}</span>
      </div>
      <div class="core-price-big" style="color:${color}">$${d.price}</div>
      <div class="core-change" style="color:${color}">${arrow} ${sign}${d.change_pct.toFixed(2)}%
        <span style="font-size:11px;opacity:.7">${sign}$${Math.abs(d.change).toFixed(2)}</span>
      </div>
      ${offHtml}
      ${earnLabel ? `<div class="core-earn">${earnLabel}</div>` : ''}`;
  });
}

async function loadMarketSnapshot() {
  // 从 data/daily/YYYY-MM-DD.json 加载今日市场数据
  const now = new Date();
  const dateStr = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
  // 尝试今天，若无则尝试昨天
  const dates = [dateStr];
  const prev = new Date(now); prev.setDate(now.getDate()-1);
  dates.push(`${prev.getFullYear()}-${String(prev.getMonth()+1).padStart(2,'0')}-${String(prev.getDate()).padStart(2,'0')}`);

  for (const d of dates) {
    try {
      const res = await fetch(`./data/daily/${d}.json?_=` + Date.now());
      if (!res.ok) continue;
      const data = await res.json();
      const mb = data.morning_brief || data.deep_analysis || {};
      if (!mb.indices) continue;

      const snap = document.getElementById('mkt-snapshot');
      snap.style.display = 'grid';

      // 指数
      const idxNames = {SPY:'标普500',QQQ:'纳斯达克',DIA:'道琼斯',IWM:'罗素2000'};
      document.getElementById('mkt-indices').innerHTML = Object.entries(mb.indices||{})
        .filter(([k])=>idxNames[k])
        .map(([k,v])=>`<div class="mkt-row">
          <span class="mkt-name">${idxNames[k]||k}</span>
          <span class="mkt-val ${v.change_pct>=0?'up':'dn'}">${v.change_pct>=0?'+':''}${v.change_pct.toFixed(2)}%</span>
        </div>`).join('');

      // 大宗商品
      const cmdNames = {'GC=F':'黄金','CL=F':'原油','SI=F':'白银','NG=F':'天然气'};
      document.getElementById('mkt-commodities').innerHTML = Object.entries(mb.commodities||{})
        .map(([k,v])=>`<div class="mkt-row">
          <span class="mkt-name">${cmdNames[k]||k}</span>
          <span class="mkt-val ${v.change_pct>=0?'up':'dn'}">${v.change_pct>=0?'+':''}${v.change_pct.toFixed(2)}%</span>
        </div>`).join('');

      // 板块 top3 + bottom3
      const secs = Object.entries(mb.sectors||{}).sort((a,b)=>b[1].change_pct-a[1].change_pct);
      const top3 = secs.slice(0,3), bot3 = secs.slice(-3);
      document.getElementById('mkt-sectors').innerHTML =
        [...top3.map(([k,v])=>`<div class="mkt-row">
          <span class="mkt-name">💪 ${v.name||k}</span>
          <span class="mkt-val up">+${v.change_pct.toFixed(2)}%</span></div>`),
         `<div style="font-size:11px;color:var(--muted);padding:3px 0;text-align:center">···</div>`,
         ...bot3.map(([k,v])=>`<div class="mkt-row">
          <span class="mkt-name">🩸 ${v.name||k}</span>
          <span class="mkt-val dn">${v.change_pct.toFixed(2)}%</span></div>`)
        ].join('');

      // 恐惧贪婪
      const fg = mb.fear_greed || {};
      document.getElementById('mkt-fg-emoji').textContent = fg.emoji || '😐';
      document.getElementById('mkt-fg-label').textContent = fg.label_zh || fg.label || '--';
      document.getElementById('mkt-fg-val').textContent = fg.value ? `${fg.value}/100 · 恐惧贪婪指数` : '恐惧贪婪指数';

      return; // 成功则返回
    } catch(e) {}
  }
}

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

  // 核心持仓卡片 — 先渲染占位，异步加载价格
  const cores = ['TSLA','GOOGL','NVDA','META'];
  document.getElementById('core-holdings').innerHTML = cores.map(t =>
    `<div class="core-card" id="core-card-${t}">
      <div class="core-ticker">${t}</div>
      <div class="core-price" style="color:var(--muted);font-size:14px">加载中...</div>
    </div>`
  ).join('');

  // 异步加载核心持仓价格数据
  loadCoreHoldings();

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

// ── PIN 系统 ────────────────────────────────────────────
let pinBuffer = '';
const PIN_KEY  = 'pos_pin_hash';
const POS_KEY  = 'private_positions';
const LOCK_KEY = 'pos_unlocked_until';
const PIN_LOCK_MINUTES = 30;

function hashPin(pin) {
  let h = 0;
  for (let i = 0; i < pin.length; i++) { h = ((h << 5) - h) + pin.charCodeAt(i); h |= 0; }
  return 'ph_' + Math.abs(h).toString(36) + '_' + pin.length;
}
function isPinSet() { return !!localStorage.getItem(PIN_KEY); }
function isUnlocked() { return Date.now() < parseInt(localStorage.getItem(LOCK_KEY)||'0'); }

window.pinInput = function(d) {
  if (pinBuffer.length >= 4) return;
  pinBuffer += d; updatePinDots();
  if (pinBuffer.length === 4) setTimeout(pinConfirm, 200);
};
window.pinClear = function() { pinBuffer = pinBuffer.slice(0,-1); updatePinDots(); };
function updatePinDots() {
  document.querySelectorAll('#pin-dots span').forEach((el,i) => el.classList.toggle('filled', i < pinBuffer.length));
}
window.pinConfirm = function() {
  if (!pinBuffer.length) return;
  const stored = localStorage.getItem(PIN_KEY);
  if (!stored) { document.getElementById('pin-msg').textContent='请先设置 PIN 码'; pinBuffer=''; updatePinDots(); return; }
  if (hashPin(pinBuffer) === stored) {
    localStorage.setItem(LOCK_KEY, Date.now() + PIN_LOCK_MINUTES*60*1000);
    showPositionsContent();
  } else {
    document.getElementById('pin-msg').textContent='❌ PIN 错误，请重试'; pinBuffer=''; updatePinDots();
  }
};
window.showPinSetup = function() {
  const pin1 = prompt('设置4位数字 PIN（首次设置）:');
  if (!pin1 || !/^\d{4}$/.test(pin1)) { alert('PIN 必须是4位数字'); return; }
  const pin2 = prompt('再次确认 PIN:');
  if (pin1 !== pin2) { alert('两次输入不一致'); return; }
  localStorage.setItem(PIN_KEY, hashPin(pin1));
  localStorage.setItem(LOCK_KEY, Date.now() + PIN_LOCK_MINUTES*60*1000);
  alert('✅ PIN 设置成功！');
  showPositionsContent();
};
window.lockPositions = function() {
  localStorage.removeItem(LOCK_KEY);
  document.getElementById('pos-content').style.display = 'none';
  document.getElementById('pos-lock-screen').style.display = 'flex';
  pinBuffer=''; updatePinDots();
};
function showPositionsContent() {
  document.getElementById('pos-lock-screen').style.display = 'none';
  document.getElementById('pos-content').style.display = 'block';
  renderPositionsTab();
}

// ── 持仓初始数据 ──────────────────────────────────────
const FUTU_POSITIONS_INIT = [
  {ticker:'TSLA',name:'特斯拉',          shares:32, cost:228.060,price:407.16,pnl:5731.20, pnlPct:78.53, type:'stock'},
  {ticker:'META',name:'Meta Platforms',  shares:15, cost:639.088,price:647.77,pnl:130.23,  pnlPct:1.36,  type:'stock'},
  {ticker:'CRWD',name:'CrowdStrike',     shares:22, cost:463.636,price:383.57,pnl:-1761.46,pnlPct:-17.27,type:'stock'},
  {ticker:'PANW',name:'Palo Alto Net.',  shares:56, cost:183.857,price:147.99,pnl:-2008.56,pnlPct:-19.51,type:'stock'},
  {ticker:'ORCL',name:'甲骨文',           shares:33, cost:186.333,price:146.11,pnl:-1327.37,pnlPct:-21.59,type:'stock'},
  {ticker:'RKLB',name:'Rocket Lab',      shares:65, cost:84.923, price:69.03, pnl:-1033.05,pnlPct:-18.71,type:'stock'},
  {ticker:'OKLO',name:'Oklo Inc',        shares:65, cost:85.108, price:62.10, pnl:-1495.50,pnlPct:-27.03,type:'stock'},
  {ticker:'SOUN',name:'SoundHound AI',   shares:450,cost:11.556, price:7.65,  pnl:-1757.50,pnlPct:-33.80,type:'stock'},
  {ticker:'SNOW',name:'Snowflake',       shares:20, cost:217.300,price:170.30,pnl:-940.00, pnlPct:-21.63,type:'stock'},
  {ticker:'ARM', name:'Arm Holdings',    shares:25, cost:120.000,price:123.35,pnl:83.75,   pnlPct:2.79,  type:'stock'},
  {ticker:'AMD', name:'美国超微公司',      shares:15, cost:194.533,price:197.14,pnl:39.10,   pnlPct:1.34,  type:'stock'},
  {ticker:'NNE', name:'NANO Nuclear',    shares:120,cost:30.000, price:24.15, pnl:-702.00, pnlPct:-19.50,type:'stock'},
  {ticker:'SOFI',name:'SoFi Technologies',shares:150,cost:24.693,price:18.66, pnl:-905.00, pnlPct:-24.43,type:'stock'},
  {ticker:'DXYZ',name:'Destiny Tech100', shares:100,cost:30.100, price:27.71, pnl:-239.00, pnlPct:-7.94, type:'stock'},
  {ticker:'ASTS',name:'AST SpaceMobile', shares:30, cost:97.000, price:78.81, pnl:-545.70, pnlPct:-18.75,type:'stock'},
  {ticker:'NBIS',name:'NEBIUS',          shares:15, cost:31.810, price:94.92, pnl:946.65,  pnlPct:198.40,type:'stock'},
  {ticker:'IONQ',name:'IonQ Inc',        shares:20, cost:45.000, price:31.25, pnl:-275.00, pnlPct:-30.56,type:'stock'},
  {ticker:'NFLX',name:'NFLX CALL 260320 85',shares:2,cost:4.200,price:1.29,  pnl:-582.00, pnlPct:-69.29,type:'options',expiry:'2026-03-20',strike:85},
];

function loadPrivatePositions() {
  const s = localStorage.getItem(POS_KEY);
  if (s) { try { return JSON.parse(s); } catch(e){} }
  localStorage.setItem(POS_KEY, JSON.stringify(FUTU_POSITIONS_INIT));
  return FUTU_POSITIONS_INIT;
}
function savePrivatePositions(p) { localStorage.setItem(POS_KEY, JSON.stringify(p)); }

window.syncPosFromYF = async function() {
  const btn = event.target; btn.textContent='⏳ 同步中...'; btn.disabled=true;
  try {
    const res = await fetch('./core_holdings.json?_='+Date.now());
    if (!res.ok) throw new Error();
    const snap = await res.json();
    const positions = loadPrivatePositions(); let updated=0;
    positions.forEach(p => {
      const yf = snap.tickers?.[p.ticker];
      if (yf?.price) {
        p.price  = yf.price;
        p.pnl    = Math.round((yf.price - p.cost)*p.shares*100)/100;
        p.pnlPct = Math.round((yf.price - p.cost)/p.cost*10000)/100;
        p.lastSync = yf.date; updated++;
      }
    });
    savePrivatePositions(positions); renderPositionsTab();
    btn.textContent=`✅ 已同步 ${updated} 只`;
  } catch(e) { btn.textContent='❌ 同步失败'; }
  setTimeout(()=>{ btn.textContent='🔄 刷新价格'; btn.disabled=false; }, 3000);
};

function renderPositionsTab() {
  const positions = loadPrivatePositions();
  const sortBy  = document.getElementById('pos-sort')?.value  || 'pnl_pct';
  const filterBy= document.getElementById('pos-filter')?.value|| 'all';
  let list = positions.filter(p => filterBy==='profit'?p.pnl>=0 : filterBy==='loss'?p.pnl<0 : true);
  list.sort((a,b) => sortBy==='pnl_pct'?b.pnlPct-a.pnlPct : sortBy==='pnl_abs'?b.pnl-a.pnl :
    sortBy==='market_val'?(b.price*b.shares)-(a.price*a.shares) : a.ticker.localeCompare(b.ticker));

  const totalPnl   = positions.reduce((s,p)=>s+p.pnl,0);
  const totalMktVal= positions.reduce((s,p)=>s+p.price*p.shares,0);
  const totalCost  = positions.reduce((s,p)=>s+p.cost*p.shares,0);
  const totalPnlPct= totalCost ? totalPnl/totalCost*100 : 0;
  const winCount   = positions.filter(p=>p.pnl>=0).length;
  const pnlColor   = totalPnl>=0 ? 'var(--green)' : 'var(--red)';

  document.getElementById('pos-summary').innerHTML = `
    <div class="pos-stat"><div class="pos-stat-val" style="color:${pnlColor}">${totalPnl>=0?'+':''}$${Math.abs(totalPnl).toFixed(0)}</div><div class="pos-stat-lbl">总盈亏</div></div>
    <div class="pos-stat"><div class="pos-stat-val" style="color:${pnlColor}">${totalPnlPct>=0?'+':''}${totalPnlPct.toFixed(2)}%</div><div class="pos-stat-lbl">综合盈亏率</div></div>
    <div class="pos-stat"><div class="pos-stat-val">$${totalMktVal.toFixed(0)}</div><div class="pos-stat-lbl">持仓市值</div></div>
    <div class="pos-stat"><div class="pos-stat-val">${positions.length} 只 · ${winCount}盈 ${positions.length-winCount}亏</div><div class="pos-stat-lbl">持仓数</div></div>`;

  const maxAbsPct = Math.max(...positions.map(p=>Math.abs(p.pnlPct)), 1);

  document.getElementById('pos-table').innerHTML = `
    <div class="pos-table-wrap"><table class="pos-table-el">
      <thead><tr><th>标的</th><th>现价</th><th>成本</th><th>数量</th><th>市值</th><th>盈亏额</th><th>盈亏%</th></tr></thead>
      <tbody>${list.map(p => {
        const isUp=p.pnl>=0, cls=isUp?'pos-pnl-up':'pos-pnl-dn', sign=isUp?'+':'';
        const barW=Math.round(Math.abs(p.pnlPct)/maxAbsPct*60), barC=isUp?'var(--green)':'var(--red)';
        return `<tr>
          <td><div class="pos-ticker-cell">
            <span class="pos-ticker-name">${p.ticker}</span>
            <span class="pos-ticker-sub">${p.name}</span>
            ${p.type==='options'?`<span class="pos-options-tag">期权 到期${p.expiry?.slice(5)||''}</span>`:''}
          </div></td>
          <td>$${p.price}</td>
          <td style="color:var(--muted)">$${p.cost}</td>
          <td>${p.shares}</td>
          <td>$${(p.price*p.shares).toFixed(0)}</td>
          <td class="${cls}">${sign}$${Math.abs(p.pnl).toFixed(2)}</td>
          <td><div class="pos-bar-wrap" style="justify-content:flex-end">
            <span class="${cls}">${sign}${p.pnlPct.toFixed(2)}%</span>
            <div class="pos-bar" style="width:${barW}px;background:${barC}"></div>
          </div></td></tr>`;
      }).join('')}</tbody>
    </table></div>`;
}

// ── Tab 3: 我的持仓 ───────────────────────────────────
function renderPositions() {
  // PIN 保护：检查是否已解锁
  if (isUnlocked()) {
    showPositionsContent();
  } else {
    document.getElementById('pos-lock-screen').style.display = 'flex';
    document.getElementById('pos-content').style.display = 'none';
  }
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

// ── Tab 5: 周末总结 ───────────────────────────────────
async function renderWeekly() {
  // 优先从 localStorage，其次从同域 JSON 文件加载
  let reports = DB.get('weekly_reports', []);
  if (!reports.length) {
    try {
      const res = await fetch('./weekly_reports.json?_=' + Date.now());
      if (res.ok) {
        reports = await res.json();
        DB.set('weekly_reports', reports);
      }
    } catch(e) {}
  }
  const list    = document.getElementById('weekly-list');
  const content = document.getElementById('weekly-content');

  if (!reports.length) {
    list.innerHTML = '<div style="font-size:13px;color:var(--muted)">暂无周报</div>';
    content.innerHTML = '<div class="empty-msg">每周一自动生成，也可手动导入</div>';
    return;
  }

  list.innerHTML = reports.map((r,i) => `
    <div class="weekly-item ${i===0?'active':''}" onclick="showWeekly(${i})" id="witem-${i}">
      <div style="font-weight:600;font-size:13px">${r.week_label||r.date}</div>
      <div style="font-size:11px;color:var(--muted);margin-top:2px">${r.generated_at?.slice(0,10)||''}</div>
    </div>`).join('');

  showWeekly(0);
}

window.showWeekly = function(idx) {
  const reports = DB.get('weekly_reports', []);
  const r = reports[idx];
  if (!r) return;

  document.querySelectorAll('.weekly-item').forEach((el,i) =>
    el.classList.toggle('active', i===idx));

  const content = document.getElementById('weekly-content');

  // 解析结构化周报字段
  const sectionHTML = (icon, title, items) => items&&items.length ? `
    <div class="wr-section">
      <div class="wr-section-title">${icon} ${title}</div>
      ${items.map(it=>`<div class="wr-item">${it}</div>`).join('')}
    </div>` : '';

  const events  = r.weekend_events || [];
  const outlook = r.market_outlook  || {};
  const stocks  = r.core_stocks     || [];
  const risks   = r.risks           || [];
  const strategy= r.strategy        || [];

  content.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <div>
        <div style="font-size:20px;font-weight:700">${r.week_label||r.date} 周末市场总结</div>
        <div style="font-size:12px;color:var(--muted);margin-top:4px">生成于 ${r.generated_at?.slice(0,16)||''}</div>
      </div>
      <div class="mood-badge-wr ${outlook.mood_class||''}">${outlook.mood_emoji||''} ${outlook.mood||'--'}</div>
    </div>

    ${sectionHTML('🗞️','周末重大事件', events.map(e=>`
      <div style="display:flex;gap:10px;align-items:flex-start">
        <span style="font-size:16px;flex-shrink:0">${e.emoji||'📌'}</span>
        <div>
          <div style="font-weight:600;font-size:14px">${e.title}</div>
          <div style="font-size:13px;color:var(--muted);margin-top:2px">${e.detail}</div>
          <div class="badge ${e.impact_class||'neutral'}" style="margin-top:4px">${e.impact}</div>
        </div>
      </div>`))}

    ${sectionHTML('📊','今晚开盘预判', outlook.items||[])}

    ${stocks.length?`
    <div class="wr-section">
      <div class="wr-section-title">⭐ 核心持仓判断</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px">
        ${stocks.map(s=>`
          <div style="background:#0f172a;border-radius:10px;padding:14px">
            <div style="font-size:18px;font-weight:800;margin-bottom:6px">${s.ticker}</div>
            <div class="badge ${s.outlook_class}" style="margin-bottom:8px">${s.outlook}</div>
            <div style="font-size:12px;color:var(--muted)">${s.reason}</div>
          </div>`).join('')}
      </div>
    </div>`:''}

    ${sectionHTML('🎯','本周操作策略', strategy)}
    ${sectionHTML('⚠️','主要风险提示', risks)}

    ${r.raw_content?`
    <details style="margin-top:20px">
      <summary style="cursor:pointer;color:var(--muted);font-size:13px">查看原文</summary>
      <pre style="margin-top:12px;white-space:pre-wrap;font-size:13px;color:#cbd5e1;line-height:1.6">${r.raw_content}</pre>
    </details>`:''}
  `;
};

// ── Tab 6: 设置 & 导入 ────────────────────────────────
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

// ── 经济日历 ──────────────────────────────────────────
let calCollapsed = false;
let earningsDetailsCache = {};  // 缓存财报详情

window.toggleCalendar = function() {
  calCollapsed = !calCollapsed;
  const banner = document.getElementById('cal-banner');
  const btn    = banner.querySelector('.cal-toggle');
  banner.classList.toggle('cal-hidden', calCollapsed);
  btn.textContent = calCollapsed ? '展开 ▼' : '收起 ▲';
};

// ── 财报弹窗 ──────────────────────────────────────────
window.showEarningsModal = async function(ticker) {
  const modal = document.getElementById('modal-earnings');
  const content = document.getElementById('earn-content');
  
  // 先显示加载中
  document.getElementById('earn-ticker').textContent = ticker;
  content.innerHTML = '<div class="empty-msg" style="padding:30px">加载财报数据中...</div>';
  modal.style.display = 'flex';

  // 先从缓存取
  let details = earningsDetailsCache[ticker];
  
  // 没缓存则从 calendar.json 里找
  if (!details) {
    try {
      const res = await fetch('./calendar.json?_=' + Date.now());
      const cal = await res.json();
      details = cal.earnings_details?.[ticker];
      if (details) earningsDetailsCache[ticker] = details;
    } catch(e) {}
  }

  if (!details || Object.keys(details).length === 0) {
    content.innerHTML = '<div class="empty-msg" style="padding:30px">暂无该股票财报数据</div>';
    return;
  }

  // 判断财报是否已发布（看是否有 actual 值）
  const hasActual = details.eps_actual !== undefined && details.eps_actual !== null;
  const timing = details.timing_zh || details.timing || '';
  const epsEst = details.eps_estimate ? `$${details.eps_estimate.toFixed(2)}` : '--';
  const revEst = details.rev_estimate ? `$${(details.rev_estimate/1e9).toFixed(2)}B` : '--';

  // 同比数据
  const epsGrowth = details.eps_growth_yoy ? `${(details.eps_growth_yoy*100).toFixed(1)}%` : '--';
  const revGrowth = details.rev_growth_yoy ? `${(details.rev_growth_yoy*100).toFixed(1)}%` : '--';

  let html = `
    <div style="margin-bottom:16px">
      <div style="font-size:13px;color:var(--muted);margin-bottom:6px">📅 财报日期</div>
      <div style="font-size:15px;font-weight:600">${details.earnings_date||'--'} ${timing ? `(${timing})` : ''}</div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:16px">
      <div style="background:#0f172a;border-radius:10px;padding:14px">
        <div style="font-size:12px;color:var(--muted);margin-bottom:6px">📊 EPS (每股收益)</div>
        <div style="font-size:18px;font-weight:700;margin-bottom:4px">${hasActual ? `$${details.eps_actual.toFixed(2)}` : epsEst}</div>
        ${hasActual ? `<div style="font-size:11px;color:var(--muted)">预期：${epsEst}</div>` : ''}
        ${hasActual ? `<div style="font-size:11px;color:${details.eps_surprise>=0?'var(--green)':'var(--red)'}">
          Gap: ${details.eps_surprise>=0?'+':''}${(details.eps_surprise*100).toFixed(1)}%
        </div>` : ''}
        ${!hasActual ? `<div style="font-size:11px;color:var(--muted)">范围：$${details.eps_low?.toFixed(2)||'--'} ~ $${details.eps_high?.toFixed(2)||'--'}</div>` : ''}
      </div>

      <div style="background:#0f172a;border-radius:10px;padding:14px">
        <div style="font-size:12px;color:var(--muted);margin-bottom:6px">💰 营收</div>
        <div style="font-size:18px;font-weight:700;margin-bottom:4px">${hasActual && details.rev_actual ? `$${(details.rev_actual/1e9).toFixed(2)}B` : revEst}</div>
        ${hasActual && details.rev_actual ? `<div style="font-size:11px;color:var(--muted)">预期：${revEst}</div>` : ''}
        ${!hasActual ? `<div style="font-size:11px;color:var(--muted)">范围：$${(details.rev_low/1e9)?.toFixed(2)||'--'}B ~ $${(details.rev_high/1e9)?.toFixed(2)||'--'}B</div>` : ''}
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:16px">
      <div style="background:#0f172a;border-radius:10px;padding:14px">
        <div style="font-size:12px;color:var(--muted);margin-bottom:6px">📈 EPS 同比增长</div>
        <div style="font-size:16px;font-weight:700">${epsGrowth}</div>
      </div>
      <div style="background:#0f172a;border-radius:10px;padding:14px">
        <div style="font-size:12px;color:var(--muted);margin-bottom:6px">📈 营收同比增长</div>
        <div style="font-size:16px;font-weight:700">${revGrowth}</div>
      </div>
    </div>

    ${details.company_name ? `<div style="font-size:12px;color:var(--muted);border-top:1px solid var(--border);padding-top:12px">
      🏢 ${details.company_name} · ${details.sector||''} · 市值 $${details.market_cap ? (details.market_cap/1e12).toFixed(2)+'T' : '--'}
    </div>` : ''}
  `;

  content.innerHTML = html;
};

window.closeEarningsModal = function() {
  document.getElementById('modal-earnings').style.display = 'none';
};

// 点击弹窗背景关闭
document.addEventListener('click', function(e) {
  const modal = document.getElementById('modal-earnings');
  if (e.target === modal) {
    modal.style.display = 'none';
  }
});

async function renderCalendar() {
  const daysEl = document.getElementById('cal-days');
  const subEl  = document.getElementById('cal-sub');

  // 先从 localStorage 取缓存
  let cal = null;
  try {
    const cached = localStorage.getItem('calendar_cache');
    if (cached) {
      const obj = JSON.parse(cached);
      // 超过6小时则重新加载
      if (Date.now() - obj._ts < 6 * 3600 * 1000) cal = obj;
    }
  } catch(e) {}

  // 没缓存则从 JSON 文件加载
  if (!cal) {
    try {
      const res = await fetch('./calendar.json?_=' + Date.now());
      if (res.ok) {
        cal = await res.json();
        cal._ts = Date.now();
        localStorage.setItem('calendar_cache', JSON.stringify(cal));
      }
    } catch(e) {}
  }

  if (!cal || !cal.by_date) {
    daysEl.innerHTML = '<div class="empty-msg" style="padding:16px">暂无日历数据</div>';
    subEl.textContent = '';
    return;
  }

  // 使用本地时间（北京时间），避免 UTC 偏移导致日期差1天
  const now = new Date();
  const todayStr = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
  // 取从今天起（含今天-1天容错）未来有事件的最多14天
  const yesterday = new Date(now); yesterday.setDate(now.getDate()-1);
  const yStr = `${yesterday.getFullYear()}-${String(yesterday.getMonth()+1).padStart(2,'0')}-${String(yesterday.getDate()).padStart(2,'0')}`;
  const dates = Object.keys(cal.by_date)
    .filter(d => d >= yStr)
    .sort()
    .slice(0, 14);

  subEl.textContent = `${cal.this_week?.length||0} 件本周事件 · 更新于 ${cal.generated_at?.slice(0,10)||'--'}`;

  if (!dates.length) {
    daysEl.innerHTML = '<div class="empty-msg" style="padding:16px">本周暂无重要事件</div>';
    return;
  }

  const dayNames = ['周日','周一','周二','周三','周四','周五','周六'];

  daysEl.innerHTML = dates.map(d => {
    const events = cal.by_date[d] || [];
    const dt    = new Date(d + 'T12:00:00');
    const isToday = d === todayStr;
    const dayLabel = `${d.slice(5)} ${dayNames[dt.getDay()]}`;

    const evHtml = events.map(ev => {
      const imp    = ev.importance >= 5 ? 'imp5' : ev.importance >= 4 ? 'imp4' : 'imp3';
      let tagHtml  = '';
      if (ev.tag === '⭐ 核心持仓')   tagHtml = '<span class="cal-ev-tag core">⭐ 持仓</span>';
      else if (ev.tag === '🎯 重点关注') tagHtml = '<span class="cal-ev-tag watch">🎯 关注</span>';
      else if (ev.category === 'fomc')  tagHtml = '<span class="cal-ev-tag fomc">🏦 FOMC</span>';
      else if (ev.category === 'macro') tagHtml = '<span class="cal-ev-tag macro">📊 宏观</span>';

      const noteText = ev.eps_range
        ? `预期EPS: ${ev.eps_range}`
        : (ev.note || '');

      const isEarnings = ev.category === 'earnings';
      const clickAttr  = isEarnings ? `onclick="showEarningsModal('${ev.ticker}')"` : '';
      const hoverClass = isEarnings ? 'earnings' : '';
      return `<div class="cal-ev ${imp} ${hoverClass}" ${clickAttr}>
        <div class="cal-ev-emoji">${ev.emoji||'📌'}</div>
        <div class="cal-ev-body">
          <div class="cal-ev-name">${ev.event}</div>
          ${noteText ? `<div class="cal-ev-note">${noteText}</div>` : ''}
          ${tagHtml}
        </div>
      </div>`;
    }).join('');

    return `<div class="cal-day${isToday?' today':''}">
      <div class="cal-day-label">
        <span>${dayLabel}</span>
        ${isToday ? '<span class="today-tag">今天</span>' : ''}
      </div>
      ${evHtml || '<div style="font-size:12px;color:var(--muted);padding:4px 0">无重要事件</div>'}
    </div>`;
  }).join('');
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
  renderCalendar();        // 首页日历
  loadMarketSnapshot();    // 市场快照
  updateStats();
}
document.addEventListener('DOMContentLoaded', init);
