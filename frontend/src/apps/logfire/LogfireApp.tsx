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

const CAP = 300; // rows rendered before we truncate (the :testing corpus has 4.5k traces)

function fmtDur(ms: number) {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  if (ms >= 1) return `${ms.toFixed(ms < 10 ? 1 : 0)}ms`;
  if (ms > 0) return `${(ms * 1000).toFixed(0)}µs`;
  return "";
}
function fmtClock(ts?: string) {
  if (!ts) return "";
  const d = new Date(ts.replace(" ", "T"));
  if (isNaN(+d)) return ts.slice(11, 23);
  const p = (n: number, w = 2) => String(n).padStart(w, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`;
}

// Logfire-style level glyph: dot for trace/debug/info, triangle for warn, ringed dot for error+.
function LevelIcon({ level }: { level: string }) {
  if (level === "warn") return <span className="lfx-ic lfx-ic-warn" title="warn" />;
  if (level === "error" || level === "fatal")
    return <span className={`lfx-ic lfx-ic-${level}`} title={level} />;
  return <span className={`lfx-ic lfx-ic-dot lfx-${level}`} title={level} />;
}

function SpanRow({
  s,
  trace,
  isRoot,
  expanded,
  onToggle,
  selected,
  onSelect,
}: {
  s: Span;
  trace: Trace;
  isRoot: boolean;
  expanded: boolean;
  onToggle: () => void;
  selected: boolean;
  onSelect: () => void;
}) {
  const total = trace.duration_ms || 1;
  const left = Math.min(((s.offset_ms ?? 0) / total) * 100, 97);
  const width = Math.max((s.duration_ms / total) * 100, 2);
  const canExpand = isRoot && trace.span_count > 1;
  return (
    <div
      className={`lfx-row ${selected ? "sel" : ""} ${isRoot ? "root" : "child"}`}
      onClick={onSelect}
    >
      <span
        className={`lfx-chev ${canExpand ? "" : "hidden"} ${expanded ? "open" : ""}`}
        onClick={(e) => {
          e.stopPropagation();
          if (canExpand) onToggle();
        }}
      >
        ▸
      </span>
      <span className="lfx-ts">{fmtClock(s.start_timestamp)}</span>
      <LevelIcon level={s.level_name} />
      <span className="lfx-msg" style={{ paddingLeft: (s.depth ?? 0) * 14 }}>
        {(s.depth ?? 0) > 0 && <span className="lfx-guide" />}
        {s.is_exception && <span className="lfx-exc">⚠</span>}
        {s.message || s.name}
      </span>
      {s.http_status_code != null && (
        <span
          className={`lfx-http ${
            s.http_status_code >= 500 ? "s5" : s.http_status_code >= 400 ? "s4" : "s2"
          }`}
        >
          {s.http_status_code}
        </span>
      )}
      <span className="lfx-svc">{s.service_name}</span>
      <span className="lfx-track">
        <span className={`lfx-bar lfx-${s.level_name}`} style={{ left: `${left}%`, width: `${width}%` }} />
      </span>
      <span className="lfx-dur">{fmtDur(s.duration_ms)}</span>
    </div>
  );
}

export function LogfireApp({ appId }: { appId: string }) {
  const [v, setV] = useState<LogfireView | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selSpan, setSelSpan] = useState<string>("");
  const [minLevel, setMinLevel] = useState<number>(0);
  const [service, setService] = useState<string>("");
  const [q, setQ] = useState<string>("");

  async function load() {
    const data: LogfireView = await api.view(appId);
    setV(data);
    setExpanded(new Set(data.traces[0] ? [data.traces[0].trace_id] : []));
    setSelSpan(data.traces[0]?.spans[0]?.span_id ?? "");
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

  const span = useMemo(() => {
    if (!v) return null;
    for (const t of v.traces) for (const s of t.spans) if (s.span_id === selSpan) return s;
    return null;
  }, [v, selSpan]);
  const selTrace = span ? v?.traces.find((t) => t.trace_id === span.trace_id) : null;

  function toggle(tid: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(tid) ? next.delete(tid) : next.add(tid);
      return next;
    });
  }

  // Build the visible row list (roots + expanded children), capped.
  const rows: { s: Span; trace: Trace; isRoot: boolean }[] = [];
  for (const t of traces) {
    if (rows.length >= CAP) break;
    rows.push({ s: t.spans[0], trace: t, isRoot: true });
    if (expanded.has(t.trace_id))
      for (const s of t.spans.slice(1)) {
        if (rows.length >= CAP) break;
        rows.push({ s, trace: t, isRoot: false });
      }
  }

  return (
    <div className="logfire">
      <SeedFileBar
        appId={appId}
        accept=".json,application/json,.gz"
        onLoaded={load}
        allowPull
        pullHint="ghcr.io/abundant-ai/logfire-service:prod-v1"
      />
      {!v ? (
        <div className="empty-state">
          Load a Logfire <b>records.json</b> to explore traces, spans and exceptions.
        </div>
      ) : (
        <div className="lfx-body">
          <div className="lfx-main">
            <div className="lfx-toolbar">
              <span className="lfx-live">
                <span className="lfx-live-dot" /> Live
              </span>
              <div className="lfx-query">
                <span className="lfx-where">WHERE</span>
                <input
                  placeholder="message ~ 'timeout' — filter spans…"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  spellCheck={false}
                />
              </div>
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

            <div className="lfx-list">
              <div className="lfx-head">
                <span className="lfx-chev hidden">▸</span>
                <span className="lfx-ts">Time</span>
                <span style={{ width: 12 }} />
                <span className="lfx-msg">Message</span>
                <span className="lfx-svc">Service</span>
                <span className="lfx-track" />
                <span className="lfx-dur">Duration</span>
              </div>
              {rows.map(({ s, trace, isRoot }) => (
                <SpanRow
                  key={s.span_id}
                  s={s}
                  trace={trace}
                  isRoot={isRoot}
                  expanded={expanded.has(trace.trace_id)}
                  onToggle={() => toggle(trace.trace_id)}
                  selected={s.span_id === selSpan}
                  onSelect={() => setSelSpan(s.span_id)}
                />
              ))}
              {rows.length >= CAP && (
                <div className="lfx-truncated">
                  showing first {CAP} rows of {traces.length} traces — narrow the filter to see more
                </div>
              )}
              {!rows.length && <div className="hint" style={{ padding: 16 }}>No spans match.</div>}
            </div>
          </div>

          {span && (
            <aside className="lfx-detail">
              <div className="lfx-d-top">
                <LevelIcon level={span.level_name} />
                <span className="lfx-d-name">{span.name}</span>
              </div>
              <div className="lfx-d-sub">
                <span className="lfx-svc">{span.service_name}</span>
                <span className="lfx-d-time">{fmtClock(span.start_timestamp)}</span>
                <span className="lfx-d-dur">{fmtDur(span.duration_ms)}</span>
              </div>

              {selTrace && selTrace.span_count > 1 && (
                <div className="lfx-mini">
                  {selTrace.spans.map((s) => {
                    const total = selTrace.duration_ms || 1;
                    return (
                      <div
                        key={s.span_id}
                        className={`lfx-mini-row ${s.span_id === selSpan ? "sel" : ""}`}
                        onClick={() => setSelSpan(s.span_id)}
                        title={`${s.name} · ${fmtDur(s.duration_ms)}`}
                      >
                        <span className="lfx-mini-name" style={{ paddingLeft: (s.depth ?? 0) * 10 }}>
                          {s.name}
                        </span>
                        <span className="lfx-mini-track">
                          <span
                            className={`lfx-bar lfx-${s.level_name}`}
                            style={{
                              left: `${Math.min(((s.offset_ms ?? 0) / total) * 100, 96)}%`,
                              width: `${Math.max((s.duration_ms / total) * 100, 2.5)}%`,
                            }}
                          />
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}

              {span.exception_type && (
                <div className="lfx-excbox">
                  <div className="lfx-excbox-h">
                    {span.exception_type}: {span.exception_message}
                  </div>
                  {span.exception_stacktrace && (
                    <pre className="lfx-stack">{span.exception_stacktrace}</pre>
                  )}
                </div>
              )}

              {(span.http_method || span.http_status_code != null) && (
                <>
                  <div className="lfx-d-label">HTTP</div>
                  <div className="lfx-kv">
                    <span>method</span><b>{span.http_method ?? "—"}</b>
                    <span>route</span><b>{span.http_route ?? "—"}</b>
                    <span>status</span>
                    <b>
                      <span
                        className={`lfx-http ${
                          (span.http_status_code ?? 0) >= 500
                            ? "s5"
                            : (span.http_status_code ?? 0) >= 400
                            ? "s4"
                            : "s2"
                        }`}
                      >
                        {span.http_status_code ?? "—"}
                      </span>
                    </b>
                    {span.http_url && (
                      <>
                        <span>url</span><b className="lfx-mono">{span.http_url}</b>
                      </>
                    )}
                  </div>
                </>
              )}

              <div className="lfx-d-label">Span</div>
              <div className="lfx-kv lfx-kv-mono">
                <span>trace</span><b>{span.trace_id}</b>
                <span>span</span><b>{span.span_id}</b>
                {span.parent_span_id && (
                  <>
                    <span>parent</span><b>{span.parent_span_id}</b>
                  </>
                )}
                {span.kind && (
                  <>
                    <span>kind</span><b>{span.kind}</b>
                  </>
                )}
                {span.otel_status_code && (
                  <>
                    <span>otel</span><b>{span.otel_status_code}</b>
                  </>
                )}
              </div>

              {span.attributes.length > 0 && (
                <>
                  <div className="lfx-d-label">Attributes</div>
                  <div className="lfx-attrs">
                    {span.attributes.map((a) => (
                      <div className="lfx-attr" key={a.key}>
                        <span className="lfx-attr-k">{a.key}</span>
                        <span className="lfx-attr-v">{String(a.value)}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </aside>
          )}
        </div>
      )}
    </div>
  );
}
