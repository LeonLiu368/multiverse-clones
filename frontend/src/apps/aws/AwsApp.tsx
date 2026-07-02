import { useState } from "react";
import { api } from "../../api";
import { SeedFileBar } from "../SeedFileBar";

type Nav = { key: string; label: string; count: number };
type AView = { meta: any; services: Record<string, any>; nav: Nav[]; stats: Record<string, number> };

// AWS-console-ish service badge colors.
const SVC_COLOR: Record<string, string> = {
  s3: "#569a31", sqs: "#c925d1", sns: "#c925d1", dynamodb: "#4053d6", lambda: "#ed7100",
  kinesis: "#c925d1", eventbridge: "#c925d1", cloudwatch_logs: "#e7157b", ssm: "#e7157b",
  secretsmanager: "#dd344c", iam: "#dd344c",
};

function J({ v }: { v: any }) {
  if (v == null) return <span className="aws-muted">—</span>;
  if (typeof v !== "object")
    return <span className="aws-scalar">{typeof v === "string" ? v : String(v)}</span>;
  return <pre className="aws-json">{JSON.stringify(v, null, 2)}</pre>;
}

function KV({ obj, keys }: { obj: any; keys: [string, string][] }) {
  return (
    <div className="aws-kv">
      {keys.map(([k, label]) =>
        obj[k] != null ? (
          <div className="aws-kv-row" key={k}>
            <span className="aws-kv-k">{label}</span>
            <span className="aws-kv-v"><J v={obj[k]} /></span>
          </div>
        ) : null
      )}
    </div>
  );
}

function ResourceCard({ svc, r }: { svc: string; r: any }) {
  const [open, setOpen] = useState(false);
  const name = r.name || r.function_name || r.key || "(resource)";
  let summary: React.ReactNode = null;
  let nested: { label: string; items: any[] } | null = null;

  if (svc === "s3") {
    summary = <span className="aws-sub">{(r.objects || []).length} objects</span>;
    nested = { label: "Objects", items: r.objects || [] };
  } else if (svc === "sqs") {
    summary = <KV obj={r.attributes || {}} keys={[["VisibilityTimeout", "Visibility"], ["MessageRetentionPeriod", "Retention"]]} />;
    nested = { label: "Messages", items: r.messages || [] };
  } else if (svc === "sns") {
    nested = { label: "Subscriptions", items: r.subscriptions || [] };
  } else if (svc === "dynamodb") {
    summary = <KV obj={r} keys={[["billing_mode", "Billing"], ["key_schema", "Key schema"]]} />;
    nested = { label: "Items", items: r.items || [] };
  } else if (svc === "lambda") {
    summary = <KV obj={r} keys={[["runtime", "Runtime"], ["handler", "Handler"], ["role", "Role"], ["log_group", "Log group"]]} />;
    nested = { label: "Event source mappings", items: r.event_source_mappings || [] };
  } else if (svc === "kinesis") {
    summary = <KV obj={r} keys={[["shard_count", "Shards"], ["retention_hours", "Retention (h)"]]} />;
    nested = { label: "Records", items: r.records || [] };
  } else if (svc === "eventbridge") {
    summary = <KV obj={r} keys={[["schedule", "Schedule"]]} />;
    nested = { label: "Targets", items: r.targets || [] };
  } else if (svc === "cloudwatch_logs") {
    nested = { label: "Streams", items: r.streams || [] };
  } else if (svc === "ssm") {
    summary = <KV obj={r} keys={[["type", "Type"], ["value", "Value"]]} />;
  } else if (svc === "secretsmanager") {
    nested = { label: "Versions", items: r.versions || [] };
  }

  return (
    <div className="aws-card">
      <div className="aws-card-h" onClick={() => nested && setOpen((o) => !o)}>
        <span className={`aws-svc-dot`} style={{ background: SVC_COLOR[svc] || "#687078" }} />
        <span className="aws-card-name">{name}</span>
        {nested && <span className="aws-count-pill">{nested.items.length}</span>}
        {nested ? <span className="aws-caret">{open ? "▾" : "▸"}</span> : null}
      </div>
      {summary && <div className="aws-card-summary">{summary}</div>}
      {nested && open && (
        <div className="aws-nested">
          <div className="aws-nested-h">{nested.label}</div>
          {nested.items.length ? (
            nested.items.map((it, i) => (
              <div className="aws-nested-item" key={i}>
                <span className="aws-nested-key">{it.key || it.name || it.protocol || it.id || `#${i + 1}`}</span>
                <J v={it.body_json ?? it.attributes ?? it} />
              </div>
            ))
          ) : (
            <div className="aws-muted" style={{ padding: "4px 0" }}>none</div>
          )}
        </div>
      )}
    </div>
  );
}

export function AwsApp({ appId }: { appId: string }) {
  const [v, setV] = useState<AView | null>(null);
  const [svc, setSvc] = useState<string>("");

  async function load() {
    const data: AView = await api.view(appId);
    setV(data);
    setSvc(data.nav[0]?.key ?? "");
  }

  const iam = v?.services.iam;
  const rows = v && svc !== "iam" ? v.services[svc] || [] : [];

  return (
    <div className="aws">
      <SeedFileBar appId={appId} accept=".json,application/json" onLoaded={load} allowPull
        pullHint="ghcr.io/abundant-ai/aws-clone-service:prod-v1" />
      {!v ? (
        <div className="empty-state">Load an aws-clone <b>state.json</b> to browse S3, SQS, DynamoDB, Lambda, IAM &amp; more.</div>
      ) : (
        <div className="aws-body">
          <div className="aws-topbar">
            <span className="aws-logo">aws</span>
            <span className="aws-acct">Account {v.meta.account_id}</span>
            <span className="aws-region">◉ {v.meta.region}</span>
          </div>
          <div className="aws-main-row">
            <aside className="aws-nav">
              {v.nav.map((n) => (
                <div key={n.key} className={`aws-nav-item ${svc === n.key ? "on" : ""}`} onClick={() => setSvc(n.key)}>
                  <span className="aws-svc-dot" style={{ background: SVC_COLOR[n.key] || "#687078" }} />
                  <span className="aws-nav-label">{n.label}</span>
                  <span className="aws-count-pill">{n.count}</span>
                </div>
              ))}
            </aside>
            <main className="aws-content">
              <h2 className="aws-svc-title">{v.nav.find((n) => n.key === svc)?.label}</h2>
              {svc === "iam" ? (
                <div className="aws-iam">
                  <div className="aws-iam-col">
                    <div className="aws-nested-h">Roles ({iam.roles.length})</div>
                    {iam.roles.map((r: any, i: number) => (
                      <div className="aws-card" key={i}>
                        <div className="aws-card-h"><span className="aws-svc-dot" style={{ background: "#dd344c" }} /><span className="aws-card-name">{r.role_name || r.name}</span></div>
                        <div className="aws-card-summary"><J v={r} /></div>
                      </div>
                    ))}
                  </div>
                  <div className="aws-iam-col">
                    <div className="aws-nested-h">Users ({iam.users.length})</div>
                    {iam.users.map((u: any, i: number) => (
                      <div className="aws-card" key={i}>
                        <div className="aws-card-h"><span className="aws-svc-dot" style={{ background: "#dd344c" }} /><span className="aws-card-name">{u.user_name || u.name}</span></div>
                        <div className="aws-card-summary"><J v={u} /></div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="aws-cards">
                  {rows.map((r: any, i: number) => <ResourceCard svc={svc} r={r} key={i} />)}
                  {!rows.length && <div className="hint">No resources.</div>}
                </div>
              )}
            </main>
          </div>
        </div>
      )}
    </div>
  );
}
