import { useMemo, useState } from "react";
import { api } from "../../api";
import { SeedFileBar } from "../SeedFileBar";

type LUser = { id: string; name: string; displayName: string; email: string; avatarLetter: string };
type LComment = { id: string; body: string; createdAt?: string; author?: LUser | null };
type LIssue = {
  id: string;
  identifier: string;
  title: string;
  description?: string;
  priority: number;
  priorityLabel: string;
  createdAt?: string;
  updatedAt?: string;
  state: { id: string; name: string; type: string };
  assignee?: LUser | null;
  team: { id: string; key: string; name: string };
  labels: { id: string; name: string }[];
  comments: LComment[];
};
type Group = { type: string; name: string; issues: LIssue[] };
type LView = {
  org: { name: string; urlKey: string };
  team: { id: string; key: string; name: string; issueCount: number };
  users: LUser[];
  groups: Group[];
  labels: { id: string; name: string }[];
  stats: Record<string, number>;
};

const AVA_PALETTE = ["#5E6AD2", "#26B5CE", "#F2994A", "#4CB782", "#EB5757", "#9B7FE8", "#3E9BE0"];
function avaColor(s: string) {
  let h = 0;
  for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AVA_PALETTE[h % AVA_PALETTE.length];
}
function fmtDate(s?: string) {
  if (!s) return "";
  const d = new Date(s);
  return isNaN(+d) ? s : d.toLocaleDateString([], { month: "short", day: "numeric" });
}

// Linear's real status iconography: outline circle (backlog/todo), partial-arc fill (in progress),
// filled check (done), struck circle (canceled).
function StatusIcon({ type, size = 14 }: { type: string; size?: number }) {
  const s = { width: size, height: size, display: "block", flexShrink: 0 } as const;
  switch (type) {
    case "backlog":
      return (
        <svg viewBox="0 0 14 14" style={s}>
          <circle cx="7" cy="7" r="5.5" fill="none" stroke="#9CA3AF" strokeWidth="1.6" strokeDasharray="2.2 2.2" />
        </svg>
      );
    case "triage":
      return (
        <svg viewBox="0 0 14 14" style={s}>
          <circle cx="7" cy="7" r="5.5" fill="none" stroke="#F2994A" strokeWidth="1.6" strokeDasharray="1 2.4" strokeLinecap="round" />
        </svg>
      );
    case "unstarted":
      return (
        <svg viewBox="0 0 14 14" style={s}>
          <circle cx="7" cy="7" r="5.5" fill="none" stroke="#9CA3AF" strokeWidth="1.6" />
        </svg>
      );
    case "started":
      return (
        <svg viewBox="0 0 14 14" style={s}>
          <circle cx="7" cy="7" r="5.5" fill="none" stroke="#F2C94A" strokeWidth="1.6" />
          <path d="M7 7 L7 1.5 A5.5 5.5 0 0 1 12.5 7 Z" fill="#F2C94A" />
        </svg>
      );
    case "completed":
      return (
        <svg viewBox="0 0 14 14" style={s}>
          <circle cx="7" cy="7" r="6" fill="#4CB782" />
          <path d="M4.2 7.2 L6.1 9 L9.8 5" fill="none" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "canceled":
      return (
        <svg viewBox="0 0 14 14" style={s}>
          <circle cx="7" cy="7" r="5.5" fill="none" stroke="#9CA3AF" strokeWidth="1.6" />
          <path d="M4.8 4.8 L9.2 9.2" stroke="#9CA3AF" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
    default:
      return (
        <svg viewBox="0 0 14 14" style={s}>
          <circle cx="7" cy="7" r="5.5" fill="none" stroke="#9CA3AF" strokeWidth="1.6" />
        </svg>
      );
  }
}

// priority = 4-bar ascending signal icon; urgent gets the distinct orange square glyph.
function PriorityIcon({ p, size = 14 }: { p: number; size?: number }) {
  const s = { width: size, height: size, display: "block", flexShrink: 0 } as const;
  if (p === 1)
    return (
      <svg viewBox="0 0 14 14" style={s} aria-label="Urgent">
        <rect x="0.5" y="0.5" width="13" height="13" rx="2.5" fill="#EB5757" />
        <rect x="6.1" y="3" width="1.8" height="5" rx="0.9" fill="#fff" />
        <rect x="6.1" y="9" width="1.8" height="1.8" rx="0.9" fill="#fff" />
      </svg>
    );
  const bars = [3, 6, 9, 12];
  const filled = 4 - p; // p=0 none, p=2 high(3 bars), p=3 medium(2), p=4 low(1)
  return (
    <svg viewBox="0 0 14 14" style={s} aria-label="Priority">
      {bars.map((h, i) => (
        <rect key={i} x={1 + i * 3.4} y={13 - h} width="2" height={h} rx="0.6"
          fill={p > 0 && i < filled ? "#6B7280" : "#DFE1E6"} />
      ))}
    </svg>
  );
}

function Avatar({ u, size = 20 }: { u?: LUser | null; size?: number }) {
  if (!u)
    return (
      <span
        className="ln-ava ln-ava-empty"
        style={{ width: size, height: size, fontSize: size * 0.55 }}
        title="Unassigned"
      >
        ∅
      </span>
    );
  return (
    <span
      className="ln-ava"
      style={{ width: size, height: size, fontSize: size * 0.5, background: avaColor(u.id) }}
      title={u.displayName}
    >
      {u.avatarLetter}
    </span>
  );
}

export function LinearApp({ appId }: { appId: string }) {
  const [v, setV] = useState<LView | null>(null);
  const [sel, setSel] = useState<string>("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  async function load() {
    const data: LView = await api.view(appId);
    setV(data);
    setSel("");
    setCollapsed(new Set());
  }

  const allIssues = useMemo(() => (v ? v.groups.flatMap((g) => g.issues) : []), [v]);
  const issue = allIssues.find((i) => i.id === sel);

  function toggle(t: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(t) ? next.delete(t) : next.add(t);
      return next;
    });
  }

  return (
    <div className="linear">
      <SeedFileBar
        appId={appId}
        accept=".json,application/json"
        onLoaded={load}
        allowPull
        pullHint="ghcr.io/abundant-ai/jira-gateway:prod-v1"
      />
      {!v ? (
        <div className="empty-state">
          Load a Linear <b>state.json</b> (the same ticketvector corpus as Jira) to browse issues.
        </div>
      ) : (
        <div className="ln-body">
          <aside className="ln-side">
            <div className="ln-ws">{v.org.name}</div>
            <div className="ln-nav on">
              <span className="ln-nav-ic">☰</span> Issues
            </div>
            <div className="ln-section">Team</div>
            <div className="ln-team">
              <span className="ln-team-key">{v.team.key}</span>
              {v.team.name}
            </div>
            <div className="ln-section">Members</div>
            {v.users.map((u) => (
              <div className="ln-member" key={u.id}>
                <Avatar u={u} size={18} />
                <span className="ln-member-name">{u.displayName}</span>
              </div>
            ))}
          </aside>

          <main className="ln-main">
            <header className="ln-head">
              <span className="ln-head-title">Issues</span>
              <span className="ln-head-count">{v.stats.issues}</span>
            </header>
            <div className="ln-scroll">
              {v.groups.map((g) => (
                <div className="ln-group" key={g.type}>
                  <div className="ln-group-head" onClick={() => toggle(g.type)}>
                    <span className={`ln-caret ${collapsed.has(g.type) ? "closed" : ""}`}>▾</span>
                    <StatusIcon type={g.type} size={13} />
                    <span className="ln-group-name">{g.name}</span>
                    <span className="ln-group-count">{g.issues.length}</span>
                  </div>
                  {!collapsed.has(g.type) &&
                    g.issues.map((i) => (
                      <div
                        className={`ln-row ${i.id === sel ? "sel" : ""}`}
                        key={i.id}
                        onClick={() => setSel(i.id)}
                      >
                        <PriorityIcon p={i.priority} />
                        <span className="ln-id">{i.identifier}</span>
                        <StatusIcon type={i.state.type} />
                        <span className="ln-title">{i.title}</span>
                        {i.labels.map((l) => (
                          <span className="ln-label" key={l.id}>
                            {l.name}
                          </span>
                        ))}
                        <span className="ln-updated">{fmtDate(i.updatedAt)}</span>
                        <Avatar u={i.assignee} />
                      </div>
                    ))}
                </div>
              ))}
            </div>
          </main>

          {issue && (
            <aside className="ln-detail">
              <div className="ln-d-head">
                <span className="ln-id">{issue.identifier}</span>
                <button className="ln-close" onClick={() => setSel("")}>
                  ✕
                </button>
              </div>
              <h1 className="ln-d-title">{issue.title}</h1>
              {issue.description && <div className="ln-d-desc">{issue.description}</div>}

              <div className="ln-props">
                <div className="ln-prop-row">
                  <span className="ln-prop-k">Status</span>
                  <span className="ln-prop-v">
                    <StatusIcon type={issue.state.type} /> {issue.state.name}
                  </span>
                </div>
                <div className="ln-prop-row">
                  <span className="ln-prop-k">Priority</span>
                  <span className="ln-prop-v">
                    <PriorityIcon p={issue.priority} /> {issue.priorityLabel}
                  </span>
                </div>
                <div className="ln-prop-row">
                  <span className="ln-prop-k">Assignee</span>
                  <span className="ln-prop-v">
                    <Avatar u={issue.assignee} size={18} /> {issue.assignee?.displayName || "Unassigned"}
                  </span>
                </div>
                <div className="ln-prop-row">
                  <span className="ln-prop-k">Team</span>
                  <span className="ln-prop-v">
                    {issue.team.key} {issue.team.name}
                  </span>
                </div>
                {issue.labels.length > 0 && (
                  <div className="ln-prop-row">
                    <span className="ln-prop-k">Labels</span>
                    <span className="ln-prop-v ln-prop-labels">
                      {issue.labels.map((l) => (
                        <span className="ln-label" key={l.id}>
                          {l.name}
                        </span>
                      ))}
                    </span>
                  </div>
                )}
              </div>

              {issue.comments.length > 0 && (
                <div className="ln-comments">
                  <div className="ln-comments-h">Activity</div>
                  {issue.comments.map((c) => (
                    <div className="ln-comment" key={c.id}>
                      <Avatar u={c.author} size={18} />
                      <div className="ln-comment-body">
                        <span className="ln-comment-a">{c.author?.displayName || "Someone"}</span>
                        <span className="ln-comment-t">{c.body}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </aside>
          )}
        </div>
      )}
    </div>
  );
}
