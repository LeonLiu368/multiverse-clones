import { useEffect, useMemo, useState } from "react";
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

export function JiraApp({ appId }: { appId: string }) {
  const [meta, setMeta] = useState<JiraMeta | null>(null);
  const [project, setProject] = useState<JiraProject | null>(null);
  const [users, setUsers] = useState<JiraUser[]>([]);
  const [issues, setIssues] = useState<JiraIssue[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
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

  async function downloadState() {
    const name = window.prompt("Name the export file:", "state")?.trim();
    if (!name) return;
    try {
      const data = await api.exportOverlay(appId);
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

  const filtered = issues.filter(
    (i) =>
      (!statusFilter || i.state.name === statusFilter) &&
      (!text ||
        i.identifier.toLowerCase().includes(text.toLowerCase()) ||
        i.title.toLowerCase().includes(text.toLowerCase()))
  );
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
        onDownload={downloadState}
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
              <li className={!statusFilter ? "active" : ""} onClick={() => setStatusFilter("")}>
                All<span className="count">{issues.length}</span>
              </li>
              {meta?.states.map((st: JiraState) => {
                const n = issues.filter((i) => i.state.name === st.name).length;
                return (
                  <li
                    key={st.id}
                    className={statusFilter === st.name ? "active" : ""}
                    onClick={() => setStatusFilter(st.name)}
                  >
                    <span className={`st-dot ${stateClass(st.category)}`} />
                    {st.name}
                    <span className="count">{n}</span>
                  </li>
                );
              })}
            </ul>
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
                  <span className={`ji-state ${stateClass(i.state.category)}`}>{i.state.name}</span>
                  <span className={`ji-prio prio-${i.priority}`}>{i.priority}</span>
                  <span className="ji-title">{i.title}</span>
                  {i.origin === "overlay" && <span className="badge ov">overlay</span>}
                  {i.edited && <span className="badge edited">edited</span>}
                  <span className="ji-assignee">
                    {i.assignees.map((a) => a.name).join(", ")}
                  </span>
                </div>
              ))}
              {!filtered.length && <div className="hint">No issues match.</div>}
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
  const [pullRef, setPullRef] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

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
      await api.load(appId, baseId);
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
        <button className="ghost-btn" title="Download merged state.json" onClick={onDownload}>
          ⬇ state.json
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
          placeholder="ghcr.io/abundant-ai/jira-gateway:prod-v1"
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

  const canDelete = issue.origin === "overlay";

  return (
    <aside className="jira-detail">
      <header className="jd-head">
        <span className="ji-key">{issue.identifier}</span>
        {issue.origin === "overlay" && <span className="badge ov">overlay</span>}
        {issue.edited && <span className="badge edited">edited</span>}
        <span className="jd-spacer" />
        {canDelete && (
          <button
            className="ghost-btn danger"
            onClick={() => onOp("remove_issue", { identifier: issue.identifier })}
          >
            🗑 delete
          </button>
        )}
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
                {c.origin === "overlay" && (
                  <button
                    className="jc-del"
                    title="Delete overlay comment"
                    onClick={() =>
                      onOp("remove_comment", { identifier: issue.identifier, comment_id: c.id }).then(
                        loadComments
                      )
                    }
                  >
                    🗑
                  </button>
                )}
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
