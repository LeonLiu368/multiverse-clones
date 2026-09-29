import { useMemo, useState } from "react";
import { api } from "../../api";
import { SeedFileBar } from "../SeedFileBar";

type Rich = { text: string; bold?: boolean; italic?: boolean; strikethrough?: boolean; underline?: boolean; code?: boolean; color?: string };
type Prop = { type: string; display: any; options?: { name?: string; color?: string }[] };
type Block = { id: string; type: string; rich: Rich[]; checked?: boolean; language?: string };
type Page = {
  id: string; title: string; database_id?: string | null; icon?: any;
  properties: Record<string, Prop>; blocks: Block[];
  comments: { id: string; rich: Rich[]; author?: any; created_time?: string }[];
  in_trash?: boolean; last_edited_time?: string;
};
type DB = { id: string; title: string; description?: string; icon?: any; property_order: string[] };
type NView = { users: any[]; databases: DB[]; pages: Page[]; stats: Record<string, number> };

// Notion named colors → pill background/text.
const NC: Record<string, { bg: string; fg: string }> = {
  default: { bg: "#e3e2e0", fg: "#37352f" }, gray: { bg: "#e3e2e0", fg: "#32302c" },
  brown: { bg: "#eee0da", fg: "#5c3b2e" }, orange: { bg: "#fadec9", fg: "#8a4b22" },
  yellow: { bg: "#fdecc8", fg: "#7a5b16" }, green: { bg: "#dbeddb", fg: "#28563a" },
  blue: { bg: "#d3e5ef", fg: "#28456c" }, purple: { bg: "#e8deee", fg: "#492f64" },
  pink: { bg: "#f5e0e9", fg: "#6d3654" }, red: { bg: "#ffe2dd", fg: "#6e3630" },
};
const pill = (c?: string) => NC[c || "default"] || NC.default;

const emoji = (icon: any) => (icon && icon.type === "emoji" ? icon.emoji : null);

function RichText({ parts }: { parts: Rich[] }) {
  if (!parts?.length) return null;
  return (
    <>
      {parts.map((p, i) => {
        const style: React.CSSProperties = {
          fontWeight: p.bold ? 600 : undefined,
          fontStyle: p.italic ? "italic" : undefined,
          textDecoration: [p.strikethrough && "line-through", p.underline && "underline"].filter(Boolean).join(" ") || undefined,
          color: p.color && p.color !== "default" && !p.color.endsWith("_background") ? (NC[p.color]?.fg) : undefined,
        };
        if (p.code)
          return <code className="nt-code" key={i}>{p.text}</code>;
        return <span key={i} style={style}>{p.text}</span>;
      })}
    </>
  );
}

function PropCell({ p }: { p: Prop }) {
  if (p == null) return <span className="nt-muted">—</span>;
  if (p.type === "status" || p.type === "select") {
    if (!p.display) return <span className="nt-muted">—</span>;
    const c = pill(p.options?.[0]?.color);
    return <span className="nt-pill" style={{ background: c.bg, color: c.fg }}>{p.display}</span>;
  }
  if (p.type === "multi_select")
    return (
      <span className="nt-pills">
        {(p.options || []).map((o, i) => {
          const c = pill(o.color);
          return <span className="nt-pill" key={i} style={{ background: c.bg, color: c.fg }}>{o.name}</span>;
        })}
      </span>
    );
  if (p.type === "checkbox") return <span>{p.display ? "☑" : "☐"}</span>;
  if (p.type === "date") return <span className="nt-date">{p.display || "—"}</span>;
  if (p.display === "" || p.display == null) return <span className="nt-muted">—</span>;
  return <span>{String(p.display)}</span>;
}

function BlockView({ b }: { b: Block }) {
  switch (b.type) {
    case "heading_1": return <h1 className="nt-h1"><RichText parts={b.rich} /></h1>;
    case "heading_2": return <h2 className="nt-h2"><RichText parts={b.rich} /></h2>;
    case "heading_3": return <h3 className="nt-h3"><RichText parts={b.rich} /></h3>;
    case "to_do":
      return (
        <div className={`nt-todo ${b.checked ? "done" : ""}`}>
          <span className="nt-check">{b.checked ? "☑" : "☐"}</span>
          <span><RichText parts={b.rich} /></span>
        </div>
      );
    case "bulleted_list_item": return <div className="nt-li"><span className="nt-bullet">•</span><span><RichText parts={b.rich} /></span></div>;
    case "numbered_list_item": return <div className="nt-li"><span className="nt-bullet">1.</span><span><RichText parts={b.rich} /></span></div>;
    case "quote": return <blockquote className="nt-quote"><RichText parts={b.rich} /></blockquote>;
    case "code": return <pre className="nt-codeblock">{b.rich.map((r) => r.text).join("")}</pre>;
    case "divider": return <hr className="nt-divider" />;
    default: return <p className="nt-p"><RichText parts={b.rich} /></p>;
  }
}

export function NotionApp({ appId }: { appId: string }) {
  const [v, setV] = useState<NView | null>(null);
  const [sel, setSel] = useState<{ kind: "db" | "page"; id: string } | null>(null);

  async function load() {
    const data: NView = await api.view(appId);
    setV(data);
    setSel(data.databases[0] ? { kind: "db", id: data.databases[0].id } : data.pages[0] ? { kind: "page", id: data.pages[0].id } : null);
  }

  const pagesByDb = useMemo(() => {
    const m: Record<string, Page[]> = {};
    v?.pages.forEach((p) => { if (p.database_id) (m[p.database_id] ||= []).push(p); });
    return m;
  }, [v]);
  const loosePages = useMemo(() => (v ? v.pages.filter((p) => !p.database_id) : []), [v]);

  const db = sel?.kind === "db" ? v?.databases.find((d) => d.id === sel.id) : null;
  const dbPages = db ? pagesByDb[db.id] || [] : [];
  const page = sel?.kind === "page" ? v?.pages.find((p) => p.id === sel.id) : null;

  return (
    <div className="notion">
      <SeedFileBar appId={appId} accept=".json,application/json" onLoaded={load} allowPull
        pullHint="ghcr.io/abundant-ai/notion-service:prod-v1" />
      {!v ? (
        <div className="empty-state">Load a Notion <b>fixture.json</b> (or a <b>notion.db</b> image) to browse databases &amp; pages.</div>
      ) : (
        <div className="nt-body">
          <aside className="nt-side">
            <div className="nt-ws">Workspace</div>
            {v.databases.map((d) => (
              <div key={d.id}>
                <div className={`nt-navitem ${sel?.kind === "db" && sel.id === d.id ? "on" : ""}`}
                  onClick={() => setSel({ kind: "db", id: d.id })}>
                  <span className="nt-ic">{emoji(d.icon) || "▤"}</span>
                  <span className="nt-navlabel">{d.title}</span>
                </div>
                {(pagesByDb[d.id] || []).map((p) => (
                  <div key={p.id} className={`nt-navitem nt-navchild ${sel?.kind === "page" && sel.id === p.id ? "on" : ""}`}
                    onClick={() => setSel({ kind: "page", id: p.id })}>
                    <span className="nt-ic">{emoji(p.icon) || "📄"}</span>
                    <span className="nt-navlabel">{p.title}</span>
                  </div>
                ))}
              </div>
            ))}
            {loosePages.map((p) => (
              <div key={p.id} className={`nt-navitem ${sel?.kind === "page" && sel.id === p.id ? "on" : ""}`}
                onClick={() => setSel({ kind: "page", id: p.id })}>
                <span className="nt-ic">{emoji(p.icon) || "📄"}</span>
                <span className="nt-navlabel">{p.title}</span>
              </div>
            ))}
          </aside>

          <main className="nt-main">
            {db ? (
              <div className="nt-dbview">
                <div className="nt-title-row">
                  <span className="nt-title-ic">{emoji(db.icon) || "▤"}</span>
                  <h1 className="nt-title">{db.title}</h1>
                </div>
                {db.description && <div className="nt-desc">{db.description}</div>}
                <div className="nt-table-wrap">
                  <table className="nt-table">
                    <thead>
                      <tr>{db.property_order.map((c) => <th key={c}>{c}</th>)}</tr>
                    </thead>
                    <tbody>
                      {dbPages.map((p) => (
                        <tr key={p.id} onClick={() => setSel({ kind: "page", id: p.id })}>
                          {db.property_order.map((c, i) => (
                            <td key={c}>
                              {i === 0
                                ? <span className="nt-cell-title"><span className="nt-ic">{emoji(p.icon) || "📄"}</span>{p.title}</span>
                                : <PropCell p={p.properties[c]} />}
                            </td>
                          ))}
                        </tr>
                      ))}
                      {!dbPages.length && <tr><td colSpan={db.property_order.length} className="nt-muted">No pages.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : page ? (
              <article className="nt-page">
                <div className="nt-page-ic">{emoji(page.icon) || "📄"}</div>
                <h1 className="nt-page-title">{page.title}{page.in_trash && <span className="nt-trash">In Trash</span>}</h1>
                <div className="nt-props">
                  {Object.entries(page.properties).filter(([, p]) => p.type !== "title").map(([k, p]) => (
                    <div className="nt-prop-row" key={k}>
                      <span className="nt-prop-k">{k}</span>
                      <span className="nt-prop-v"><PropCell p={p} /></span>
                    </div>
                  ))}
                </div>
                <div className="nt-blocks">
                  {page.blocks.map((b) => <BlockView b={b} key={b.id} />)}
                  {!page.blocks.length && <div className="nt-muted">Empty page.</div>}
                </div>
                {page.comments.length > 0 && (
                  <div className="nt-comments">
                    <div className="nt-comments-h">{page.comments.length} comment{page.comments.length > 1 ? "s" : ""}</div>
                    {page.comments.map((c) => (
                      <div className="nt-comment" key={c.id}>
                        <span className="nt-comment-a">{c.author?.name || "someone"}</span>
                        <span className="nt-comment-b"><RichText parts={c.rich} /></span>
                      </div>
                    ))}
                  </div>
                )}
              </article>
            ) : (
              <div className="hint" style={{ padding: 24 }}>Select a database or page.</div>
            )}
          </main>
        </div>
      )}
    </div>
  );
}
