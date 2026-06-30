// spoink dashboard — thin client of the control-plane API.
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const el = (t, props = {}, kids = []) => {
  const n = Object.assign(document.createElement(t), props);
  for (const k of [].concat(kids)) if (k != null && k !== "") n.append(k);
  return n;
};
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  const b = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(b.detail || b.error || r.statusText);
  return b;
};
let TT;
const toast = (m, err = false) => {
  const t = $("#toast"); t.textContent = m; t.className = "show" + (err ? " err" : "");
  clearTimeout(TT); TT = setTimeout(() => (t.className = ""), 4200);
};
const ago = (s) => {
  if (!s) return "—";
  const d = Math.max(0, Date.now() / 1000 - s);
  return d < 60 ? `${d | 0}s` : d < 3600 ? `${(d / 60) | 0}m` : d < 86400 ? `${(d / 3600) | 0}h` : `${(d / 86400) | 0}d`;
};
const cap = (s) => (s ? String(s).charAt(0).toUpperCase() + String(s).slice(1) : s);

// service identity — proper-cased names + icons, used wherever a service appears
const SVC_LABEL = { slack: "Slack", linear: "Linear", logfire: "Logfire", gauge: "Gauge", github: "GitHub" };
const svcLabel = (id) => SVC_LABEL[id] || cap(id);
const SRC_KIND = { slack: "Messages", linear: "Issues", logfire: "Logs", gauge: "Logs", github: "Code" };
const _svg = (p) => `<svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
// official brand marks (Simple Icons), filled, currentColor
const _bi = (d) => `<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="${d}"/></svg>`;
const SRC_ICON = {
  slack: _bi('M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zM18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zM17.688 8.834a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312zM15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52zM15.165 17.688a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z'),
  linear: _bi('M2.886 4.18A11.982 11.982 0 0 1 11.99 0C18.624 0 24 5.376 24 12.009c0 3.64-1.62 6.903-4.18 9.105L2.887 4.18ZM1.817 5.626l16.556 16.556c-.524.33-1.075.62-1.65.866L.951 7.277c.247-.575.537-1.126.866-1.65ZM.322 9.163l14.515 14.515c-.71.172-1.443.282-2.195.322L0 11.358a12 12 0 0 1 .322-2.195Zm-.17 4.862 9.823 9.824a12.02 12.02 0 0 1-9.824-9.824Z'),
  logfire: _bi('m23.826 17.316-4.23-5.866-6.847-9.496c-.348-.48-1.151-.48-1.497 0l-6.845 9.494-4.233 5.868a.925.925 0 0 0 .46 1.417l11.078 3.626h.002a.92.92 0 0 0 .572 0h.002l11.077-3.626c.28-.092.5-.31.59-.592a.916.916 0 0 0-.13-.825h.002ZM12.001 4.07l4.44 6.158-4.152-1.36c-.032-.01-.066-.008-.098-.016a.8.8 0 0 0-.096-.016c-.032-.004-.062-.016-.094-.016s-.062.012-.094.016a.74.74 0 0 0-.096.016c-.032.006-.066.006-.096.016L7.59 10.221l-.026.008 4.44-6.158h-.002Zm-6.273 8.7 4.834-1.583.516-.168v9.19L2.41 17.372l3.317-4.6Zm7.197 7.437V11.02l5.35 1.752 3.316 4.598-8.666 2.838Z'),
  github: _bi('M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12'),
  gauge: _svg('<path d="M2.7 11.4a5.3 5.3 0 1 1 10.6 0"/><path d="M8 11.4 11 7.7"/>'),
};
const LOCK = '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="3.3" y="7" width="9.4" height="6.4" rx="1.4"/><path d="M5.3 7V5.2a2.7 2.7 0 0 1 5.4 0V7"/></svg>';

// ---- timezone-aware date fields -----------------------------------------------
// Each datetime-local shows wall-clock in the selected zone; the value sent to the backend is
// always UTC ISO. Snapshot fields default to "now". The zone selector (sidebar) drives display.
const ZONES = [["UTC", "UTC"], ["America/Los_Angeles", "PT"], ["America/Denver", "MT"],
  ["America/Chicago", "CT"], ["America/New_York", "ET"], ["Europe/London", "London"],
  ["Europe/Berlin", "CET"], ["Asia/Kolkata", "IST"], ["Asia/Tokyo", "JST"]];
const _localZone = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { return "UTC"; } })();
if (_localZone && !ZONES.some((z) => z[0] === _localZone)) ZONES.unshift([_localZone, _localZone.split("/").pop().replace(/_/g, " ")]);
let TZ = ZONES.some((z) => z[0] === _localZone) ? _localZone : "UTC";
const ZONED = [];

const _parts = (inst, zone) => {
  const f = new Intl.DateTimeFormat("en-CA", { timeZone: zone, hour12: false,
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const p = {}; for (const x of f.formatToParts(inst)) p[x.type] = x.value;
  if (p.hour === "24") p.hour = "00";
  return p;
};
const _offset = (inst, zone) => {
  const p = _parts(inst, zone);
  return Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second) - inst.getTime();
};
const isoToWall = (iso, zone) => {
  if (!iso) return "";
  if (zone === "UTC") return iso.replace("Z", "").slice(0, 16);
  const p = _parts(new Date(iso), zone);
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
};
const wallToIso = (wall, zone) => {
  if (!wall) return "";
  if (zone === "UTC") return wall.slice(0, 16) + ":00Z";
  const naive = new Date(wall.slice(0, 16) + ":00Z");
  let inst = new Date(naive - _offset(naive, zone));
  inst = new Date(naive - _offset(inst, zone));
  return inst.toISOString().slice(0, 19) + "Z";
};
const nowIso = () => new Date().toISOString().slice(0, 19) + "Z";
function zonedInput(input, iso) {
  input._iso = iso || "";
  input.value = isoToWall(input._iso, TZ);
  const sync = () => { input._iso = wallToIso(input.value, TZ); };
  input.addEventListener("input", sync); input.addEventListener("change", sync);
  ZONED.push(input);
  return () => input._iso;
}
function setupTz() {
  const sel = $("#tzSelect");
  if (sel && !sel.options.length) {
    for (const [id, label] of ZONES) sel.append(el("option", { value: id, textContent: label }));
    sel.value = TZ;
    sel.onchange = () => { TZ = sel.value; for (const i of ZONED) i.value = isoToWall(i._iso, TZ); };
  }
}

let SOURCES = [], OPTCACHE = {}, TASKRUNS = [];

// ---------------------------------------------------------------- tabs
$$(".tabs button").forEach((b) => (b.onclick = () => {
  $$(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
  $$(".tab").forEach((s) => s.classList.toggle("active", s.id === "tab-" + b.dataset.tab));
  if (b.dataset.tab === "runs") loadRuns();
  if (b.dataset.tab === "tasks") loadTaskRuns();
  if (b.dataset.tab === "published") loadPublished();
}));

// ---------------------------------------------------------------- sources
async function loadSources() {
  const { sources } = await api("/api/sources");
  SOURCES = sources;
  setupTz();
  const wrap = $("#sourceList"); wrap.innerHTML = "";
  for (const s of sources) wrap.append(sourceCard(s));
}

function sourceCard(s) {
  const body = el("div", { className: "src-body" });
  const inputs = {}, loaders = [];
  const deps = () => { const o = {}; for (const [k, g] of Object.entries(inputs)) { const v = g(); if (typeof v === "string" && v) o[k] = v; } return o; };
  for (const p of s.params) {
    const f = el("div", { className: "field" });
    f.append(el("label", { textContent: p.label + (p.required ? " *" : "") }));
    if (p.discover && p.kind === "multiselect") inputs[p.name] = multiselect(f, s, p, loaders, deps);
    else if (p.discover && p.kind === "select") inputs[p.name] = discoverSelect(f, s, p, loaders);
    else if (p.discover && p.kind === "combo") inputs[p.name] = comboField(f, s, p, loaders);
    else if (p.kind === "datetime") {
      const i = el("input", { type: "datetime-local", step: "60" });
      f.append(i); inputs[p.name] = zonedInput(i, p.default === "now" ? nowIso() : (p.default || ""));
      if (p.default === "now") { const now = el("button", { className: "ghost sm nowbtn", textContent: "Now" }); now.onclick = () => { i._iso = nowIso(); i.value = isoToWall(i._iso, TZ); }; f.append(now); }
    } else {
      const i = el("input", { type: p.kind === "number" ? "number" : "text", value: p.default || "", placeholder: p.help || "" });
      f.append(i); inputs[p.name] = () => i.value;
    }
    if (p.help && p.kind !== "multiselect") f.append(el("div", { className: "help", textContent: p.help }));
    body.append(f);
  }
  const btn = el("button", { textContent: `Capture ${s.label}`, disabled: !s.has_key });
  btn.onclick = () => capture(s, inputs, btn);
  body.append(btn);
  if (s.note) body.prepend(el("div", { className: "src-note", textContent: s.note }));

  const key = el("span", { className: "key " + (s.has_key ? "ok" : "no") });
  key.append(el("i", { className: "tick", textContent: s.has_key ? "✓" : "✗" }), " " + s.env_key);
  const head = el("div", { className: "src-head" }, [
    el("span", { className: "chev", textContent: "›" }),
    el("span", { className: "src-icon", innerHTML: SRC_ICON[s.id] || "" }),
    el("span", { className: "src-name", textContent: s.label }),
    el("span", { className: "src-kind", textContent: SRC_KIND[s.id] || cap(s.kind) }),
    key,
  ]);
  const card = el("div", { className: "src" }, [head, body]);
  let loaded = false;
  head.onclick = () => {
    card.classList.toggle("open");
    if (card.classList.contains("open") && !loaded && s.has_key) { loaded = true; loaders.forEach((fn) => fn()); }
  };
  return card;
}

// discovery-backed multi-select (Slack channels, GitHub repos)
function multiselect(field, s, p, loaders, getDeps) {
  const chosen = new Set();
  const list = el("div", { className: "ms-list" }, el("div", { className: "ms-empty", textContent: "Loading…" }));
  const search = el("input", { placeholder: "Filter…" });
  const reload = el("button", { className: "ghost sm", textContent: "Reload" });
  const ms = el("div", { className: "ms" }, [el("div", { className: "ms-bar" }, [search, reload]), list]);
  const tally = el("div", { className: "chosen", textContent: "None selected" });
  field.append(ms, tally);

  let opts = [];
  const render = () => {
    const q = search.value.toLowerCase();
    list.innerHTML = "";
    const shown = opts.filter((o) => (o.label || "").toLowerCase().includes(q));
    if (!shown.length) { list.append(el("div", { className: "ms-empty", textContent: "No matches" })); return; }
    for (const o of shown) {
      const cb = el("input", { type: "checkbox", checked: chosen.has(o.value) });
      cb.onchange = () => { cb.checked ? chosen.add(o.value) : chosen.delete(o.value); tally.textContent = chosen.size ? `${chosen.size} selected` : "None selected"; };
      list.append(el("label", { className: "ms-item" }, [cb,
        o.private ? el("span", { className: "lock", title: "Private", innerHTML: LOCK }) : "",
        el("span", { className: "nm", textContent: o.label }),
        el("span", { className: "meta" }, [
          o.count != null ? el("span", { className: "ct", textContent: o.count }) : "",
        ])]));
    }
  };
  const load = async () => {
    list.innerHTML = ""; list.append(el("div", { className: "ms-empty", textContent: "Loading…" }));
    try {
      const q = new URLSearchParams(getDeps ? getDeps() : {}).toString();
      const key = `${s.id}:${p.discover}:${q}`;
      const resp = OPTCACHE[key] || (OPTCACHE[key] = await api(`/api/sources/${s.id}/options/${p.discover}${q ? "?" + q : ""}`));
      opts = resp.options || [];
      if (!opts.length && resp.note) { list.innerHTML = ""; list.append(el("div", { className: "ms-empty", textContent: resp.note })); return; }
      render();
    } catch (e) { list.innerHTML = ""; list.append(el("div", { className: "ms-empty", textContent: "Load failed: " + e.message })); }
  };
  search.oninput = render;
  reload.onclick = () => { Object.keys(OPTCACHE).filter((k) => k.startsWith(`${s.id}:${p.discover}:`)).forEach((k) => delete OPTCACHE[k]); opts = []; load(); };
  loaders.push(() => { if (!opts.length) load(); });
  return () => [...chosen];
}

function comboField(field, s, p, loaders) {
  // free-text input backed by a <datalist> of suggestions (e.g. your GitHub orgs)
  const listId = `dl-${s.id}-${p.name}`;
  const input = el("input", { type: "text", value: p.default || "", placeholder: p.help || "",
                              autocomplete: "off" });
  input.setAttribute("list", listId);
  const dl = el("datalist", { id: listId });
  field.append(input, dl);
  const load = async () => {
    try {
      const key = `${s.id}:${p.discover}`;
      const opts = OPTCACHE[key] || (OPTCACHE[key] = (await api(`/api/sources/${s.id}/options/${p.discover}`)).options);
      dl.innerHTML = "";
      for (const o of opts) dl.append(el("option", { value: o.value, label: o.note || "" }));
    } catch (e) { /* suggestions are best-effort; typing still works */ }
  };
  loaders.push(() => { if (!dl.children.length) load(); });
  return () => input.value.trim();
}

function discoverSelect(field, s, p, loaders) {
  const sel = el("select", {}, el("option", { value: "", textContent: "Auto (most issues)" }));
  field.append(sel);
  const load = async () => {
    try {
      const key = `${s.id}:${p.discover}`;
      const opts = OPTCACHE[key] || (OPTCACHE[key] = (await api(`/api/sources/${s.id}/options/${p.discover}`)).options);
      for (const o of opts) sel.append(el("option", { value: o.value, textContent: o.label + (o.count != null ? `  ·  ${o.count} issues` : "") }));
    } catch (e) { toast("Options: " + e.message, true); }
  };
  loaders.push(() => { if (sel.options.length < 2) load(); });
  return () => sel.value;
}

async function capture(s, inputs, btn) {
  const params = {};
  for (const [k, get] of Object.entries(inputs)) params[k] = get();
  btn.disabled = true;
  try {
    await api("/api/capture", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: s.id, params }) });
    toast(`${s.label} capture queued`);
    $$(".tabs button").find((b) => b.dataset.tab === "runs").click();
  } catch (e) { toast(`Capture failed: ${e.message}`, true); }
  finally { btn.disabled = !s.has_key; }
}

// ---------------------------------------------------------------- runs
async function loadRuns() {
  const { runs } = await api("/api/runs");
  const running = runs.filter((r) => r.status === "running" || r.status === "queued");
  const done = runs.filter((r) => r.status === "done" || r.status === "error");
  paint($("#running"), $("#runningEmpty"), running);
  paint($("#completed"), $("#completedEmpty"), done);
  const badge = $("#runBadge");
  badge.hidden = !running.length; badge.textContent = running.length;
  if (running.length) clearTimeout(loadRuns._t), (loadRuns._t = setTimeout(loadRuns, 2000));
}
function paint(host, empty, list) {
  host.innerHTML = ""; empty.style.display = list.length ? "none" : "block";
  for (const j of list) host.append(runRow(j));
}
function statusPill(j) {
  if (j.status === "running") return el("span", { className: "pill running" }, [el("span", { className: "spin" }), "Running"]);
  return el("span", { className: "pill " + j.status, textContent: cap(j.status) });
}
function runRow(j) {
  const running = j.status === "running" || j.status === "queued";
  const top = el("div", { className: "run-top" }, [
    el("span", { className: "run-icon", innerHTML: SRC_ICON[j.source] || "" }),
    el("span", { className: "run-name", textContent: j.name || (svcLabel(j.source) + " snapshot") }),
    statusPill(j),
    el("span", { className: "run-when", textContent: running ? "" : ago(j.created) + " ago" }),
    menu(j),
  ]);
  const body = el("div", { className: "run-body" });
  if (running) body.append(progress(j));
  else if (j.status === "error") body.append(el("div", { className: "run-err", textContent: j.error || "failed" }));
  else body.append(meta(j.metadata || {}));
  if (j.published && j.published.status) body.append(pubBanner(j.published));
  return el("div", { className: "run" + (running ? " running" : "") }, [top, body]);
}
function progress(j) {
  const elapsed = j.started ? Math.max(0, Date.now() / 1000 - j.started) : 0;
  const eta = j.eta || null;
  const pct = eta ? Math.min(98, (elapsed / eta) * 100) : null;
  const fill = el("div", { className: "pfill" + (pct == null ? " indet" : ""), style: `width:${pct == null ? 35 : pct}%` });
  const txt = j.status === "queued" ? "Queued…"
    : `${elapsed | 0}s elapsed` + (eta ? ` · ~${Math.round(eta)}s typical` : "");
  return el("div", { className: "prog" }, [el("div", { className: "pbar" }, fill), el("div", { className: "pmeta", textContent: txt })]);
}
function meta(md) {
  const grid = el("div", { className: "kv" });
  for (const [k, v] of Object.entries(md)) {
    const long = String(v).length > 60;
    grid.append(el("div", { className: "kv-row" + (long ? " wide" : "") }, [
      el("span", { className: "kv-k", textContent: cap(k) }),
      el("span", { className: "kv-v", textContent: String(v), title: String(v) }),
    ]));
  }
  return grid;
}
function pubBanner(p) {
  const cls = p.status === "done" ? "ok" : p.status === "error" ? "err" : "busy";
  const txt = p.status === "done" ? "Published · " + p.image
    : p.status === "error" ? "Publish failed: " + (p.error || "") : "Publishing…";
  return el("div", { className: "pub-banner " + cls, textContent: txt });
}

// dropdown menu (⋮) — Rename / Publish / Delete
function menu(j) {
  const dd = el("div", { className: "menu-dd", hidden: true });
  const item = (label, fn, cls = "") => { const b = el("button", { className: "menu-it " + cls, textContent: label }); b.onclick = (e) => { e.stopPropagation(); closeMenus(); fn(); }; return b; };
  dd.append(item("Rename", () => renameRun(j)));
  if (j.status === "done") {
    const src = SOURCES.find((s) => s.id === j.source) || {};
    if (src.publishable) dd.append(item("Publish", () => openPublish(j)));
    dd.append(item("Copy location", () => { navigator.clipboard?.writeText((j.metadata || {}).location || ""); toast("Path copied"); }));
  }
  dd.append(item("Delete", () => deleteRun(j), "danger"));
  const btn = el("button", { className: "menu-btn", textContent: "⋮", title: "Actions" });
  btn.onclick = (e) => { e.stopPropagation(); const open = !dd.hidden; closeMenus(); dd.hidden = open; };
  return el("div", { className: "menu" }, [btn, dd]);
}
function closeMenus() { $$(".menu-dd").forEach((d) => (d.hidden = true)); }
document.addEventListener("click", closeMenus);

async function renameRun(j) {
  const name = prompt("Rename run", j.name || svcLabel(j.source));
  if (name == null) return;
  try { await api(`/api/runs/${j.id}/rename`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) }); toast("Renamed"); loadRuns(); }
  catch (e) { toast(e.message, true); }
}
async function deleteRun(j) {
  if (!confirm(`Delete "${j.name || svcLabel(j.source)}"?\nThis removes the captured data on disk.`)) return;
  try { await api(`/api/runs/${j.id}`, { method: "DELETE" }); toast("Deleted"); loadRuns(); }
  catch (e) { toast(e.message, true); }
}

// ---------------------------------------------------------------- publish
let PUBJOB = null;
async function openPublish(j) {
  PUBJOB = j;
  const m = $("#publishModal"); m.hidden = false;
  const st = $("#pubStatus"); st.textContent = ""; st.className = "pub-status";
  $("#pubMeta").innerHTML = ""; $("#pubImage").value = ""; $("#pubGo").disabled = true;
  try {
    const s = await api(`/api/runs/${j.id}/publish/suggest`);
    $("#pubImage").value = s.image;
    $("#pubMeta").append(meta(s.metadata || {}));
    $("#pubGo").disabled = !s.publishable;
    if (!s.publishable) { st.textContent = "This source isn't bakeable into a single image."; st.className = "pub-status err"; }
  } catch (e) { toast(e.message, true); }
}
$("#pubClose").onclick = () => ($("#publishModal").hidden = true);
$("#publishModal").onclick = (e) => { if (e.target.id === "publishModal") e.target.hidden = true; };
$("#pubGo").onclick = async () => {
  const image = $("#pubImage").value.trim(); if (!image || !PUBJOB) return;
  const st = $("#pubStatus"); $("#pubGo").disabled = true; st.textContent = "Baking + pushing…"; st.className = "pub-status busy";
  try {
    await api(`/api/runs/${PUBJOB.id}/publish`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ image }) });
    pollPublish(PUBJOB.id);
  } catch (e) { st.textContent = e.message; st.className = "pub-status err"; $("#pubGo").disabled = false; }
};
async function pollPublish(id) {
  const d = await api(`/api/runs/${id}`); const p = d.published || {}; const st = $("#pubStatus");
  if (p.status === "publishing") { st.textContent = "Baking + pushing…"; st.className = "pub-status busy"; setTimeout(() => pollPublish(id), 3000); return; }
  if (p.status === "done") { st.textContent = "Published ✓  " + p.image; st.className = "pub-status ok"; toast("Published to GHCR"); loadPublished(); }
  else if (p.status === "error") { st.textContent = "Failed: " + (p.error || ""); st.className = "pub-status err"; }
  $("#pubGo").disabled = false;
}

// ---------------------------------------------------------------- published
async function loadPublished() {
  const { published } = await api("/api/published");
  const host = $("#publishedList"); host.innerHTML = "";
  $("#publishedEmpty").style.display = published.length ? "none" : "block";
  const groups = {};
  for (const p of published) (groups[p.source] = groups[p.source] || []).push(p);
  for (const [src, items] of Object.entries(groups)) {
    host.append(el("div", { className: "pub-grp" }, [
      el("div", { className: "pub-grp-h" }, [el("span", { className: "run-icon", innerHTML: SRC_ICON[src] || "" }), el("span", { textContent: svcLabel(src) })]),
      ...items.map(pubRow),
    ]));
  }
}
function pubRow(p) {
  const copy = el("button", { className: "ghost sm", textContent: "Copy" });
  copy.onclick = () => { navigator.clipboard?.writeText(p.image); toast("Image ref copied"); };
  return el("div", { className: "pub-row" }, [
    el("span", { className: "pub-img", textContent: p.image, title: p.digest || "" }),
    el("span", { className: "pub-when", textContent: p.pushed_at || "" }),
    copy,
  ]);
}
$("#refreshPub").onclick = loadPublished;

// ---------------------------------------------------------------- task creator
async function loadTaskRuns() {
  const { runs } = await api("/api/runs");
  TASKRUNS = runs.filter((r) => r.status === "done");
  const host = $("#taskRuns"); host.innerHTML = "";
  if (!TASKRUNS.length) { host.append(el("p", { className: "muted sm", textContent: "No completed runs to bundle yet." })); return; }
  for (const j of TASKRUNS) {
    const cb = el("input", { type: "checkbox", value: j.id });
    host.append(el("label", {}, [cb,
      el("span", { className: "run-icon", innerHTML: SRC_ICON[j.source] || "" }),
      el("span", { textContent: j.name || svcLabel(j.source) }),
      el("span", { className: "ct muted sm", style: "margin-left:auto", textContent: (j.metadata || {})["as of"] || "" })]));
  }
}
$("#genPlan").onclick = async () => {
  const ids = $$("#taskRuns input:checked").map((c) => c.value);
  if (!ids.length) return toast("Pick at least one run", true);
  const firstAsOf = (TASKRUNS.find((r) => ids.includes(r.id))?.metadata || {})["as of"] || nowIso();
  try {
    const r = await api("/api/tasks/spec", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_ids: ids,
        name: ($("#anchorRepo").value.split("/").pop() || "incident") + "/new-task",
        kind: "observability", incident_t: firstAsOf,
        anchor_repo: $("#anchorRepo").value, anchor_commit: $("#anchorSha").value, resolution_pr: $("#anchorPr").value,
      }),
    });
    const o = $("#planOut"); o.hidden = false; o.innerHTML = "";
    const specText = JSON.stringify(r.spec, null, 2);
    const copy = el("button", { className: "ghost sm", textContent: "Copy" });
    copy.onclick = () => { navigator.clipboard?.writeText(specText); toast("spec.json copied"); };
    o.append(
      el("div", { className: "plan-head" }, [el("span", { className: "plan-title", textContent: "spec.json" }), copy]),
      el("pre", { className: "plan-pre", textContent: specText }),
      el("div", { className: "grp", textContent: "To finish before generating" }),
      el("ul", { className: "plan-todos" }, (r.todos || []).map((t) => el("li", { textContent: t }))),
      el("div", { className: "plan-cmd", textContent: "python -m spoink.pipeline spec.json --out generated-tasks/" }),
    );
  } catch (e) { toast(e.message, true); }
};

$("#refresh").onclick = loadRuns;
loadSources().then(loadRuns).catch((e) => toast(e.message, true));
