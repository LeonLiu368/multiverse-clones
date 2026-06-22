import { useState } from "react";
import { api } from "../../api";
import { SeedFileBar } from "../SeedFileBar";

type GithubView = {
  repos: { name?: string; description?: string; private?: boolean }[];
  issues: { repo?: string; title: string; body?: string; labels: string[]; assignees: string[] }[];
  prs: { repo?: string; title: string; body?: string; head?: string; base?: string }[];
  reviews: { pr?: string; repo?: string; state: string; body?: string }[];
  comments: { on: string; repo?: string; body?: string }[];
  other: string[];
  raw: string;
};

export function GithubApp({ appId }: { appId: string }) {
  const [v, setV] = useState<GithubView | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  async function load() {
    setV(await api.view(appId));
  }

  return (
    <div className="ghv">
      <SeedFileBar appId={appId} pathHint="path to a github seed.sh" onLoaded={load} />
      {!v ? (
        <div className="empty-state">
          Load a GitHub <b>seed.sh</b> to preview the repos / issues / PRs / reviews its <code>gh</code> calls create.
        </div>
      ) : (
        <div className="ghv-body">
          <div className="ghv-toolbar">
            <button className={showRaw ? "" : "primary"} onClick={() => setShowRaw(false)}>
              Preview
            </button>
            <button className={showRaw ? "primary" : ""} onClick={() => setShowRaw(true)}>
              Raw script
            </button>
          </div>
          {showRaw ? (
            <pre className="ghv-raw">{v.raw}</pre>
          ) : (
            <div className="ghv-cards">
              <Section title={`Repos (${v.repos.length})`}>
                {v.repos.map((r, i) => (
                  <div className="ghv-card" key={i}>
                    <div className="ghv-card-h">
                      <span className="ghv-repo">{r.name}</span>
                      {r.private && <span className="badge">private</span>}
                    </div>
                    {r.description && <div className="ghv-body-text">{r.description}</div>}
                  </div>
                ))}
              </Section>

              <Section title={`Issues (${v.issues.length})`}>
                {v.issues.map((it, i) => (
                  <div className="ghv-card" key={i}>
                    <div className="ghv-card-h">
                      <span className="ghv-ic">●</span>
                      <b>{it.title}</b>
                      <span className="ghv-repo-tag">{it.repo}</span>
                    </div>
                    {it.body && <div className="ghv-body-text">{it.body}</div>}
                    <div className="ghv-tags">
                      {it.labels.map((l) => (
                        <span className="badge lbl" key={l}>
                          {l}
                        </span>
                      ))}
                      {it.assignees.map((a) => (
                        <span className="ghv-assignee" key={a}>
                          @{a}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </Section>

              <Section title={`Pull requests (${v.prs.length})`}>
                {v.prs.map((p, i) => (
                  <div className="ghv-card" key={i}>
                    <div className="ghv-card-h">
                      <span className="ghv-pr">⑃</span>
                      <b>{p.title}</b>
                      <span className="ghv-repo-tag">{p.repo}</span>
                      {p.head && (
                        <span className="ghv-branch">
                          {p.head} → {p.base}
                        </span>
                      )}
                    </div>
                    {p.body && <div className="ghv-body-text">{p.body}</div>}
                    {v.reviews
                      .filter((r) => r.repo === p.repo)
                      .map((r, j) => (
                        <div className={`ghv-review rv-${r.state}`} key={j}>
                          <span className="ghv-review-state">{r.state.replace("_", " ")}</span>
                          {r.body}
                        </div>
                      ))}
                  </div>
                ))}
              </Section>

              {v.other.length > 0 && (
                <Section title={`Other gh calls (${v.other.length})`}>
                  {v.other.map((o, i) => (
                    <code className="ghv-other" key={i}>
                      {o}
                    </code>
                  ))}
                </Section>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="ghv-section">
      <div className="ghv-section-h">{title}</div>
      {children}
    </section>
  );
}
