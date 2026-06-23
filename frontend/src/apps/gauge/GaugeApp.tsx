import { useState } from "react";
import { api } from "../../api";
import { SeedFileBar } from "../SeedFileBar";

type LogLine = { ts: string; labels?: Record<string, string>; line: string; origin?: string };
type Series = { metric: Record<string, string>; values: [string | number, number | string][] };
type GaugeView = {
  meta: any;
  datasources: any[];
  dashboards: any[];
  alerts: any[];
  log_queries: Record<string, LogLine[]>;
  metric_queries: Record<string, Series[]>;
};
type Sel = { kind: "log" | "metric" | "dash"; key: string };

const levelClass = (lvl?: string) =>
  ({ error: "lv-error", warn: "lv-warn", warning: "lv-warn", info: "lv-info", debug: "lv-debug" }[
    (lvl || "").toLowerCase()
  ] ?? "lv-info");

function metricLabel(m: Record<string, string>) {
  const name = m.__name__ || "";
  const rest = Object.entries(m).filter(([k]) => k !== "__name__");
  return name + (rest.length ? `{${rest.map(([k, val]) => `${k}="${val}"`).join(", ")}}` : "");
}

function Sparkline({ values }: { values: [string | number, number | string][] }) {
  const nums = values.map((v) => Number(v[1])).filter((n) => Number.isFinite(n));
  if (nums.length < 2) return <span className="g-muted">{nums.length ? nums[0] : "—"}</span>;
  const W = 240, H = 36, min = Math.min(...nums), max = Math.max(...nums), span = max - min || 1;
  const pts = nums
    .map((n, i) => `${(i / (nums.length - 1)) * W},${H - ((n - min) / span) * (H - 4) - 2}`)
    .join(" ");
  return (
    <svg className="g-spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      <polyline points={pts} fill="none" stroke="#e6522c" strokeWidth="1.5" />
    </svg>
  );
}

export function GaugeApp({ appId }: { appId: string }) {
  const [v, setV] = useState<GaugeView | null>(null);
  const [sel, setSel] = useState<Sel | null>(null);

  async function load() {
    const data: GaugeView = await api.view(appId);
    setV(data);
    const log0 = Object.keys(data.log_queries)[0];
    const metric0 = Object.keys(data.metric_queries)[0];
    setSel(log0 ? { kind: "log", key: log0 } : metric0 ? { kind: "metric", key: metric0 } : null);
  }

  const dash = sel?.kind === "dash" ? v?.dashboards.find((d) => d.uid === sel.key) : null;

  return (
    <div className="gauge">
      <SeedFileBar
        appId={appId}
        accept=".json,application/json"
        onLoaded={load}
        allowPull
        allowOverlay
        pullHint="ghcr.io/abundant-ai/gauge-gateway:<dataset>"
      />
      {!v ? (
        <div className="empty-state">Load a gauge <b>state.json</b> to inspect its logs (Loki), metrics (Prometheus), dashboards and datasources.</div>
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

            <div className="g-section">Log streams (Loki)</div>
            <ul className="g-list">
              {Object.entries(v.log_queries).map(([q, lines]) => (
                <li
                  key={q}
                  className={`g-item ${sel?.kind === "log" && sel.key === q ? "active" : ""}`}
                  onClick={() => setSel({ kind: "log", key: q })}
                >
                  <code className="g-q">{q}</code>
                  <span className="count">{lines.length}</span>
                </li>
              ))}
              {!Object.keys(v.log_queries).length && <li className="g-empty">none</li>}
            </ul>

            <div className="g-section">Metrics (Prometheus)</div>
            <ul className="g-list">
              {Object.entries(v.metric_queries).map(([expr, series]) => (
                <li
                  key={expr}
                  className={`g-item ${sel?.kind === "metric" && sel.key === expr ? "active" : ""}`}
                  onClick={() => setSel({ kind: "metric", key: expr })}
                >
                  <code className="g-q g-promql">{expr}</code>
                  <span className="count">{series.length}</span>
                </li>
              ))}
              {!Object.keys(v.metric_queries).length && <li className="g-empty">none</li>}
            </ul>

            <div className="g-section">Dashboards</div>
            <ul className="g-list">
              {v.dashboards.map((d) => (
                <li
                  key={d.uid}
                  className={`g-item ${sel?.kind === "dash" && sel.key === d.uid ? "active" : ""}`}
                  onClick={() => setSel({ kind: "dash", key: d.uid })}
                >
                  📊 {d.title}
                  <span className="count">{(d.panels || []).length}</span>
                </li>
              ))}
            </ul>
          </aside>

          <main className="g-main">
            {sel?.kind === "dash" && dash ? (
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
            ) : sel?.kind === "metric" ? (
              <div className="g-metrics">
                <div className="g-logs-head">
                  <code className="g-q g-promql">{sel.key}</code>
                  <span className="g-muted">{(v.metric_queries[sel.key] || []).length} series</span>
                </div>
                {(v.metric_queries[sel.key] || []).map((s, i) => {
                  const nums = s.values.map((x) => Number(x[1])).filter(Number.isFinite);
                  const last = nums.length ? nums[nums.length - 1] : null;
                  return (
                    <div className="g-series" key={i}>
                      <div className="g-series-h">
                        <code className="g-metric-label">{metricLabel(s.metric)}</code>
                        <Sparkline values={s.values} />
                        <span className="g-series-stat">
                          last <b>{last ?? "—"}</b>
                          {nums.length ? <> · min {Math.min(...nums)} · max {Math.max(...nums)}</> : null}
                        </span>
                      </div>
                      <div className="g-points">
                        {s.values.map((pt, j) => (
                          <span className="g-point" key={j}>
                            <span className="g-pt-ts">{String(pt[0])}</span> {String(pt[1])}
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })}
                {!(v.metric_queries[sel.key] || []).length && <div className="hint">No series.</div>}
              </div>
            ) : sel?.kind === "log" ? (
              <div className="g-logs">
                <div className="g-logs-head">
                  <code className="g-q">{sel.key}</code>
                  <span className="g-muted">{(v.log_queries[sel.key] || []).length} lines</span>
                </div>
                {(v.log_queries[sel.key] || []).map((l, i) => (
                  <div className={`g-line ${levelClass(l.labels?.level)} ${l.origin === "overlay" ? "g-overlay" : ""}`} key={i}>
                    <span className="g-ts">{l.ts}</span>
                    <span className="g-lvl">{l.labels?.level ?? ""}</span>
                    <span className="g-text">{l.line}</span>
                    {l.origin === "overlay" && <span className="g-ovtag">overlay</span>}
                  </div>
                ))}
                {!(v.log_queries[sel.key] || []).length && <div className="hint">No log lines.</div>}
              </div>
            ) : (
              <div className="hint" style={{ padding: 20 }}>Select a log stream, metric or dashboard.</div>
            )}
          </main>
        </div>
      )}
    </div>
  );
}
