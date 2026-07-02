import { useEffect, useState } from "react";
import { api, AppInfo } from "./api";
import { SlackApp } from "./apps/slack/SlackApp";
import { JiraApp } from "./apps/jira/JiraApp";
import { FigmaApp } from "./apps/figma/FigmaApp";
import { GaugeApp } from "./apps/gauge/GaugeApp";
import { SentryApp } from "./apps/sentry/SentryApp";
import { GithubApp } from "./apps/github/GithubApp";
import { LogfireApp } from "./apps/logfire/LogfireApp";
import { GworkspaceApp } from "./apps/gworkspace/GworkspaceApp";
import { NotionApp } from "./apps/notion/NotionApp";
import { AwsApp } from "./apps/aws/AwsApp";
import { DiscordApp } from "./apps/discord/DiscordApp";
import { GenericApp } from "./apps/GenericApp";
import { BrandIcon } from "./apps/icons";

// Visual metadata per app id. A new clone adds one entry; everything else is generic.
const APP_META: Record<string, { glyph: string; color: string; blurb: string }> = {
  slack: { glyph: "S", color: "#4a154b", blurb: "Slack workspace (base + overlay)" },
  jira: { glyph: "J", color: "#0052cc", blurb: "Jira issues (state.json base + overlay)" },
  figma: { glyph: "F", color: "#0d99ff", blurb: "Design file (fixture.json node tree)" },
  gauge: { glyph: "G", color: "#f46800", blurb: "Logs & dashboards (gauge state.json)" },
  sentry: { glyph: "S", color: "#362d59", blurb: "Issues & events (Sentry state.json)" },
  github: { glyph: "G", color: "#24292f", blurb: "Repos/issues/PRs (gh seed.sh)" },
  logfire: { glyph: "🔥", color: "#e5202e", blurb: "Traces & spans (Logfire records.json)" },
  gworkspace: { glyph: "W", color: "#1a73e8", blurb: "Drive / Docs / Calendar / Gmail (gws fixture or gws.db)" },
  notion: { glyph: "N", color: "#000000", blurb: "Databases & pages (Notion fixture or notion.db)" },
  aws: { glyph: "A", color: "#232f3e", blurb: "S3 / SQS / DynamoDB / Lambda / IAM (aws-clone state.json)" },
  discord: { glyph: "D", color: "#5865f2", blurb: "Guild / channels / chat (Discord fixture or discord.db)" },
  echo: { glyph: "E", color: "#1264a3", blurb: "Demo adapter (extension-point proof)" },
};

function Launcher({ apps, onOpen }: { apps: AppInfo[]; onOpen: (a: AppInfo) => void }) {
  // Always show known placeholders even if the backend doesn't register them yet.
  const ids = new Set(apps.map((a) => a.id));
  const placeholders: AppInfo[] = []; // all registered clones are active
  const all = [...apps, ...placeholders];
  return (
    <div className="launcher">
      <header className="launcher-head">
        <h1>Overlay Dashboard</h1>
        <p>Inspect the data overlaid onto each service clone — exactly as an agent's tools would see it.</p>
      </header>
      <div className="tile-grid">
        {all.map((a) => {
          const meta = APP_META[a.id] ?? { glyph: a.display_name[0], color: "#616061", blurb: "" };
          const active = a.status === "active";
          return (
            <button
              key={a.id}
              className={`tile ${active ? "" : "tile-soon"}`}
              disabled={!active}
              onClick={() => active && onOpen(a)}
            >
              <span className="tile-glyph">
                <BrandIcon id={a.id} />
              </span>
              <span className="tile-name">{a.display_name}</span>
              <span className="tile-blurb">{active ? meta.blurb : "Coming soon"}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function App() {
  const [apps, setApps] = useState<AppInfo[]>([]);
  const [open, setOpen] = useState<AppInfo | null>(null);
  const [err, setErr] = useState<string>("");

  useEffect(() => {
    api.apps().then(setApps).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="fatal">Backend unreachable: {err}</div>;

  if (open) {
    return (
      <div className="app-shell">
        <button className="back-btn" onClick={() => setOpen(null)}>
          ← Apps
        </button>
        {open.ui_module === "slack" ? (
          <SlackApp appId={open.id} />
        ) : open.ui_module === "jira" ? (
          <JiraApp appId={open.id} />
        ) : open.ui_module === "figma" ? (
          <FigmaApp appId={open.id} />
        ) : open.ui_module === "gauge" ? (
          <GaugeApp appId={open.id} />
        ) : open.ui_module === "sentry" ? (
          <SentryApp appId={open.id} />
        ) : open.ui_module === "github" ? (
          <GithubApp appId={open.id} />
        ) : open.ui_module === "logfire" ? (
          <LogfireApp appId={open.id} />
        ) : open.ui_module === "gworkspace" ? (
          <GworkspaceApp appId={open.id} />
        ) : open.ui_module === "notion" ? (
          <NotionApp appId={open.id} />
        ) : open.ui_module === "aws" ? (
          <AwsApp appId={open.id} />
        ) : open.ui_module === "discord" ? (
          <DiscordApp appId={open.id} />
        ) : (
          <GenericApp appId={open.id} />
        )}
      </div>
    );
  }
  return <Launcher apps={apps} onOpen={setOpen} />;
}
