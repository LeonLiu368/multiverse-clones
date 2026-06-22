import { useEffect, useState } from "react";
import { api, Base } from "../api";

// Shared loader for the read-only single-file clones (gauge / sentry / github): pick a bundled sample
// or paste a path to any seed file, then Load.
export function SeedFileBar({
  appId,
  pathHint,
  onLoaded,
}: {
  appId: string;
  pathHint: string;
  onLoaded: () => Promise<void> | void;
}) {
  const [bases, setBases] = useState<Base[]>([]);
  const [baseId, setBaseId] = useState("");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    api
      .bases(appId)
      .then((b) => {
        setBases(b);
        if (b[0]) setBaseId(b[0].id);
      })
      .catch((e) => setErr(String(e)));
  }, [appId]);

  async function load(id: string) {
    setErr("");
    setBusy("Loading…");
    try {
      await api.load(appId, id);
      await onLoaded();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="seedbar">
      <div className="seedbar-row">
        <span className="field-label">Seed</span>
        <select className="base-select" value={baseId} onChange={(e) => setBaseId(e.target.value)}>
          {bases.map((b) => (
            <option key={b.id} value={b.id}>
              {b.label}
            </option>
          ))}
          {!bases.length && <option value="">(no bundled samples — paste a path →)</option>}
        </select>
        <button className="primary" disabled={!baseId || !!busy} onClick={() => load(baseId)}>
          Load
        </button>
        <span className="field-label muted">or path</span>
        <input
          className="pull-input"
          value={path}
          placeholder={pathHint}
          onChange={(e) => setPath(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && path.trim() && load("file:" + path.trim())}
        />
        <button disabled={!path.trim() || !!busy} onClick={() => load("file:" + path.trim())}>
          Load file
        </button>
        <div className="seedbar-status">
          {busy && <span className="hint">⏳ {busy}</span>}
          {err && <span className="err">⚠ {err}</span>}
        </div>
      </div>
    </div>
  );
}
