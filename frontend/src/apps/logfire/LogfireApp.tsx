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
  start_epoch?: number | null;
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
  duration_ms: number;
  span_count: number;
  error_count: number;
  spans: Span[];
};
type LogfireView = {
  records: Span[];
  traces: Trace[];
  services: string[];
  stats: { records: number; traces: number; services: number; errors: number; exceptions: number };
};

const CAP = 300;

function fmtDur(ms: number) {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  if (ms >= 1) return `${ms.toFixed(ms < 10 ? 1 : 0)}ms`;
  if (ms > 0) return `${(ms * 1000).toFixed(0)}µs`;
  return "";
}
function fmtClock(ts?: string | number | null) {
  if (ts == null || ts === "") return "";
  const d = typeof ts === "number" ? new Date(ts * 1000) : new Date(String(ts).replace(" ", "T"));
  if (isNaN(+d)) return String(ts).slice(11, 19);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
function fmtWindow(ms: number) {
  if (ms >= 3600_000) return `${(ms / 3600_000).toFixed(1)}h`;
  if (ms >= 60_000) return `${Math.round(ms / 60_000)}m`;
  return `${Math.max(1, Math.round(ms / 1000))}s`;
}

function LevelIcon({ level }: { level: string }) {
  if (level === "warn") return <span className="lfx-ic lfx-ic-warn" title="warn" />;
  if (level === "error" || level === "fatal")
    return <span className={`lfx-ic lfx-ic-${level}`} title={level} />;
  return <span className={`lfx-ic lfx-ic-dot lfx-${level}`} title={level} />;
}

// The level-stacked count-over-time histogram that sits above Logfire's live feed.
function Histogram({ spans }: { spans: Span[] }) {
  const data = useMemo(() => {
    const ts = spans.map((s) => s.start_epoch).filter((x): x is number => x != null);
    if (ts.length < 2) return null;
    const min = Math.min(...ts), max = Math.max(...ts);
    const span = Math.max(max - min, 1e-6);
    const N = 60;
    const buckets = Array.from({ length: N }, () => ({ info: 0, warn: 0, error: 0 }));
    for (const s of spans) {
      if (s.start_epoch == null) continue;
      const i = Math.min(N - 1, Math.floor(((s.start_epoch - min) / span) * N));
      if (s.level >= 17) buckets[i].error++;
      else if (s.level >= 13) buckets[i].warn++;
      else buckets[i].info++;
    }
    const peak = Math.max(1, ...buckets.map((b) => b.info + b.warn + b.error));
    return { buckets, peak, min, max };
  }, [spans]);
  if (!data) return null;
  const { buckets, peak, min, max } = data;
  const W = 1000, H = 56, bw = W / buckets.length;
  return (
    <div className="lfx-histo">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="lfx-histo-svg">
        {buckets.map((b, i) => {
          const total = b.info + b.warn + b.error;
          if (!total) return null;
          const h = Math.max(2, (total / peak) * (H - 4));
          const x = i * bw + 1, w = Math.max(bw - 2, 2);
          const eh = (b.error / total) * h, wh = (b.warn / total) * h, ih = h - eh - wh;
          let y = H - h;
          const parts: JSX.Element[] = [];
          if (b.error) { parts.push(<rect key="e" x={x} y={y} width={w} height={eh} fill="#ef4444" />); y += eh; }
          if (b.warn) { parts.push(<rect key="w" x={x} y={y} width={w} height={wh} fill="#f5a623" />); y += wh; }
          if (b.info) { parts.push(<rect key="i" x={x} y={y} width={w} height={ih} fill="#3d5a8f" />); }
          return <g key={i}>{parts}</g>;
        })}
      </svg>
      <div className="lfx-histo-axis">
        <span>{fmtClock(min)}</span>
        <span className="lfx-histo-mid">{spans.length} records · {fmtWindow((max - min) * 1000)} window</span>
        <span>{fmtClock(max)}</span>
      </div>
    </div>
  );
}

function SpanRow({
  s, trace, isRoot, expanded, onToggle, selected, onSelect,
}: {
  s: Span; trace: Trace; isRoot: boolean; expanded: boolean;
  onToggle: () => void; selected: boolean; onSelect: () => void;
}) {
  const canExpand = isRoot && trace.span_count > 1;
  return (
    <div className={`lfx-row ${selected ? "sel" : ""} ${isRoot ? "" : "child"}`} onClick={onSelect}>
      <span
        className={`lfx-chev ${canExpand ? "" : "hidden"} ${expanded ? "open" : ""}`}
        onClick={(e) => { e.stopPropagation(); if (canExpand) onToggle(); }}
      >
        ▸
      </span>
      <span className="lfx-indent" style={{ width: (s.depth ?? 0) * 16 }} />
      <LevelIcon level={s.level_name} />
      <span className="lfx-msg">
        {s.is_exception && <span className="lfx-exc">⚠</span>}
        {s.message || s.name}
      </span>
      {canExpand && !expanded && <span className="lfx-nspans">{trace.span_count} spans</span>}
      {s.http_status_code != null && (
        <span className={`lfx-http ${s.http_status_code >= 500 ? "s5" : s.http_status_code >= 400 ? "s4" : "s2"}`}>
          {s.http_status_code}
        </span>
      )}
      <span className="lfx-svc">{s.service_name}</span>
      {s.duration_ms > 0 && <span className="lfx-durchip">{fmtDur(s.duration_ms)}</span>}
      <span className="lfx-ts">{fmtClock(s.start_timestamp)}</span>
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
  const [nav, setNav] = useState<"live" | "dash" | "alerts" | "explore">("live");

  async function load() {
    const data: LogfireView = await api.view(appId);
    setV(data);
    setExpanded(new Set(data.traces[0] ? [data.traces[0].trace_id] : []));
    setSelSpan("");
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
  const filteredSpans = useMemo(() => (v ? v.records.filter(matches) : []), [v, minLevel, service, q]);

  const span = useMemo(() => {
    if (!v || !selSpan) return null;
    for (const t of v.traces) for (const s of t.spans) if (s.span_id === selSpan) return s;
    return null;
  }, [v, selSpan]);
  const selTrace = span ? v?.traces.find((t) => t.trace_id === span.trace_id) : null;
  const codeAttr = span?.attributes.find((a) => a.key === "code.filepath");
  const lineAttr = span?.attributes.find((a) => a.key === "code.lineno");

  function toggle(tid: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(tid) ? next.delete(tid) : next.add(tid);
      return next;
    });
  }

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

  const NAVS: { id: typeof nav; glyph: string; label: string }[] = [
    { id: "live", glyph: "◉", label: "Live" },
    { id: "dash", glyph: "▦", label: "Dashboards" },
    { id: "alerts", glyph: "◬", label: "Alerts" },
    { id: "explore", glyph: "⌕", label: "Explore" },
  ];

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
        <div className="lfx-shell">
          {/* icon nav rail */}
          <nav className="lfx-rail">
            <span className="lfx-flame">🔥</span>
            {NAVS.map((n) => (
              <button
                key={n.id}
                className={`lfx-rail-btn ${nav === n.id ? "on" : ""}`}
                title={n.label}
                onClick={() => setNav(n.id)}
              >
                {n.glyph}
              </button>
            ))}
          </nav>

          <div className="lfx-workspace">
            {/* project header */}
            <header className="lfx-header">
              <span className="lfx-crumb">
                <b>acme</b><span className="lfx-crumb-sep">/</span>{service || "all services"}
              </span>
              <div className="lfx-query">
                <span className="lfx-q-ic">⌕</span>
                <input
                  placeholder="Search spans — message, route, exception…"
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
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <span className="lfx-live">
                <span className="lfx-live-dot" /> Live
              </span>
            </header>

            {nav !== "live" ? (
              <div className="lfx-nyi">
                <span className="lfx-nyi-glyph">{NAVS.find((n) => n.id === nav)?.glyph}</span>
                {NAVS.find((n) => n.id === nav)?.label} isn't part of the seed viewer — the corpus
                only carries records. <button className="link" onClick={() => setNav("live")}>Back to Live</button>
              </div>
            ) : (
              <div className="lfx-live-wrap">
                <div className="lfx-feedpane">
                  <Histogram spans={filteredSpans} />
                  <div className="lfx-list">
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
                    <div className="lfx-d-bar">
                      <span className="lfx-d-kind">Span details</span>
                      <button className="lfx-d-close" onClick={() => setSelSpan("")}>✕</button>
                    </div>
                    <div className="lfx-d-top">
                      <span className="lfx-d-top-ic">
                        <LevelIcon level={span.level_name} />
                      </span>
                      <span className="lfx-d-name">{span.name}</span>
                    </div>
                    <div className="lfx-d-sub">
                      <span className="lfx-svc">{span.service_name}</span>
                      <span className="lfx-d-time">{fmtClock(span.start_timestamp)}</span>
                      {span.duration_ms > 0 && <span className="lfx-durchip">{fmtDur(span.duration_ms)}</span>}
                    </div>
                    {codeAttr && (
                      <div className="lfx-d-code">
                        {String(codeAttr.value)}{lineAttr ? `:${lineAttr.value}` : ""}
                      </div>
                    )}

                    {selTrace && selTrace.span_count > 1 && (
                      <>
                        <div className="lfx-d-label">Trace</div>
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
                      </>
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
                            <span className={`lfx-http ${(span.http_status_code ?? 0) >= 500 ? "s5" : (span.http_status_code ?? 0) >= 400 ? "s4" : "s2"}`}>
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
                      {span.parent_span_id && (<><span>parent</span><b>{span.parent_span_id}</b></>)}
                      {span.kind && (<><span>kind</span><b>{span.kind}</b></>)}
                      {span.otel_status_code && (<><span>otel</span><b>{span.otel_status_code}</b></>)}
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
        </div>
      )}
    </div>
  );
}
