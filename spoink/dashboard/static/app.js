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
// datetime-local <-> ISO-Z, treating the picker value as UTC wall-clock (no tz math, predictable).
const isoToInput = (iso) => (iso || "").replace("Z", "").slice(0, 16);
const inputToIso = (v) => (v ? v.slice(0, 16) + ":00Z" : "");

let SOURCES = [], DEFAULT_T = "", OPTCACHE = {};
const globalIso = () => inputToIso($("#globalT").value);

// ---------------------------------------------------------------- tabs
$$(".tabs button").forEach((b) => (b.onclick = () => {
  $$(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
  $$(".tab").forEach((s) => s.classList.toggle("active", s.id === "tab-" + b.dataset.tab));
  if (b.dataset.tab === "runs") loadRuns();
  if (b.dataset.tab === "tasks") loadTaskRuns();
}));

// ---------------------------------------------------------------- sources
async function loadSources() {
  const { sources, default_t } = await api("/api/sources");
  SOURCES = sources; DEFAULT_T = default_t;
  $("#globalT").value = isoToInput(default_t);
  const wrap = $("#sourceList"); wrap.innerHTML = "";
  for (const s of sources) wrap.append(sourceCard(s));
}

function sourceCard(s) {
  const body = el("div", { className: "src-body" });
  const inputs = {}, loaders = [];
  for (const p of s.params) {
    const f = el("div", { className: "field" });
    f.append(el("label", { textContent: p.label + (p.required ? " *" : "") }));
    if (p.discover && p.kind === "multiselect") inputs[p.name] = multiselect(f, s, p, loaders);
    else if (p.discover && p.kind === "select") inputs[p.name] = discoverSelect(f, s, p, loaders);
    else if (p.kind === "datetime") {
      const i = el("input", { type: "datetime-local", step: "60", value: isoToInput(p.default || DEFAULT_T) });
      f.append(i); inputs[p.name] = () => inputToIso(i.value);
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

  const head = el("div", { className: "src-head" }, [
    el("span", { className: "chev", textContent: "›" }),
    el("span", { className: "src-name", textContent: s.label }),
    s.note ? el("span", { className: "src-note", textContent: s.note }) : "",
    el("span", { className: "key " + (s.has_key ? "ok" : "no"), textContent: (s.has_key ? "✓ " : "✗ ") + s.env_key }),
  ]);
  const card = el("div", { className: "src" }, [head, body]);
  let loaded = false;
  head.onclick = () => {
    card.classList.toggle("open");
    if (card.classList.contains("open") && !loaded && s.has_key) { loaded = true; loaders.forEach((fn) => fn()); }
  };
  return card;
}

// discovery-backed multi-select (Slack channels): lazy-load on first open, search + checkboxes
function multiselect(field, s, p, loaders) {
  const chosen = new Set();
  const list = el("div", { className: "ms-list" }, el("div", { className: "ms-empty", textContent: "loading…" }));
  const search = el("input", { placeholder: "filter…" });
  const reload = el("button", { className: "ghost sm", textContent: "reload" });
  const ms = el("div", { className: "ms" }, [el("div", { className: "ms-bar" }, [search, reload]), list]);
  const tally = el("div", { className: "chosen", textContent: "none selected" });
  field.append(ms, tally);

  let opts = [];
  const render = () => {
    const q = search.value.toLowerCase();
    list.innerHTML = "";
    const shown = opts.filter((o) => (o.label || "").toLowerCase().includes(q));
    if (!shown.length) { list.append(el("div", { className: "ms-empty", textContent: "no matches" })); return; }
    for (const o of shown) {
      const cb = el("input", { type: "checkbox", checked: chosen.has(o.value) });
      cb.onchange = () => { cb.checked ? chosen.add(o.value) : chosen.delete(o.value); tally.textContent = chosen.size ? `${chosen.size} selected` : "none selected"; };
      list.append(el("label", { className: "ms-item" }, [cb,
        el("span", { className: "nm", textContent: o.label }),
        el("span", { className: "meta" }, [
          o.member ? el("span", { className: "mb", textContent: "member" }) : "",
          o.private ? el("span", { className: "pv", textContent: "private" }) : "",
          o.count != null ? el("span", { className: "ct", textContent: o.count }) : "",
        ])]));
    }
  };
  const load = async () => {
    list.innerHTML = ""; list.append(el("div", { className: "ms-empty", textContent: "loading…" }));
    try {
      const key = `${s.id}:${p.discover}`;
      opts = OPTCACHE[key] || (OPTCACHE[key] = (await api(`/api/sources/${s.id}/options/${p.discover}`)).options);
      render();
    } catch (e) { list.innerHTML = ""; list.append(el("div", { className: "ms-empty", textContent: "load failed: " + e.message })); }
  };
  search.oninput = render;
  reload.onclick = () => { delete OPTCACHE[`${s.id}:${p.discover}`]; opts = []; load(); };
  loaders.push(() => { if (!opts.length) load(); });
  return () => [...chosen];
}

function discoverSelect(field, s, p, loaders) {
  const sel = el("select", {}, el("option", { value: "", textContent: "auto (most issues)" }));
  field.append(sel);
  const load = async () => {
    try {
      const key = `${s.id}:${p.discover}`;
      const opts = OPTCACHE[key] || (OPTCACHE[key] = (await api(`/api/sources/${s.id}/options/${p.discover}`)).options);
      for (const o of opts) sel.append(el("option", { value: o.value, textContent: o.label + (o.count != null ? ` (${o.count})` : "") }));
    } catch (e) { toast("options: " + e.message, true); }
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
    toast(`Capture ${s.label} queued`);
    $$(".tabs button").find((b) => b.dataset.tab === "runs").click();
  } catch (e) { toast(`capture failed: ${e.message}`, true); }
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
  if (running.length) clearTimeout(loadRuns._t), (loadRuns._t = setTimeout(loadRuns, 2500));
}
function paint(host, empty, list) {
  host.innerHTML = ""; empty.style.display = list.length ? "none" : "block";
  for (const j of list) host.append(runRow(j));
}
function runRow(j) {
  const src = SOURCES.find((s) => s.id === j.source) || {};
  const acts = el("div", { className: "acts" });
  if (j.status === "done") {
    if (src.view_app) acts.append(act("view", () => view(j.id)));
    if (j.kind === "capture" && src.can_slice) acts.append(act("slice @T", () => sliceRun(j)));
  }
  if (j.status === "error") acts.append(act("error", () => toast(j.error || "failed", true)));
  const st = j.status === "running"
    ? el("span", { className: "pill running" }, [el("span", { className: "spin" }), "running"])
    : el("span", { className: "pill " + j.status, textContent: j.status });
  return el("div", { className: "run" }, [
    el("div", { className: "src-id", textContent: j.source }),
    el("div", { className: "kind", textContent: j.kind }),
    el("div", {}, [st, " ", el("span", { className: "summary", innerHTML: summarize(j) })]),
    el("div", { className: "when", textContent: ago(j.created) + " ago" }),
    el("div", {}, [acts]),
  ]);
}
const act = (label, fn) => { const b = el("button", { className: "ghost sm", textContent: label }); b.onclick = fn; return b; };
function summarize(j) {
  const r = j.report || {}; if (!r || j.status !== "done") return j.label || "";
  if (r.counts) return `${r.artifact} · ` + Object.entries(r.counts).slice(0, 3).map(([k, v]) => `${k}=<b>${v}</b>`).join(" ");
  if (r.incident_records != null) return `<b>${r.incident_records}</b> incident recs`;
  if (r.issues_kept != null) return `kept <b>${r.issues_kept}</b> / dropped ${r.issues_dropped}`;
  if (r.kept != null) return `kept <b>${r.kept}</b> / dropped ${r.dropped} msgs`;
  if (r.repo) return r.repo;
  return r.artifact || "";
}
async function sliceRun(j) {
  try { await api("/api/slice", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: j.id, cutoff: globalIso() }) });
    toast(`slice @ ${globalIso()} queued`); loadRuns();
  } catch (e) { toast(`slice failed: ${e.message}`, true); }
}
async function view(id) {
  try {
    const r = await api(`/api/runs/${id}/view`, { method: "POST" });
    if (r.loaded) { window.open(r.seed_dashboard_url, "_blank"); toast(`loaded into seed-dashboard (${r.view_app})`); }
    else toast(r.hint || "seed-dashboard offline", true);
  } catch (e) { toast(`view failed: ${e.message}`, true); }
}

// ---------------------------------------------------------------- task creator
async function loadTaskRuns() {
  const { runs } = await api("/api/runs");
  const done = runs.filter((r) => r.status === "done");
  const host = $("#taskRuns"); host.innerHTML = "";
  if (!done.length) { host.append(el("p", { className: "muted sm", textContent: "no completed runs to bundle yet." })); return; }
  for (const j of done) {
    const cb = el("input", { type: "checkbox", value: j.id });
    host.append(el("label", {}, [cb, el("span", { textContent: `${j.source} · ${j.kind}` }),
      el("span", { className: "ct muted sm", style: "margin-left:auto", textContent: j.label || "" })]));
  }
}
$("#genPlan").onclick = async () => {
  const ids = $$("#taskRuns input:checked").map((c) => c.value);
  if (!ids.length) return toast("pick at least one run", true);
  try {
    const plans = await Promise.all(ids.map((id) => api(`/api/runs/${id}/task_plan`)));
    const out = {
      incident_T: $("#globalT").value + ":00Z",
      code_anchor: { repo: $("#anchorRepo").value, commit: $("#anchorSha").value, resolution_pr: $("#anchorPr").value },
      surfaces: plans.map((p) => ({ source: p.source, artifacts: p.artifacts, would_bundle: p.would_bundle })),
      status: "preview — pipeline not wired yet",
    };
    const o = $("#planOut"); o.hidden = false; o.textContent = JSON.stringify(out, null, 2);
  } catch (e) { toast(e.message, true); }
};

$("#refresh").onclick = loadRuns;
loadSources().then(loadRuns).catch((e) => toast(e.message, true));
