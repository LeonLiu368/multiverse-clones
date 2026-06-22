import { useState } from "react";
import { api } from "../../api";
import { SeedFileBar } from "../SeedFileBar";

type GaugeView = {
  meta: any;
  datasources: any[];
  dashboards: any[];
  alerts: any[];
  log_queries: Record<string, { ts: string; labels?: Record<string, string>; line: string }[]>;
  metric_queries: Record<string, any>;
};

const levelClass = (lvl?: string) =>
  ({ error: "lv-error", warn: "lv-warn", warning: "lv-warn", info: "lv-info", debug: "lv-debug" }[
    (lvl || "").toLowerCase()
  ] ?? "lv-info");

export function GaugeApp({ appId }: { appId: string }) {
  const [v, setV] = useState<GaugeView | null>(null);
  const [sel, setSel] = useState<string>("");
  const [dash, setDash] = useState<any | null>(null);

  async function load() {
    const data: GaugeView = await api.view(appId);
    setV(data);
    const first = Object.keys(data.log_queries)[0] ?? "";
    setSel(first);
    setDash(null);
  }

  return (
    <div className="gauge">
      <SeedFileBar appId={appId} pathHint="path to a gauge state.json" onLoaded={load} />
      {!v ? (
        <div className="empty-state">Load a gauge <b>state.json</b> to inspect its log streams, dashboards and datasources.</div>
      ) : (
        <div className="gauge-body">
          <aside className="g-side">
            <div className="g-section">Datasources</div>
            <ul className="g-list">
              {v.datasources.map((d) => (
                <li key={d.uid} className="g-ds">
                  <span className={`g-dot ds-${d.type}`} />
                  {d.name} <span className="g-muted">{d.type}</span>
                </li>
              ))}
            </ul>
            <div className="g-section">Log streams</div>
            <ul className="g-list">
              {Object.entries(v.log_queries).map(([q, lines]) => (
                <li
                  key={q}
                  className={`g-item ${!dash && sel === q ? "active" : ""}`}
                  onClick={() => {
                    setSel(q);
                    setDash(null);
                  }}
                >
                  <code className="g-q">{q}</code>
                  <span className="count">{lines.length}</span>
                </li>
              ))}
            </ul>
            <div className="g-section">Dashboards</div>
            <ul className="g-list">
              {v.dashboards.map((d) => (
                <li key={d.uid} className={`g-item ${dash === d ? "active" : ""}`} onClick={() => setDash(d)}>
                  📊 {d.title}
                  <span className="count">{(d.panels || []).length}</span>
                </li>
              ))}
            </ul>
          </aside>

          <main className="g-main">
            {dash ? (
              <div className="g-dash">
                <h2 className="g-title">📊 {dash.title}</h2>
                <div className="g-sub">{dash.folder} · {(dash.tags || []).join(", ")}</div>
                {(dash.panels || []).map((p: any) => (
                  <div className="g-panel" key={p.id}>
                    <div className="g-panel-head">
                      <b>{p.title}</b> <span className="badge">{p.type}</span>
                    </div>
                    {(p.targets || []).map((t: any, i: number) => (
                      <code className="g-expr" key={i}>{t.expr}</code>
                    ))}
                  </div>
                ))}
              </div>
            ) : (
              <div className="g-logs">
                <div className="g-logs-head">
                  <code className="g-q">{sel}</code>
                  <span className="g-muted">{(v.log_queries[sel] || []).length} lines</span>
                </div>
                {(v.log_queries[sel] || []).map((l, i) => (
                  <div className={`g-line ${levelClass(l.labels?.level)}`} key={i}>
                    <span className="g-ts">{l.ts}</span>
                    <span className="g-lvl">{l.labels?.level ?? ""}</span>
                    <span className="g-text">{l.line}</span>
                  </div>
                ))}
                {!(v.log_queries[sel] || []).length && <div className="hint">No log lines.</div>}
              </div>
            )}
          </main>
        </div>
      )}
    </div>
  );
}
