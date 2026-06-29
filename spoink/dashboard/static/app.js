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
const SRC_ICON = {
  slack: _svg('<path d="M5.6 2 4.2 14M11.8 2 10.4 14M2.4 5.6h11.2M1.9 10.4h11.2"/>'),
  linear: _svg('<rect x="2.4" y="2.4" width="11.2" height="11.2" rx="2.6"/><path d="M5.5 8.2 7.1 9.9 11 5.9"/>'),
  logfire: _svg('<rect x="2" y="2.9" width="12" height="10.2" rx="2"/><path d="M4.9 6.3 6.8 8 4.9 9.7M8.5 9.8H11"/>'),
  gauge: _svg('<path d="M2.7 11.4a5.3 5.3 0 1 1 10.6 0"/><path d="M8 11.4 11 7.7"/>'),
  github: _svg('<circle cx="4.3" cy="3.9" r="1.5"/><circle cx="4.3" cy="12.1" r="1.5"/><circle cx="11.7" cy="5.4" r="1.5"/><path d="M4.3 5.4v5.2M4.3 9.1c0-2.3.7-2.9 3.4-3.3"/>'),
};

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
        el("span", { className: "nm", textContent: o.label }),
        el("span", { className: "meta" }, [
          o.member ? el("span", { className: "mb", textContent: "Member" }) : "",
          o.private ? el("span", { className: "pv", textContent: "Private" }) : "",
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

function discoverSelect(field, s, p, loaders) {
  const sel = el("select", {}, el("option", { value: "", textContent: "Auto (most issues)" }));
  field.append(sel);
  const load = async () => {
    try {
      const key = `${s.id}:${p.discover}`;
      const opts = OPTCACHE[key] || (OPTCACHE[key] = (await api(`/api/sources/${s.id}/options/${p.discover}`)).options);
      for (const o of opts) sel.append(el("option", { value: o.value, textContent: o.label + (o.count != null ? ` (${o.count})` : "") }));
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
