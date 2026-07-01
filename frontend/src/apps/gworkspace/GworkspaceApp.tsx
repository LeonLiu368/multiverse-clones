import { useMemo, useState } from "react";
import { api } from "../../api";
import { SeedFileBar } from "../SeedFileBar";

type Owner = { displayName?: string; emailAddress?: string };
type GFile = {
  id: string;
  name: string;
  mimeType: string;
  parents: string[];
  modifiedTime?: string;
  owners: Owner[];
  size?: string;
  isFolder: boolean;
  children?: GFile[];
};
type Para = {
  paragraph?: {
    paragraphStyle?: { namedStyleType?: string };
    elements?: { textRun?: { content?: string; textStyle?: any } }[];
  };
};
type GDoc = {
  documentId: string;
  title: string;
  revisionId?: string;
  body: { content?: Para[] };
  text: string;
  headings: { level: number; text: string }[];
};
type GEvent = {
  id: string;
  summary?: string;
  location?: string;
  status?: string;
  start?: any;
  end?: any;
  organizer?: Owner;
  attendees?: Owner[];
};
type GMsg = {
  id: string;
  threadId?: string;
  labelIds?: string[];
  from?: string;
  to?: string;
  subject?: string;
  date?: string;
  snippet?: string;
  bodyText?: string;
};
type GView = {
  files: GFile[];
  tree: GFile[];
  documents: GDoc[];
  events: GEvent[];
  messages: GMsg[];
  stats: { files: number; folders: number; documents: number; events: number; messages: number };
};

const MIME: Record<string, { icon: string; color: string; label: string }> = {
  "application/vnd.google-apps.folder": { icon: "▸", color: "#5f6368", label: "Folder" },
  "application/vnd.google-apps.document": { icon: "📄", color: "#1a73e8", label: "Google Docs" },
  "application/vnd.google-apps.spreadsheet": { icon: "📊", color: "#188038", label: "Google Sheets" },
  "application/vnd.google-apps.presentation": { icon: "📑", color: "#e37400", label: "Google Slides" },
  "application/pdf": { icon: "📕", color: "#ea4335", label: "PDF" },
};
function fileMeta(m: string) {
  if (m?.startsWith("image/")) return { icon: "🖼", color: "#ea4335", label: "Image" };
  return MIME[m] ?? { icon: "📄", color: "#5f6368", label: m?.split(".").pop() || "File" };
}
function fmtDate(s?: string) {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(+d) ? s : d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}
function fmtSize(s?: string) {
  const n = Number(s);
  if (!n) return "—";
  return n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`;
}

export function GworkspaceApp({ appId }: { appId: string }) {
  const [v, setV] = useState<GView | null>(null);
  const [tab, setTab] = useState<"drive" | "docs" | "calendar" | "gmail">("drive");
  const [folder, setFolder] = useState<string>("");        // current Drive folder id ("" = root)
  const [selDoc, setSelDoc] = useState<string>("");
  const [selMsg, setSelMsg] = useState<string>("");

  async function load() {
    const data: GView = await api.view(appId);
    setV(data);
    setFolder("");
    setSelDoc(data.documents[0]?.documentId ?? "");
    setSelMsg(data.messages[0]?.id ?? "");
    setTab(data.stats.files + data.stats.folders ? "drive" : data.documents.length ? "docs" : "drive");
  }

  const byId = useMemo(() => {
    const m: Record<string, GFile> = {};
    v?.files.forEach((f) => (m[f.id] = f));
    return m;
  }, [v]);
  const folders = useMemo(() => (v ? v.files.filter((f) => f.isFolder) : []), [v]);

  // contents of the current folder ("" = roots: files whose parent isn't a known folder)
  const contents = useMemo(() => {
    if (!v) return [];
    const inFolder = (f: GFile) =>
      folder ? f.parents.includes(folder) : !f.parents.some((p) => byId[p]);
    return v.files
      .filter(inFolder)
      .sort((a, b) => (a.isFolder === b.isFolder ? a.name.localeCompare(b.name) : a.isFolder ? -1 : 1));
  }, [v, folder, byId]);

  const crumbs = useMemo(() => {
    const path: GFile[] = [];
    let cur = folder ? byId[folder] : null;
    while (cur) {
      path.unshift(cur);
      cur = cur.parents.map((p) => byId[p]).find(Boolean) || null;
    }
    return path;
  }, [folder, byId]);

  function openFile(f: GFile) {
    if (f.isFolder) return setFolder(f.id);
    if (f.mimeType === "application/vnd.google-apps.document" && v?.documents.some((d) => d.documentId === f.id)) {
      setSelDoc(f.id);
      setTab("docs");
    }
  }

  const doc = v?.documents.find((d) => d.documentId === selDoc) ?? null;
  const msg = v?.messages.find((m) => m.id === selMsg) ?? null;

  const TABS: [typeof tab, string, number][] = v
    ? [
        ["drive", "Drive", v.stats.files + v.stats.folders],
        ["docs", "Docs", v.stats.documents],
        ["calendar", "Calendar", v.stats.events],
        ["gmail", "Gmail", v.stats.messages],
      ]
    : [];

  return (
    <div className="gws">
      <SeedFileBar
        appId={appId}
        accept=".json,application/json"
        onLoaded={load}
        allowPull
        pullHint="ghcr.io/abundant-ai/gws-service:prod-v1"
      />
      {!v ? (
        <div className="empty-state">
          Load a Workspace <b>fixture.json</b> (or pull a <b>gws.db</b> image) to browse Drive, Docs,
          Calendar and Gmail.
        </div>
      ) : (
        <div className="gws-body">
          <div className="gws-tabs">
            {TABS.map(([id, label, n]) => (
              <button
                key={id}
                className={`gws-tab ${tab === id ? "on" : ""}`}
                disabled={!n}
                onClick={() => setTab(id)}
              >
                {label}
                <span className="gws-count">{n}</span>
              </button>
            ))}
          </div>

          {/* ---------------- Drive ---------------- */}
          {tab === "drive" && (
            <div className="gws-drive">
              <aside className="gws-tree">
                <div className={`gws-tnode ${!folder ? "on" : ""}`} onClick={() => setFolder("")}>
                  <span className="gws-ticon">🗂</span> My Drive
                </div>
                {folders.map((f) => (
                  <div
                    key={f.id}
                    className={`gws-tnode ${folder === f.id ? "on" : ""}`}
                    style={{ paddingLeft: 12 + f.parents.filter((p) => byId[p]).length * 14 }}
                    onClick={() => setFolder(f.id)}
                  >
                    <span className="gws-ticon">📁</span> {f.name}
                  </div>
                ))}
              </aside>
              <main className="gws-files">
                <div className="gws-crumbs">
                  <span className="gws-crumb" onClick={() => setFolder("")}>
                    My Drive
                  </span>
                  {crumbs.map((c) => (
                    <span key={c.id}>
                      <span className="gws-crumb-sep">›</span>
                      <span className="gws-crumb" onClick={() => setFolder(c.id)}>
                        {c.name}
                      </span>
                    </span>
                  ))}
                </div>
                <div className="gws-filehead">
                  <span>Name</span>
                  <span>Owner</span>
                  <span>Modified</span>
                  <span>Size</span>
                </div>
                {contents.map((f) => {
                  const m = fileMeta(f.mimeType);
                  return (
                    <div
                      key={f.id}
                      className="gws-filerow"
                      onClick={() => openFile(f)}
                      title={m.label}
                    >
                      <span className="gws-fname">
                        <span className="gws-ficon" style={{ color: m.color }}>
                          {m.icon}
                        </span>
                        {f.name}
                      </span>
                      <span className="gws-fowner">{f.owners[0]?.displayName ?? "—"}</span>
                      <span className="gws-fdate">{fmtDate(f.modifiedTime)}</span>
                      <span className="gws-fsize">{f.isFolder ? "—" : fmtSize(f.size)}</span>
                    </div>
                  );
                })}
                {!contents.length && <div className="hint" style={{ padding: 20 }}>Empty folder.</div>}
              </main>
            </div>
          )}

          {/* ---------------- Docs ---------------- */}
          {tab === "docs" && (
            <div className="gws-docs">
              <aside className="gws-doclist">
                {v.documents.map((d) => (
                  <div
                    key={d.documentId}
                    className={`gws-docitem ${d.documentId === selDoc ? "on" : ""}`}
                    onClick={() => setSelDoc(d.documentId)}
                  >
                    <span className="gws-ficon" style={{ color: "#1a73e8" }}>📄</span>
                    <span className="gws-docitem-t">{d.title}</span>
                  </div>
                ))}
              </aside>
              {doc ? (
                <main className="gws-docmain">
                  <div className="gws-page">
                    {(doc.body.content || []).map((el, i) => {
                      const p = el.paragraph;
                      if (!p) return null;
                      const style = p.paragraphStyle?.namedStyleType || "NORMAL_TEXT";
                      const tag = style.startsWith("HEADING_")
                        ? `h${Math.min(Number(style.split("_")[1]) || 1, 4)}`
                        : "p";
                      const cls = style.startsWith("HEADING_") ? "gws-h" : "gws-p";
                      const runs = (p.elements || []).map((e, j) => {
                        const ts = e.textRun?.textStyle || {};
                        return (
                          <span
                            key={j}
                            style={{
                              fontWeight: ts.bold ? 700 : undefined,
                              fontStyle: ts.italic ? "italic" : undefined,
                              textDecoration: ts.underline ? "underline" : undefined,
                            }}
                          >
                            {(e.textRun?.content || "").replace(/\n$/, "")}
                          </span>
                        );
                      });
                      const Tag = tag as any;
                      return <Tag key={i} className={`${cls} ${cls}-${tag}`}>{runs}</Tag>;
                    })}
                  </div>
                </main>
              ) : (
                <div className="hint" style={{ padding: 24 }}>Select a document.</div>
              )}
              {doc && doc.headings.length > 0 && (
                <aside className="gws-outline">
                  <div className="gws-outline-h">Outline</div>
                  {doc.headings.map((h, i) => (
                    <div key={i} className="gws-ol-item" style={{ paddingLeft: 10 + (h.level - 1) * 12 }}>
                      {h.text}
                    </div>
                  ))}
                  <div className="gws-doc-meta">rev {doc.revisionId ?? "—"} · {doc.documentId}</div>
                </aside>
              )}
            </div>
          )}

          {/* ---------------- Calendar ---------------- */}
          {tab === "calendar" && (
            <div className="gws-agenda">
              {v.events.map((e) => (
                <div key={e.id} className="gws-event">
                  <div className="gws-event-time">
                    {fmtDate(e.start?.dateTime || e.start?.date)}
                    <span>
                      {(e.start?.dateTime || "").slice(11, 16)}–{(e.end?.dateTime || "").slice(11, 16)}
                    </span>
                  </div>
                  <div className="gws-event-body">
                    <div className="gws-event-title">{e.summary}</div>
                    <div className="gws-event-sub">
                      {e.location && <span>📍 {e.location}</span>}
                      {e.attendees?.length ? <span>👥 {e.attendees.length}</span> : null}
                      {e.status && <span className="gws-event-status">{e.status}</span>}
                    </div>
                  </div>
                </div>
              ))}
              {!v.events.length && <div className="hint" style={{ padding: 24 }}>No events.</div>}
            </div>
          )}

          {/* ---------------- Gmail ---------------- */}
          {tab === "gmail" && (
            <div className="gws-gmail">
              <aside className="gws-maillist">
                {v.messages.map((m) => (
                  <div
                    key={m.id}
                    className={`gws-mailrow ${m.id === selMsg ? "on" : ""}`}
                    onClick={() => setSelMsg(m.id)}
                  >
                    <div className="gws-mail-from">{m.from}</div>
                    <div className="gws-mail-subj">{m.subject}</div>
                    <div className="gws-mail-snip">{m.snippet}</div>
                    <div className="gws-mail-labels">
                      {(m.labelIds || []).map((l) => (
                        <span key={l} className="gws-label">{l}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </aside>
              {msg ? (
                <main className="gws-mailview">
                  <h2>{msg.subject}</h2>
                  <div className="gws-mailmeta">
                    <b>{msg.from}</b> → {msg.to} · {fmtDate(msg.date)}
                  </div>
                  <pre className="gws-mailbody">{msg.bodyText || msg.snippet}</pre>
                </main>
              ) : (
                <div className="hint" style={{ padding: 24 }}>Select a message.</div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
