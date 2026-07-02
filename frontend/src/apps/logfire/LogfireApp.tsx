import { useMemo, useState } from "react";
import { api } from "../../api";
import { SeedFileBar } from "../SeedFileBar";

type Attr = { key: string; value: any };
type Span = {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  name: string;
  message: string;
  level: number;
  level_name: string;
  service_name: string;
  start_timestamp?: string;
  duration_ms: number;
  is_exception: boolean;
  exception_type?: string | null;
  exception_message?: string | null;
  exception_stacktrace?: string | null;
  http_method?: string | null;
  http_route?: string | null;
  http_status_code?: number | null;
  http_url?: string | null;
  kind?: string | null;
  otel_status_code?: string | null;
  attributes: Attr[];
  depth?: number;
  offset_ms?: number;
};
type Trace = {
  trace_id: string;
  root_name: string;
  service_name: string;
  start_timestamp?: string;
  duration_ms: number;
  span_count: number;
  error_count: number;
  level: number;
  level_name: string;
  spans: Span[];
};
type LogfireView = {
  records: Span[];
  traces: Trace[];
  services: string[];
  stats: { records: number; traces: number; services: number; errors: number; exceptions: number };
};

const LEVELS = ["trace", "debug", "info", "warn", "error", "fatal"];
const lvlClass = (l: string) => `lf-lvl-${l}`;

function fmtDur(ms: number) {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  if (ms >= 1) return `${ms.toFixed(ms < 10 ? 1 : 0)}ms`;
  return `${(ms * 1000).toFixed(0)}µs`;
}
function fmtTime(ts?: string) {
  if (!ts) return "";
  const d = new Date(ts.replace(" ", "T"));
  return isNaN(+d) ? ts : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function LogfireApp({ appId }: { appId: string }) {
  const [v, setV] = useState<LogfireView | null>(null);
  const [mode, setMode] = useState<"traces" | "records">("traces");
  const [selTrace, setSelTrace] = useState<string>("");
  const [selSpan, setSelSpan] = useState<string>("");
  const [minLevel, setMinLevel] = useState<number>(0);
  const [service, setService] = useState<string>("");
  const [q, setQ] = useState<string>("");

  async function load() {
    const data: LogfireView = await api.view(appId);
    setV(data);
    const t = data.traces[0];
    setMode("traces");
    setSelTrace(t?.trace_id ?? "");
    setSelSpan(t?.spans[0]?.span_id ?? "");
  }

  const matches = (s: Span) =>
    s.level >= minLevel &&
    (!service || s.service_name === service) &&
    (!q ||
      `${s.name} ${s.message} ${s.exception_type ?? ""} ${s.http_route ?? ""}`
        .toLowerCase()
        .includes(q.toLowerCase()));

  const traces = useMemo(
    () => (v ? v.traces.filter((t) => t.spans.some(matches)) : []),
    [v, minLevel, service, q]
  );
  const records = useMemo(() => (v ? v.records.filter(matches) : []), [v, minLevel, service, q]);

  const trace = v?.traces.find((t) => t.trace_id === selTrace) ?? null;
  const span =
    trace?.spans.find((s) => s.span_id === selSpan) ??
    v?.records.find((s) => s.span_id === selSpan) ??
    null;

  function openSpan(s: Span) {
    setSelTrace(s.trace_id);
    setSelSpan(s.span_id);
  }

  return (
    <div className="logfire">
      <SeedFileBar
        appId={appId}
        accept=".json,application/json"
        onLoaded={load}
        allowPull
        pullHint="ghcr.io/abundant-ai/logfire-gateway:<incident>"
      />
      {!v ? (
        <div className="empty-state">
          Load a Logfire <b>records.json</b> to explore traces, spans and exceptions.
        </div>
      ) : (
        <div className="lf-body">
          {/* ---------- left: live feed (traces / records) ---------- */}
          <aside className="lf-left">
            <div className="lf-toolbar">
              <div className="lf-seg">
                <button className={mode === "traces" ? "on" : ""} onClick={() => setMode("traces")}>
                  Traces
                </button>
                <button className={mode === "records" ? "on" : ""} onClick={() => setMode("records")}>
                  Records
                </button>
              </div>
              <input
                className="lf-search"
                placeholder="Search spans…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
              <div className="lf-filters">
                <select value={minLevel} onChange={(e) => setMinLevel(Number(e.target.value))}>
                  <option value={0}>all levels</option>
                  <option value={9}>info+</option>
                  <option value={13}>warn+</option>
                  <option value={17}>error+</option>
                </select>
                <select value={service} onChange={(e) => setService(e.target.value)}>
                  <option value="">all services</option>
                  {v.services.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="lf-feed">
              {mode === "traces"
                ? traces.map((t) => (
                    <div
                      key={t.trace_id}
                      className={`lf-trace-row ${t.trace_id === selTrace ? "sel" : ""}`}
                      onClick={() => {
                        setSelTrace(t.trace_id);
                        setSelSpan(t.spans[0]?.span_id ?? "");
                      }}
                    >
                      <span className={`lf-dot ${lvlClass(t.level_name)}`} />
                      <div className="lf-trace-main">
                        <div className="lf-trace-name">{t.root_name}</div>
                        <div className="lf-trace-sub">
                          <span className="lf-svc">{t.service_name}</span>
                          <span className="lf-spans">{t.span_count} spans</span>
                          {t.error_count > 0 && <span className="lf-errc">{t.error_count} error</span>}
                        </div>
                      </div>
                      <span className="lf-dur">{fmtDur(t.duration_ms)}</span>
                    </div>
                  ))
                : records.map((s) => (
                    <div
                      key={s.span_id}
                      className={`lf-rec-row ${s.span_id === selSpan ? "sel" : ""}`}
                      onClick={() => openSpan(s)}
                    >
                      <span className={`lf-pill ${lvlClass(s.level_name)}`}>{s.level_name}</span>
                      <div className="lf-rec-main">
                        <div className="lf-rec-name">
                          {s.is_exception && <span className="lf-exc-ic">⚠</span>}
                          {s.name}
                        </div>
                        <div className="lf-rec-sub">
                          <span className="lf-svc">{s.service_name}</span>
                          <span>{fmtTime(s.start_timestamp)}</span>
                        </div>
                      </div>
                      <span className="lf-dur">{fmtDur(s.duration_ms)}</span>
                    </div>
                  ))}
              {(mode === "traces" ? traces : records).length === 0 && (
                <div className="hint" style={{ padding: 16 }}>
                  No spans match the filter.
                </div>
              )}
            </div>
          </aside>

          {/* ---------- center: trace waterfall ---------- */}
          <main className="lf-center">
            {trace ? (
              <>
                <div className="lf-trace-head">
                  <h2>{trace.root_name}</h2>
                  <div className="lf-trace-meta">
                    <code className="lf-tid">trace {trace.trace_id}</code>
                    <span>{fmtDur(trace.duration_ms)}</span>
                    <span>{trace.span_count} spans</span>
                    {trace.error_count > 0 && (
                      <span className="lf-errc">{trace.error_count} error</span>
                    )}
                  </div>
                </div>
                <div className="lf-waterfall">
                  <div className="lf-waxis">
                    <div className="lf-wlabel lf-waxis-label">Span</div>
                    <div className="lf-wtrack">
                      {[0, 0.25, 0.5, 0.75, 1].map((f, i) => (
                        <span className="lf-tick" key={i} style={{ left: `${f * 100}%` }}>
                          {fmtDur((trace.duration_ms || 0) * f)}
                        </span>
                      ))}
                    </div>
                  </div>
                  {trace.spans.map((s) => {
                    const max = trace.duration_ms || 1;
                    const left = Math.min(((s.offset_ms ?? 0) / max) * 100, 99);
                    const width = Math.max((s.duration_ms / max) * 100, 0.8);
                    const labelRight = left > 62; // put the duration before the bar when it's far right
                    return (
                      <div
                        key={s.span_id}
                        className={`lf-wrow ${s.span_id === selSpan ? "sel" : ""}`}
                        onClick={() => setSelSpan(s.span_id)}
                      >
                        <div className="lf-wlabel" style={{ paddingLeft: 10 + (s.depth ?? 0) * 14 }}>
                          <span className={`lf-dot ${lvlClass(s.level_name)}`} />
                          {s.is_exception && <span className="lf-exc-ic">⚠</span>}
                          <span className="lf-wname">{s.name}</span>
                          <span className="lf-wsvc">{s.service_name}</span>
                        </div>
                        <div className="lf-wtrack">
                          <div
                            className={`lf-wbar ${lvlClass(s.level_name)} ${s.is_exception ? "exc" : ""}`}
                            style={{ left: `${left}%`, width: `${width}%` }}
                            title={`${s.name} · ${fmtDur(s.duration_ms)}`}
                          />
                          <span
                            className={`lf-wdur ${labelRight ? "before" : ""}`}
                            style={labelRight ? { right: `${100 - left + 1}%` } : { left: `${Math.min(left + width + 1, 90)}%` }}
                          >
                            {fmtDur(s.duration_ms)}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            ) : (
              <div className="hint" style={{ padding: 24 }}>
                Select a trace to see its waterfall.
              </div>
            )}
          </main>

          {/* ---------- right: span detail ---------- */}
          <aside className="lf-right">
            {span ? (
              <div className="lf-detail">
                <div className="lf-d-head">
                  <span className={`lf-pill ${lvlClass(span.level_name)}`}>{span.level_name}</span>
                  <span className="lf-d-name">{span.name}</span>
                </div>
                <div className="lf-d-svc">{span.service_name}</div>

                {span.exception_type && (
                  <div className="lf-exc">
                    <div className="lf-exc-h">
                      {span.exception_type}: {span.exception_message}
                    </div>
                    {span.exception_stacktrace && (
                      <pre className="lf-stack">{span.exception_stacktrace}</pre>
                    )}
                  </div>
                )}

                <div className="lf-d-grid">
                  <span>duration</span>
                  <b>{fmtDur(span.duration_ms)}</b>
                  <span>start</span>
                  <b>{span.start_timestamp ?? "—"}</b>
                  {span.kind && (
                    <>
                      <span>kind</span>
                      <b>{span.kind}</b>
                    </>
                  )}
                  {span.otel_status_code && (
                    <>
                      <span>status</span>
                      <b>{span.otel_status_code}</b>
                    </>
                  )}
                </div>

                {(span.http_method || span.http_status_code) && (
                  <>
                    <div className="lf-d-label">HTTP</div>
                    <div className="lf-d-grid">
                      <span>method</span>
                      <b>{span.http_method ?? "—"}</b>
                      <span>route</span>
                      <b>{span.http_route ?? "—"}</b>
                      <span>status</span>
                      <b
                        className={
                          (span.http_status_code ?? 0) >= 500
                            ? "lf-http-5xx"
                            : (span.http_status_code ?? 0) >= 400
                            ? "lf-http-4xx"
                            : "lf-http-2xx"
                        }
                      >
                        {span.http_status_code ?? "—"}
                      </b>
                      {span.http_url && (
                        <>
                          <span>url</span>
                          <b className="lf-d-url">{span.http_url}</b>
                        </>
                      )}
                    </div>
                  </>
                )}

                <div className="lf-d-label">IDs</div>
                <div className="lf-d-grid lf-d-mono">
                  <span>trace</span>
                  <b>{span.trace_id}</b>
                  <span>span</span>
                  <b>{span.span_id}</b>
                  {span.parent_span_id && (
                    <>
                      <span>parent</span>
                      <b>{span.parent_span_id}</b>
                    </>
                  )}
                </div>

                {span.attributes.length > 0 && (
                  <>
                    <div className="lf-d-label">Attributes</div>
                    <div className="lf-attrs">
                      {span.attributes.map((a) => (
                        <div className="lf-attr" key={a.key}>
                          <span className="lf-attr-k">{a.key}</span>
                          <span className="lf-attr-v">{String(a.value)}</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            ) : (
              <div className="hint" style={{ padding: 24 }}>
                Select a span.
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
