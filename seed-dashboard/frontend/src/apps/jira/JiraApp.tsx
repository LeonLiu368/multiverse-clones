import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  Base,
  JiraComment,
  JiraIssue,
  JiraMeta,
  JiraProject,
  JiraState,
  JiraUser,
} from "../../api";

const PRIORITIES = ["urgent", "high", "medium", "low", "none"];

function stateClass(cat?: string) {
  return (
    { completed: "st-done", started: "st-prog", cancelled: "st-cancel", backlog: "st-backlog" }[
      cat ?? ""
    ] ?? "st-todo"
  );
}

// Jira-style priority glyphs (chevrons for severity).
const PRIO_GLYPH: Record<string, string> = {
  urgent: "⏫",
  high: "↑",
  medium: "=",
  low: "↓",
  none: "–",
};

const AVA_PALETTE = ["#0052cc", "#36b37e", "#ff7452", "#6554c0", "#00b8d9", "#ffab00", "#de350b"];
function avaColor(s: string) {
  let h = 0;
  for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AVA_PALETTE[h % AVA_PALETTE.length];
}

function Assignees({ people }: { people: { id?: string; name?: string }[] }) {
  if (!people.length) return <span className="ji-ava ji-ava-empty" title="Unassigned">∅</span>;
  const first = people[0];
  const label = first.name || first.id || "?";
  return (
    <span className="ji-ava-wrap" title={people.map((p) => p.name || p.id).join(", ")}>
      <span className="ji-ava" style={{ background: avaColor(label) }}>
        {label[0]?.toUpperCase()}
      </span>
      {people.length > 1 && <span className="ji-ava-more">+{people.length - 1}</span>}
    </span>
  );
}

export function JiraApp({ appId }: { appId: string }) {
  const [meta, setMeta] = useState<JiraMeta | null>(null);
  const [project, setProject] = useState<JiraProject | null>(null);
  const [users, setUsers] = useState<JiraUser[]>([]);
  const [issues, setIssues] = useState<JiraIssue[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [changesView, setChangesView] = useState(false);
  const [text, setText] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [err, setErr] = useState("");

  const userMap = useMemo(() => {
    const m: Record<string, JiraUser> = {};
    users.forEach((u) => (m[u.id] = u));
    return m;
  }, [users]);

  async function refresh() {
    const [mt, ps, us, iss] = await Promise.all([
      api.jira.meta(appId),
      api.jira.projects(appId),
      api.jira.users(appId),
      api.jira.issues(appId, "_"),
    ]);
    setMeta(mt);
    setProject(ps[0] ?? null);
    setUsers(us);
    setIssues(iss);
    setLoaded(true);
  }

  function flash(e: unknown) {
    setErr(String(e));
    setTimeout(() => setErr(""), 4000);
  }

  async function op(name: string, payload: Record<string, any>) {
    try {
      const r = await api.overlayOp(appId, name, payload);
      await refresh();
      return r;
    } catch (e) {
      flash(e);
      throw e;
    }
  }

  async function downloadPatch() {
    const name = window.prompt("Name the patch file:", "state-patch")?.trim();
    if (!name) return;
    try {
      const data = await api.exportOverlay(appId); // the {version, ops} task diff
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${name}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      flash(e);
    }
  }

  const matchText = (i: JiraIssue) =>
    !text ||
    i.identifier.toLowerCase().includes(text.toLowerCase()) ||
    i.title.toLowerCase().includes(text.toLowerCase());
  const filtered = issues.filter(
    (i) =>
      matchText(i) &&
      (changesView
        ? i.origin === "overlay" || i.edited
        : !statusFilter || i.state.name === statusFilter)
  );
  const deletedTombstones = changesView ? meta?.changes?.deleted ?? [] : [];
  const active = issues.find((i) => i.identifier === selected) ?? null;

  return (
    <div className="jira">
      <JiraSeedBar
        appId={appId}
        meta={meta}
        onLoaded={async () => {
          setSelected("");
          setStatusFilter("");
          await refresh();
        }}
        onDownload={downloadPatch}
      />
      {err && <div className="edit-err">⚠ {err}</div>}
      {!loaded ? (
        <div className="empty-state">
          Pick a base <b>state.json</b> (file or image) above, then <b>Load</b> to inspect the Jira
          workspace.
        </div>
      ) : (
        <div className="jira-body">
          {/* sidebar: project + status filter */}
          <aside className="jira-side">
            <div className="jira-proj">
              <span className="proj-key" style={{ background: "#0052cc" }}>
                {project?.key}
              </span>
              <div>
                <div className="proj-name">{project?.name}</div>
                <div className="proj-sub">
                  {meta?.stats?.issues} issues · {meta?.stats?.users} users
                </div>
              </div>
            </div>
            <div className="jira-section">Statuses</div>
            <ul className="status-list">
              <li
                className={!statusFilter && !changesView ? "active" : ""}
                onClick={() => {
                  setStatusFilter("");
                  setChangesView(false);
                }}
              >
                All<span className="count">{issues.length}</span>
              </li>
              {meta?.states.map((st: JiraState) => {
                const n = issues.filter((i) => i.state.name === st.name).length;
                return (
                  <li
                    key={st.id}
                    className={!changesView && statusFilter === st.name ? "active" : ""}
                    onClick={() => {
                      setStatusFilter(st.name);
                      setChangesView(false);
                    }}
                  >
                    <span className={`st-dot ${stateClass(st.category)}`} />
                    {st.name}
                    <span className="count">{n}</span>
                  </li>
                );
              })}
            </ul>
            <div className="jira-section">Patch diff</div>
            <ul className="status-list">
              <li
                className={`changes-item ${changesView ? "active" : ""}`}
                onClick={() => setChangesView(true)}
              >
                <span className="st-dot st-prog" />
                Changes
                <span className="count">{meta?.changes?.ops ?? 0} ops</span>
              </li>
            </ul>
            {meta?.changes && meta.changes.ops > 0 && (
              <div className="changes-summary">
                +{meta.changes.added.length} added · ~{meta.changes.edited.length} edited · −
                {meta.changes.deleted.length} deleted
                {meta.changes.comments_added + meta.changes.comments_deleted > 0 && (
                  <>
                    {" "}
                    · {meta.changes.comments_added + meta.changes.comments_deleted} comment ops
                  </>
                )}
              </div>
            )}
          </aside>

          {/* main: issue list */}
          <main className="jira-list">
            <header className="jira-list-head">
              <input
                className="jira-search"
                placeholder="Filter issues…"
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              <button className="primary" onClick={() => setShowNew(true)}>
                + New issue
              </button>
            </header>
            {showNew && (
              <NewIssue
                meta={meta!}
                users={users}
                onClose={() => setShowNew(false)}
                onCreate={async (payload) => {
                  const i = await op("add_issue", payload);
                  setShowNew(false);
                  if (i?.identifier) setSelected(i.identifier);
                }}
              />
            )}
            <div className="jira-rows">
              {filtered.map((i) => (
                <div
                  key={i.identifier}
                  className={`jira-row ${i.identifier === selected ? "sel" : ""} ${
                    i.origin === "overlay" ? "ov" : ""
                  }`}
                  onClick={() => setSelected(i.identifier)}
                >
                  <span className="ji-key">{i.identifier}</span>
                  <span className="ji-title">{i.title}</span>
                  {i.origin === "overlay" && <span className="badge ov">overlay</span>}
                  {i.edited && <span className="badge edited">edited</span>}
                  <span className={`ji-prio prio-${i.priority}`} title={`Priority: ${i.priority}`}>
                    {PRIO_GLYPH[i.priority] ?? "="}
                  </span>
                  <span className={`ji-state ${stateClass(i.state.category)}`}>{i.state.name}</span>
                  <Assignees people={i.assignees} />
                </div>
              ))}
              {deletedTombstones.map((d) => (
                <div key={d.identifier} className="jira-row tombstone" title="Deleted (recorded as a delete op)">
                  <span className="ji-key">{d.identifier}</span>
                  <span className="ji-title">{d.title}</span>
                  <span className="badge del">deleted</span>
                </div>
              ))}
              {!filtered.length && !deletedTombstones.length && (
                <div className="hint">{changesView ? "No pending changes." : "No issues match."}</div>
              )}
            </div>
          </main>

          {/* detail panel */}
          {active && (
            <IssueDetail
              appId={appId}
              key={active.identifier}
              issue={active}
              meta={meta!}
              users={users}
              userMap={userMap}
              onClose={() => setSelected("")}
              onOp={op}
            />
          )}
        </div>
      )}
    </div>
  );
}

// ---- seed bar (base = state.json file or jira-gateway image) ----
function JiraSeedBar({
  appId,
  meta,
  onLoaded,
  onDownload,
}: {
  appId: string;
  meta: JiraMeta | null;
  onLoaded: () => Promise<void>;
  onDownload: () => void;
}) {
  const [bases, setBases] = useState<Base[]>([]);
  const [extra, setExtra] = useState<Base[]>([]);
  const [baseId, setBaseId] = useState("");
  const [overlayFile, setOverlayFile] = useState<File | null>(null);
  const [pullRef, setPullRef] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const overlayRef = useRef<HTMLInputElement>(null);

  async function loadBases() {
    const b = await api.bases(appId);
    setBases(b);
    if (b.length && !baseId) setBaseId(b[0].id);
  }
  useEffect(() => {
    loadBases().catch((e) => setErr(String(e)));
  }, [appId]);

  const all = useMemo(() => {
    const seen = new Set<string>();
    return [...extra, ...bases].filter((b) => (seen.has(b.id) ? false : seen.add(b.id)));
  }, [bases, extra]);
  const images = all.filter((b) => b.kind === "image");
  const files = all.filter((b) => b.kind !== "image");

  async function doLoad() {
    setErr("");
    setBusy("Loading…");
    try {
      if (overlayFile) await api.loadOverlay(appId, baseId, overlayFile);
      else await api.load(appId, baseId);
      await onLoaded();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy("");
    }
  }
  async function doPull() {
    const ref = pullRef.trim();
    if (!ref) return;
    setErr("");
    setBusy("Pulling (amd64)…");
    try {
      const b = await api.pull(appId, ref);
      setExtra((e) => [b, ...e.filter((x) => x.id !== b.id)]);
      setBaseId(b.id);
      setPullRef("");
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="seedbar">
      <div className="seedbar-row">
        <span className="field-label">Base</span>
        <select className="base-select" value={baseId} onChange={(e) => setBaseId(e.target.value)}>
          {images.length > 0 && (
            <optgroup label="Images">
              {images.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.label.replace(/^ghcr\.io\/abundant-ai\//, "")}
                </option>
              ))}
            </optgroup>
          )}
          {files.length > 0 && (
            <optgroup label="Local state.json / empty">
              {files.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.label}
                </option>
              ))}
            </optgroup>
          )}
        </select>
        <button className="primary" onClick={doLoad} disabled={!baseId || !!busy}>
          Load
        </button>
        <span className="field-label muted">+ overlay</span>
        <input
          ref={overlayRef}
          type="file"
          accept=".json,application/json"
          className="overlay-file-hidden"
          onChange={(e) => setOverlayFile(e.target.files?.[0] ?? null)}
        />
        <button className="overlay-pick" disabled={!!busy} onClick={() => overlayRef.current?.click()}>
          {overlayFile ? `📄 ${overlayFile.name}` : "Overlay file…"}
        </button>
        {overlayFile && (
          <button className="icon-btn" title="clear overlay" onClick={() => setOverlayFile(null)}>
            ✕
          </button>
        )}
        <button className="ghost-btn" title="Download the task diff as an apply_state_patch op-list" onClick={onDownload}>
          ⬇ patch.json
        </button>
        <div className="seedbar-status">
          {busy && <span className="hint">⏳ {busy}</span>}
          {err && <span className="err">⚠ {err}</span>}
          {!busy && !err && meta && (
            <span className="hint">
              <b>{(meta.base || "").replace(/^ghcr\.io\/abundant-ai\//, "")}</b> ·{" "}
              {meta.stats?.issues} issues · {meta.stats?.comments} comments
            </span>
          )}
        </div>
      </div>
      <div className="seedbar-row sub">
        <span className="field-label muted">Pull</span>
        <input
          className="pull-input"
          value={pullRef}
          placeholder="ghcr.io/abundant-ai/jira-gateway-mv:prod-v1"
          onChange={(e) => setPullRef(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && doPull()}
        />
        <button onClick={doPull} disabled={!pullRef.trim() || !!busy}>
          Pull from GHCR
        </button>
      </div>
    </div>
  );
}

// ---- new-issue form ----
function NewIssue({
  meta,
  users,
  onClose,
  onCreate,
}: {
  meta: JiraMeta;
  users: JiraUser[];
  onClose: () => void;
  onCreate: (p: Record<string, any>) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [state, setState] = useState(meta.states[0]?.name ?? "");
  const [priority, setPriority] = useState("medium");
  const [assignee, setAssignee] = useState("");
  return (
    <div className="new-issue">
      <input
        className="ni-title"
        placeholder="Issue title"
        value={title}
        autoFocus
        onChange={(e) => setTitle(e.target.value)}
      />
      <textarea
        className="ni-desc"
        placeholder="Description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <div className="ni-row">
        <select value={state} onChange={(e) => setState(e.target.value)}>
          {meta.states.map((s) => (
            <option key={s.id}>{s.name}</option>
          ))}
        </select>
        <select value={priority} onChange={(e) => setPriority(e.target.value)}>
          {PRIORITIES.map((p) => (
            <option key={p}>{p}</option>
          ))}
        </select>
        <select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
          <option value="">unassigned</option>
          {users.map((u) => (
            <option key={u.id} value={u.handle}>
              {u.name}
            </option>
          ))}
        </select>
        <button
          className="primary"
          disabled={!title.trim()}
          onClick={() =>
            onCreate({ title, description, state, priority, assignee: assignee || undefined })
          }
        >
          Create
        </button>
        <button className="ghost-btn" onClick={onClose}>
          Cancel
        </button>
      </div>
    </div>
  );
}

// ---- issue detail + comments ----
function IssueDetail({
  appId,
  issue,
  meta,
  users,
  userMap,
  onClose,
  onOp,
}: {
  appId: string;
  issue: JiraIssue;
  meta: JiraMeta;
  users: JiraUser[];
  userMap: Record<string, JiraUser>;
  onClose: () => void;
  onOp: (op: string, payload: Record<string, any>) => Promise<any>;
}) {
  const [comments, setComments] = useState<JiraComment[] | null>(null);
  const [body, setBody] = useState("");
  const [author, setAuthor] = useState(users[0]?.handle ?? "");

  async function loadComments() {
    setComments(await api.jira.comments(appId, issue.project?.key ?? "_", issue.identifier));
  }
  useEffect(() => {
    setComments(null);
    loadComments();
  }, [appId, issue.identifier]);

  return (
    <aside className="jira-detail">
      <header className="jd-head">
        <span className="ji-key">{issue.identifier}</span>
        {issue.origin === "overlay" && <span className="badge ov">overlay</span>}
        {issue.edited && <span className="badge edited">edited</span>}
        <span className="jd-spacer" />
        <button
          className="ghost-btn danger"
          title={issue.origin === "base" ? "Delete (recorded as a delete op in the patch)" : "Delete overlay issue"}
          onClick={() => onOp("remove_issue", { identifier: issue.identifier })}
        >
          🗑 delete
        </button>
        <button className="link" onClick={onClose}>
          ✕
        </button>
      </header>

      <div className="jd-scroll">
        <h2 className="jd-title">{issue.title}</h2>

        <div className="jd-fields">
          <label>Status</label>
          <select
            value={issue.state.name}
            onChange={(e) => onOp("update_issue", { identifier: issue.identifier, state: e.target.value })}
          >
            {meta.states.map((s) => (
              <option key={s.id}>{s.name}</option>
            ))}
          </select>

          <label>Priority</label>
          <select
            value={issue.priority}
            onChange={(e) =>
              onOp("update_issue", { identifier: issue.identifier, priority: e.target.value })
            }
          >
            {PRIORITIES.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>

          <label>Assignee</label>
          <select
            value={issue.assignees[0]?.handle ?? ""}
            onChange={(e) =>
              onOp("update_issue", {
                identifier: issue.identifier,
                assignees: e.target.value ? [e.target.value] : [],
              })
            }
          >
            <option value="">unassigned</option>
            {users.map((u) => (
              <option key={u.id} value={u.handle}>
                {u.name}
              </option>
            ))}
          </select>
        </div>

        {issue.description && <div className="jd-desc">{issue.description}</div>}

        <div className="jd-comments-head">Comments</div>
        {!comments ? (
          <div className="hint">loading…</div>
        ) : (
          comments.map((c) => (
            <div key={c.id} className={`jd-comment ${c.origin === "overlay" ? "ov" : ""}`}>
              <div className="jc-meta">
                <b>{c.author?.name ?? c.author?.handle}</b>
                {c.origin === "overlay" && <span className="badge ov">overlay</span>}
                <button
                  className="jc-del"
                  title={c.origin === "base" ? "Delete (recorded as a delete op)" : "Delete overlay comment"}
                  onClick={() =>
                    onOp("remove_comment", { identifier: issue.identifier, comment_id: c.id }).then(
                      loadComments
                    )
                  }
                >
                  🗑
                </button>
              </div>
              <div className="jc-body">{c.body}</div>
            </div>
          ))
        )}

        <div className="jd-add-comment">
          <select value={author} onChange={(e) => setAuthor(e.target.value)}>
            {users.map((u) => (
              <option key={u.id} value={u.handle}>
                {u.name}
              </option>
            ))}
          </select>
          <input
            placeholder="Add a comment…"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={async (e) => {
              if (e.key === "Enter" && body.trim()) {
                await onOp("add_comment", { identifier: issue.identifier, body, author });
                setBody("");
                loadComments();
              }
            }}
          />
          <button
            className="primary"
            disabled={!body.trim()}
            onClick={async () => {
              await onOp("add_comment", { identifier: issue.identifier, body, author });
              setBody("");
              loadComments();
            }}
          >
            Comment
          </button>
        </div>
      </div>
    </aside>
  );
}
