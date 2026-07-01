// Parity dashboard — loads per-clone manifests and renders the 4 required panels per demo.
const $ = (s, r = document) => r.querySelector(s);
const el = (t, cls, html) => { const e = document.createElement(t); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const esc = s => String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

let INDEX = null, CACHE = {};

async function boot() {
  INDEX = await (await fetch('data/index.json')).json();
  $('#brand-sub').textContent = INDEX.subtitle || '';
  const nav = $('#nav');
  INDEX.clones.forEach((c, i) => {
    const b = el('button');
    b.innerHTML = `<span class="dot" style="background:${c.accent || '#6ea8fe'}"></span>${c.product}<span class="vb ${c.verdict}">${c.verdict}</span>`;
    b.onclick = () => select(i, b);
    nav.appendChild(b);
    c._btn = b;
  });
  if (INDEX.clones.length) select(0, INDEX.clones[0]._btn);
}

async function select(i, btn) {
  document.querySelectorAll('.nav button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const c = INDEX.clones[i];
  if (!CACHE[c.file]) CACHE[c.file] = await (await fetch('data/' + c.file)).json();
  renderClone(CACHE[c.file], c);
}

function renderClone(m, c) {
  const main = $('#main'); main.innerHTML = '';
  const rs = m.real_service || {};
  const head = el('div', 'clone-head');
  head.innerHTML = `
    <h1>${esc(m.product)} <span class="pill ${c.verdict}">${c.verdict} parity</span></h1>
    <div class="meta">
      <span>clone: <code>${esc(m.clone)}</code></span>
      <span>real service: <a href="${rs.reference}" target="_blank">${esc(rs.name || '')} ↗</a></span>
      <span>surfaces: <code>${esc(m.surfaces?.cli || '')}</code> CLI · <code>${esc(m.surfaces?.mcp || '')}</code> MCP</span>
      <span>seed: <code>${esc(m.seed_file || '')}</code></span>
    </div>
    ${m.parity?.note ? `<div class="parity-note">✔ ${esc(m.parity.note)}</div>` : ''}`;
  main.appendChild(head);
  m.demos.forEach(d => main.appendChild(renderDemo(d)));
  main.appendChild(el('div', 'foot', `Seed data loaded in-process from <code>${esc(m.seed_file)}</code> and served through the clone — the CLONE column is real captured output, verifying the seed format is accepted. REAL column is a golden sample from the linked docs.`));
}

function renderDemo(d) {
  const card = el('div', 'demo');
  card.appendChild(el('div', 'demo-head',
    `<span class="method ${d.method}">${d.method}</span><span class="t">${esc(d.title)}</span><span class="cap">${esc(d.capability || '')}</span>`));

  const grid = el('div', 'grid');
  // Panel 1 — seed data + real-product UI render
  grid.appendChild(cell('Seed data → how the real product shows it', 1,
    `<div class="label">Seed slice</div>${jsonBlock(d.seed_excerpt)}<div class="label">Rendered like the real UI</div>${renderMock(d.ui)}`));
  // Panel 2 — the agent's CLI/MCP call
  grid.appendChild(cell('What an agent runs (CLI / MCP)', 2, agentBlock(d.agent)));
  // Panel 3 — the real endpoint it maps to
  grid.appendChild(cell('Maps to · real service', 3, mappingBlock(d.real_mapping)));
  // Panel 4 — output: GET comparison, POST change
  grid.appendChild(cell(d.method === 'POST' ? 'Effect · the write reflected' : 'Output · real vs clone', 4,
    d.method === 'POST' ? changeBlock(d) : compareBlock(d.real_output, d.clone_output)));
  card.appendChild(grid);
  return card;
}

function cell(title, n, html) {
  const cls = (n === 4) ? 'cell full' : 'cell';
  return el('div', cls, `<h4><span class="n">${n}</span>${esc(title)}</h4>${html}`);
}

// ---------- code / json ----------
function jsonBlock(obj) { return `<pre class="code">${hlJson(obj)}</pre>`; }
function hlJson(obj) {
  const j = JSON.stringify(obj, null, 2);
  return esc(j)
    .replace(/(&quot;[^&]*?&quot;)(\s*:)/g, '<span class="tok-key">$1</span>$2')
    .replace(/:\s(&quot;.*?&quot;)/g, ': <span class="tok-str">$1</span>')
    .replace(/:\s(-?\d+\.?\d*)/g, ': <span class="tok-num">$1</span>')
    .replace(/:\s(true|false)/g, ': <span class="tok-bool">$1</span>')
    .replace(/:\s(null)/g, ': <span class="tok-null">$1</span>');
}
function agentBlock(a) {
  if (!a) return '';
  let h = '';
  if (a.cli) h += `<div class="label">CLI</div><pre class="code wrap"><span class="cli-prompt">$ </span><span class="cli-cmd">${esc(a.cli)}</span></pre>`;
  if (a.mcp) h += `<div class="label">MCP tool call</div><pre class="code">${hlJson(a.mcp)}</pre>`;
  return h;
}
function mappingBlock(r) {
  if (!r) return '';
  let h = '';
  if (r.api) h += `<div class="label">HTTP API</div><pre class="code">${esc(r.api)}</pre>`;
  if (r.cli) h += `<div class="label">real CLI</div><pre class="code">${esc(r.cli)}</pre>`;
  if (r.mcp) h += `<div class="label">real MCP</div><pre class="code">${esc(r.mcp)}</pre>`;
  if (r.doc) h += `<div style="margin-top:10px"><a href="${r.doc}" target="_blank">Reference docs ↗</a></div>`;
  return h;
}

// ---------- parity comparison (GET) ----------
function compareBlock(real, clone) {
  const check = parityCheck(real, clone);
  return `${check.summaryHtml}<div class="parity-check">${check.chips}</div>
    <div class="cmp">
      <div class="side real"><h5></h5>${jsonBlock(real)}</div>
      <div class="side clone"><h5></h5>${jsonBlock(clone)}</div>
    </div>`;
}
// Parity = same response SHAPE (field paths + types). Values differ (the REAL column is a
// golden doc sample), so we compare structure recursively, not literal values.
function typeOf(v) { return v === null ? 'null' : Array.isArray(v) ? 'array' : typeof v; }
function shapePaths(v, prefix, out, depth) {
  out = out || {}; depth = depth || 0;
  const t = typeOf(v);
  if (prefix) out[prefix] = t;
  if (depth > 5) return out;
  if (t === 'array') { if (v.length) shapePaths(v[0], prefix + '[]', out, depth + 1); }
  else if (t === 'object') { for (const k of Object.keys(v)) shapePaths(v[k], prefix ? prefix + '.' + k : k, out, depth + 1); }
  return out;
}
function parityCheck(real, clone) {
  const rp = shapePaths(real, ''), cp = shapePaths(clone, '');
  const all = [...new Set([...Object.keys(rp), ...Object.keys(cp)])].filter(Boolean).sort();
  let match = 0, shared = 0;
  const chipArr = all.map(p => {
    const inR = p in rp, inC = p in cp;
    const label = esc(p.replace(/\[\]/g, '[ ]'));
    if (inR && inC) {
      shared++;
      const same = rp[p] === cp[p];
      if (same) match++;
      return `<span class="pc ${same ? 'match' : 'diff'}" title="${rp[p]} vs ${cp[p]}">${same ? '✓' : '≈'} ${label}</span>`;
    }
    return `<span class="pc only">${inC ? '＋clone' : '＋real'} ${label}</span>`;
  });
  const shown = chipArr.slice(0, 18).join('') + (chipArr.length > 18 ? `<span class="pc" style="color:var(--dim2)">+${chipArr.length - 18} more</span>` : '');
  const pct = shared ? Math.round(100 * match / shared) : 100;
  const cloneOnly = all.filter(p => !(p in rp)).length;
  const summaryHtml = `<div class="summary">Response-shape parity: <b class="ok">${match}/${shared} shared field paths identical in type</b> (${pct}%)${cloneOnly ? ` · ${cloneOnly} clone-only field${cloneOnly > 1 ? 's' : ''}` : ''}. ✓ same shape · ≈ type differs · ＋ one-side-only.</div>`;
  return { chips: shown, summaryHtml };
}

// ---------- change reflection (POST) ----------
function changeBlock(d) {
  const c = d.change || { before: d.ui?.before, after: d.ui?.after, new_id: d.ui?.new_id };
  const before = c.before || [], after = c.after || [], newId = c.new_id;
  const rows = (arr, hiId) => (arr.length ? arr : []).map(x => {
    const isNew = hiId != null && (x.id === hiId);
    const tags = (x.tags || []).map(t => `<span class="tg">${esc(t)}</span>`).join('');
    return `<div class="tl-item ${isNew ? 'new' : ''}">${esc(x.text ?? x.title ?? JSON.stringify(x))}${tags}${isNew ? '<span class="tl-new-badge">NEW ✓ written &amp; read back</span>' : ''}</div>`;
  }).join('') || '<div class="tl-item" style="color:var(--dim2)">(empty)</div>';
  const cmp = parityCheck(d.real_output, d.clone_output);
  return `<div class="cmp">
      <div class="side"><div class="label">Before the write (${before.length})</div><div class="mock"><div class="mock-body">${rows(before, null)}</div></div></div>
      <div class="side"><div class="label">After the agent's POST (${after.length}) — new row highlighted</div><div class="mock"><div class="mock-body">${rows(after, newId)}</div></div></div>
    </div>
    <div class="label" style="margin-top:14px">The clone's response to the write · vs the real API's shape</div>
    ${cmp.summaryHtml}<div class="parity-check">${cmp.chips}</div>
    <div class="cmp">
      <div class="side real"><h5></h5>${jsonBlock(d.real_output)}</div>
      <div class="side clone"><h5></h5>${jsonBlock(d.clone_output)}</div>
    </div>`;
}

// ---------- UI mock renderers ----------
function renderMock(ui) {
  if (!ui) return '';
  const bar = `<div class="mock-bar">◷ ${esc(ui.title || '')}</div>`;
  let body = '';
  switch (ui.type) {
    case 'list': body = (ui.rows || []).map(r =>
      `<div class="ui-row"><span class="ic">${r.icon || '•'}</span><span class="tt">${esc(r.title || '')}</span><span class="ss">${esc(r.sub || '')}</span><span class="ui-tags">${(r.tags || []).filter(Boolean).map(t => `<span class="ui-tag">${esc(t)}</span>`).join('')}</span></div>`).join(''); break;
    case 'chart': body = chartSvg(ui.series || []); break;
    case 'timeline': body = (ui.after || ui.before || []).map(a =>
      `<div class="tl-item ${a.id === ui.new_id ? 'new' : ''}">${esc(a.text || '')} ${(a.tags || []).map(t => `<span class="tg">${esc(t)}</span>`).join('')}${a.id === ui.new_id ? '<span class="tl-new-badge">NEW</span>' : ''}</div>`).join(''); break;
    case 'chat': body = (ui.messages || []).map(msg =>
      `<div class="chat-msg"><div class="chat-av" style="background:${msg.color || '#3a4a63'}">${esc((msg.user || '?')[0].toUpperCase())}</div><div class="chat-body"><div class="who">${esc(msg.user || '')}<span class="ts">${esc(msg.ts || '')}</span></div><div class="txt">${esc(msg.text || '')}</div></div></div>`).join(''); break;
    case 'doc': body = `<div class="doc"><h3>${esc(ui.doc_title || '')}</h3>${(ui.blocks || []).map(b => `<div class="blk ${b.type || ''}">${esc(b.text || '')}</div>`).join('')}</div>`; break;
    case 'canvas': body = `<div class="canvas">${(ui.nodes || []).map(n => `<div class="node-box ${n.type || ''}" style="left:${n.x}px;top:${n.y}px;width:${n.w}px;height:${n.h}px">${esc(n.name || '')}</div>`).join('')}</div>`; break;
    case 'table': body = tableHtml(ui.columns || [], ui.rows || []); break;
    default: body = jsonBlock(ui.data || {});
  }
  return `<div class="mock">${bar}<div class="mock-body">${body}</div></div>`;
}
function chartSvg(series) {
  const W = 460, H = 150, pad = 24;
  const colors = ['#6ea8fe', '#4ec9a5', '#e0a458', '#c586c0', '#e06c75'];
  let allPts = series.flatMap(s => s.points);
  if (!allPts.length) return '<div style="color:var(--dim2);padding:20px">no series</div>';
  const xs = allPts.map(p => p[0]), ys = allPts.map(p => p[1]);
  const xmin = Math.min(...xs), xmax = Math.max(...xs) || xmin + 1, ymax = Math.max(...ys, 1);
  const sx = t => pad + (W - 2 * pad) * (xmax === xmin ? .5 : (t - xmin) / (xmax - xmin));
  const sy = v => H - pad - (H - 2 * pad) * (v / ymax);
  const paths = series.map((s, i) => {
    const pts = s.points.slice().sort((a, b) => a[0] - b[0]);
    const dot = pts.length === 1;
    const d = pts.map((p, j) => `${j ? 'L' : 'M'}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join(' ');
    const marks = pts.map(p => `<circle cx="${sx(p[0]).toFixed(1)}" cy="${sy(p[1]).toFixed(1)}" r="${dot ? 4 : 2.5}" fill="${colors[i % 5]}"/>`).join('');
    return `<path d="${d}" fill="none" stroke="${colors[i % 5]}" stroke-width="1.6"/>${marks}`;
  }).join('');
  const legend = series.map((s, i) => `<span><i style="background:${colors[i % 5]}"></i>${esc(s.name)}</span>`).join('');
  return `<div class="chart"><svg viewBox="0 0 ${W} ${H}"><line x1="${pad}" y1="${H - pad}" x2="${W - pad}" y2="${H - pad}" stroke="#262d3d"/><line x1="${pad}" y1="${pad}" x2="${pad}" y2="${H - pad}" stroke="#262d3d"/>${paths}</svg><div class="legend">${legend}</div></div>`;
}
function tableHtml(cols, rows) {
  const head = cols.map(c => `<th>${esc(c)}</th>`).join('');
  const body = rows.map(r => `<tr>${cols.map((c, i) => {
    const v = r[c] ?? r[i] ?? '';
    if (c.toLowerCase() === 'level' || c.toLowerCase() === 'severity') return `<td><span class="sev ${esc(String(v).toLowerCase())}">${esc(v)}</span></td>`;
    return `<td class="${i === 0 ? 'hi' : ''}">${esc(v)}</td>`;
  }).join('')}</tr>`).join('');
  return `<table class="tbl"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

boot();
