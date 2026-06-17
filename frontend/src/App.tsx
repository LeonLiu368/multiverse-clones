import { useEffect, useState } from "react";
import { api, AppInfo } from "./api";
import { SlackApp } from "./apps/slack/SlackApp";
import { GenericApp } from "./apps/GenericApp";

// Visual metadata per app id. A new clone adds one entry; everything else is generic.
const APP_META: Record<string, { glyph: string; color: string; blurb: string }> = {
  slack: { glyph: "S", color: "#4a154b", blurb: "Slack workspace (base + overlay)" },
  echo: { glyph: "E", color: "#1264a3", blurb: "Demo adapter (extension-point proof)" },
  github: { glyph: "G", color: "#24292f", blurb: "Coming soon" },
  linear: { glyph: "L", color: "#5e6ad2", blurb: "Coming soon" },
};

function Launcher({ apps, onOpen }: { apps: AppInfo[]; onOpen: (a: AppInfo) => void }) {
  // Always show known placeholders even if the backend doesn't register them yet.
  const ids = new Set(apps.map((a) => a.id));
  const placeholders: AppInfo[] = ["github", "linear"]
    .filter((id) => !ids.has(id))
    .map((id) => ({ id, display_name: id[0].toUpperCase() + id.slice(1), status: "soon", ui_module: "generic" }));
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
              <span className="tile-glyph" style={{ background: meta.color }}>
                {meta.glyph}
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
        {open.ui_module === "slack" ? <SlackApp appId={open.id} /> : <GenericApp appId={open.id} />}
      </div>
    );
  }
  return <Launcher apps={apps} onOpen={setOpen} />;
}
