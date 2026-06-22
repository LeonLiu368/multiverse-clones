import { useState } from "react";
import { api } from "../../api";
import { SeedFileBar } from "../SeedFileBar";

type Frame = { filename: string; function?: string; lineno?: number; context?: string };
type SentryEvent = {
  id: string;
  timestamp?: string;
  message?: string;
  tags?: Record<string, string>;
  exception?: { type?: string; value?: string; stacktrace?: Frame[] };
};
type Issue = {
  id: string;
  shortId?: string;
  title: string;
  culprit?: string;
  level?: string;
  status?: string;
  count?: number;
  userCount?: number;
  firstSeen?: string;
  lastSeen?: string;
  tags?: Record<string, string>;
  events?: SentryEvent[];
};
type SentryView = { org: string; project: string; issues: Issue[] };

export function SentryApp({ appId }: { appId: string }) {
  const [v, setV] = useState<SentryView | null>(null);
  const [sel, setSel] = useState<string>("");

  async function load() {
    const data: SentryView = await api.view(appId);
    setV(data);
    setSel(data.issues[0]?.id ?? "");
  }

  const active = v?.issues.find((i) => i.id === sel) ?? null;

  return (
    <div className="sentry">
      <SeedFileBar appId={appId} accept=".json,application/json" onLoaded={load} />
      {!v ? (
        <div className="empty-state">Load a Sentry <b>state.json</b> to inspect its issues and events.</div>
      ) : (
        <div className="sentry-body">
          <aside className="se-list">
            <div className="se-head">
              {v.org}/{v.project} · {v.issues.length} issues
            </div>
            {v.issues.map((i) => (
              <div
                key={i.id}
                className={`se-row ${i.id === sel ? "sel" : ""}`}
                onClick={() => setSel(i.id)}
              >
                <span className={`se-level lv-${(i.level || "error").toLowerCase()}`}>{i.level}</span>
                <div className="se-row-body">
                  <div className="se-title">{i.title}</div>
                  <div className="se-meta">
                    {i.culprit} · {i.count ?? 0} events · {i.userCount ?? 0} users
                    <span className={`se-status st-${i.status}`}>{i.status}</span>
                  </div>
                </div>
              </div>
            ))}
          </aside>

          <main className="se-detail">
            {active && (
              <>
                <div className="se-key">{active.shortId ?? active.id}</div>
                <h2 className="se-h">{active.title}</h2>
                <div className="se-tags">
                  {Object.entries(active.tags || {}).map(([k, val]) => (
                    <span className="se-tag" key={k}>
                      {k}: {val}
                    </span>
                  ))}
                </div>
                {(active.events || []).map((ev) => (
                  <div className="se-event" key={ev.id}>
                    <div className="se-event-head">
                      <b>{ev.exception?.type ?? "event"}</b>: {ev.exception?.value ?? ev.message}
                      <span className="se-ts">{ev.timestamp}</span>
                    </div>
                    {ev.exception?.stacktrace?.length ? (
                      <div className="se-trace">
                        {ev.exception.stacktrace.map((f, i) => (
                          <div className="se-frame" key={i}>
                            <span className="se-loc">
                              {f.filename}
                              {f.function ? ` in ${f.function}` : ""}
                              {f.lineno ? `:${f.lineno}` : ""}
                            </span>
                            {f.context && <code className="se-ctx">{f.context}</code>}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}
              </>
            )}
          </main>
        </div>
      )}
    </div>
  );
}
