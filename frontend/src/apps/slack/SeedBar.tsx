import { useEffect, useState } from "react";
import { api, Base, Meta } from "../../api";

// The "seed process" UI: choose a base seed image (or local export dir), optionally a per-task
// overlay dir, optionally pull a GHCR tag, then Load to build the merged workspace host-side.
export function SeedBar({
  appId,
  meta,
  onLoaded,
}: {
  appId: string;
  meta: Meta | null;
  onLoaded: () => void;
}) {
  const [bases, setBases] = useState<Base[]>([]);
  const [baseId, setBaseId] = useState("");
  const [overlay, setOverlay] = useState("");
  const [pullRef, setPullRef] = useState("");
  const [busy, setBusy] = useState<string>("");
  const [err, setErr] = useState("");

  async function loadBases() {
    const b = await api.bases(appId);
    setBases(b);
    if (b.length && !baseId) setBaseId(b[0].id);
  }
  useEffect(() => {
    loadBases().catch((e) => setErr(String(e)));
  }, [appId]);

  async function doLoad() {
    setErr("");
    setBusy("Loading & merging…");
    try {
      await api.load(appId, baseId, overlay.trim() || undefined);
      onLoaded();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy("");
    }
  }

  async function doPull() {
    if (!pullRef.trim()) return;
    setErr("");
    setBusy("Pulling image…");
    try {
      await api.pull(appId, pullRef.trim());
      await loadBases();
      setBaseId(pullRef.trim());
      setPullRef("");
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="seedbar">
      <div className="seedbar-row">
        <label>Base</label>
        <select value={baseId} onChange={(e) => setBaseId(e.target.value)}>
          {bases.map((b) => (
            <option key={b.id} value={b.id}>
              {b.kind === "image" ? "🅸 " : "🗀 "}
              {b.label}
            </option>
          ))}
        </select>

        <label>Overlay dir</label>
        <input
          className="overlay-input"
          value={overlay}
          placeholder="optional — path to a task's environment/data/overlay"
          onChange={(e) => setOverlay(e.target.value)}
        />

        <button className="primary" onClick={doLoad} disabled={!baseId || !!busy}>
          Load
        </button>
      </div>

      <div className="seedbar-row sub">
        <label>Pull GHCR</label>
        <input
          className="pull-input"
          value={pullRef}
          placeholder="ghcr.io/abundant-ai/slack-gateway:prod-v1"
          onChange={(e) => setPullRef(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && doPull()}
        />
        <button onClick={doPull} disabled={!pullRef.trim() || !!busy}>
          Pull
        </button>

        <div className="seedbar-status">
          {busy && <span className="hint">{busy}</span>}
          {err && <span className="err">{err}</span>}
          {!busy && !err && meta && (
            <span className="hint">
              Loaded <b>{meta.base}</b>
              {meta.overlay_path ? (
                <>
                  {" "}
                  + overlay <b>{shortPath(meta.overlay_path)}</b>
                </>
              ) : null}{" "}
              · {meta.stats?.channels} channels, {meta.stats?.users} users
              {meta.stats?.overlay ? (
                <>
                  {" "}
                  · <span className="badge seed">+{meta.stats.overlay.messages} seeded</span>
                </>
              ) : null}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function shortPath(p: string) {
  const parts = p.split("/");
  return parts.slice(-3).join("/");
}
