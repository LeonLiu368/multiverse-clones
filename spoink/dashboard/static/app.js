// spoink dashboard — thin client of the control-plane API.
const $ = (s, r = document) => r.querySelector(s);
const el = (t, props = {}, kids = []) => {
  const n = Object.assign(document.createElement(t), props);
  for (const k of [].concat(kids)) n.append(k);
  return n;
};
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || body.error || r.statusText);
  return body;
};
let TOAST_T;
const toast = (msg, err = false) => {
  const t = $("#toast"); t.textContent = msg; t.className = "show" + (err ? " err" : "");
  clearTimeout(TOAST_T); TOAST_T = setTimeout(() => (t.className = ""), 4000);
};
const ago = (s) => {
  if (!s) return "—";
  const d = Math.max(0, Date.now() / 1000 - s);
  if (d < 60) return `${d | 0}s ago`;
  if (d < 3600) return `${(d / 60) | 0}m ago`;
  return `${(d / 3600) | 0}h ago`;
};

let SOURCES = [], DEFAULT_T = "";

async function loadSources() {
  const { sources, default_t } = await api("/api/sources");
  SOURCES = sources; DEFAULT_T = default_t;
  if (!$("#globalT").value) $("#globalT").value = default_t;
  const wrap = $("#sourceCards"); wrap.innerHTML = "";
  for (const s of sources) wrap.append(sourceCard(s));
}

function sourceCard(s) {
  const form = el("div", { className: "form", id: `form-${s.id}` });
  for (const p of s.params) {
    const id = `f-${s.id}-${p.name}`;
    const input = p.kind === "select"
      ? el("select", { id }, p.options.map((o) => el("option", { value: o, textContent: o })))
      : el("input", { id, value: p.default || "", placeholder: p.help || "" });
    input.dataset.role = p.name === "latest" || p.name === "until" ? "T" : "";
    form.append(el("div", { className: "field" }, [
      el("label", { textContent: p.label + (p.required ? " *" : "") }),
      input,
      p.help ? el("div", { className: "help", textContent: p.help }) : "",
    ]));
  }
  const btn = el("button", { textContent: `capture ${s.label}`, disabled: !s.has_key });
  btn.onclick = () => capture(s, btn);
  return el("div", { className: "card" }, [
    el("div", { className: "top" }, [
      el("div", { className: "name", textContent: s.label }),
      el("span", {
        className: "key " + (s.has_key ? "ok" : "no"),
        textContent: (s.has_key ? "✓ " : "✗ ") + s.env_key,
      }),
    ]),
    form,
    el("div", { className: "actions" }, [btn]),
  ]);
}

async function capture(s, btn) {
  const params = {};
  for (const p of s.params) params[p.name] = $(`#f-${s.id}-${p.name}`).value;
  btn.disabled = true;
  try {
    await api("/api/capture", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: s.id, params }),
    });
    toast(`capture ${s.label} queued`);
    loadRuns();
  } catch (e) { toast(`capture failed: ${e.message}`, true); }
  finally { btn.disabled = !s.has_key; }
}

async function loadRuns() {
  const { runs } = await api("/api/runs");
  const tb = $("#runsTable tbody"); tb.innerHTML = "";
  $("#runsEmpty").style.display = runs.length ? "none" : "block";
  $("#runsTable").style.display = runs.length ? "table" : "none";
  for (const j of runs) tb.append(runRow(j));
  // keep polling while anything is in flight
  if (runs.some((j) => j.status === "running" || j.status === "queued"))
    clearTimeout(loadRuns._t), (loadRuns._t = setTimeout(loadRuns, 2500));
}

function runRow(j) {
  const acts = el("div", { className: "row-actions" });
  const src = SOURCES.find((s) => s.id === j.source) || {};
  if (j.status === "done") {
    if (src.view_app) {
      const v = el("button", { className: "ghost sm", textContent: "view" });
      v.onclick = () => view(j.id, v); acts.append(v);
    }
    if (j.kind === "capture" && src.can_slice) {
      const sl = el("button", { className: "ghost sm", textContent: "slice @T" });
      sl.onclick = () => sliceRun(j, sl); acts.append(sl);
    }
    const tp = el("button", { className: "ghost sm", textContent: "task plan" });
    tp.onclick = () => taskPlan(j.id); acts.append(tp);
  }
  if (j.status === "error") {
    const e = el("button", { className: "ghost sm", textContent: "error" });
    e.onclick = () => toast(j.error || "failed", true); acts.append(e);
  }
  const summary = j.report ? summarize(j) : "";
  return el("tr", {}, [
    el("td", { className: "mono", textContent: j.source }),
    el("td", { textContent: j.kind }),
    el("td", {}, [el("span", { className: "pill " + j.status, textContent: j.status })]),
    el("td", { textContent: j.label || "" }),
    el("td", { className: "artifacts", textContent: summary }),
    el("td", { className: "muted", textContent: ago(j.created) }),
    el("td", {}, [acts]),
  ]);
}

function summarize(j) {
  const r = j.report || {};
  if (r.counts && typeof r.counts === "object")
    return r.artifact + " · " + Object.entries(r.counts).slice(0, 3).map(([k, v]) => `${k}=${v}`).join(" ");
  if (r.incident_records != null) return `logfire · ${r.incident_records} incident recs`;
  if (r.issues_kept != null) return `kept ${r.issues_kept} issues / dropped ${r.issues_dropped}`;
  if (r.kept != null) return `kept ${r.kept} / dropped ${r.dropped} msgs`;
  return r.artifact || "";
}

async function sliceRun(j, btn) {
  const cutoff = $("#globalT").value || DEFAULT_T;
  btn.disabled = true;
  try {
    await api("/api/slice", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: j.id, cutoff }),
    });
    toast(`slice @ ${cutoff} queued`); loadRuns();
  } catch (e) { toast(`slice failed: ${e.message}`, true); }
  finally { btn.disabled = false; }
}

async function view(id, btn) {
  btn.disabled = true;
  try {
    const r = await api(`/api/runs/${id}/view`, { method: "POST" });
    if (r.loaded) { window.open(r.seed_dashboard_url, "_blank"); toast(`loaded into seed-dashboard (${r.view_app})`); }
    else toast(r.hint || "seed-dashboard offline", true);
  } catch (e) { toast(`view failed: ${e.message}`, true); }
  finally { btn.disabled = false; }
}

async function taskPlan(id) {
  try {
    const p = await api(`/api/runs/${id}/task_plan`);
    toast(`task plan: would bundle ${(p.artifacts || []).join(", ")} @ ${p.cutoff_T || "T"} (preview)`);
    console.log("task plan", p);
  } catch (e) { toast(e.message, true); }
}

$("#applyT").onclick = () => {
  const t = $("#globalT").value;
  document.querySelectorAll('input[data-role="T"]').forEach((i) => (i.value = t));
  toast("T applied to source forms");
};
$("#refresh").onclick = loadRuns;

loadSources().then(loadRuns).catch((e) => toast(e.message, true));
