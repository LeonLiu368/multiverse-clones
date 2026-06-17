import { useEffect, useMemo, useState } from "react";
import { api, Base, Meta } from "../../api";

// Strip the noisy registry prefix for display; keep the full ref in a title tooltip.
function prettyRef(ref: string) {
  return ref.replace(/^ghcr\.io\/abundant-ai\//, "").replace(/^ghcr\.io\//, "");
}
function shortPath(p: string) {
  return p.split("/").slice(-3).join("/");
}

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
  const [extra, setExtra] = useState<Base[]>([]); // images pulled this session, not in the curated list
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

  // Merge curated + pulled, de-duped, split into images vs local dirs for grouped rendering.
  const { images, dirs } = useMemo(() => {
    const seen = new Set<string>();
    const all = [...extra, ...bases].filter((b) => (seen.has(b.id) ? false : seen.add(b.id)));
    return {
      images: all.filter((b) => b.kind === "image"),
      dirs: all.filter((b) => b.kind === "dir"),
    };
  }, [bases, extra]);

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
    const ref = pullRef.trim();
    if (!ref) return;
    setErr("");
    setBusy(`Pulling ${prettyRef(ref)} (amd64)…`);
    try {
      const b = await api.pull(appId, ref);
      setExtra((e) => [b, ...e.filter((x) => x.id !== b.id)]);
      setBaseId(b.id); // select what we just pulled
      setPullRef("");
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="seedbar">
      {/* Section 1 — choose & load a base */}
      <div className="seedbar-section-label">Base seed</div>
      <div className="seedbar-row">
        <select className="base-select" value={baseId} onChange={(e) => setBaseId(e.target.value)} title={baseId}>
          {images.length > 0 && (
            <optgroup label="Seed images">
              {images.map((b) => (
                <option key={b.id} value={b.id} title={b.ref}>
                  {prettyRef(b.ref)}
                </option>
              ))}
            </optgroup>
          )}
          {dirs.length > 0 && (
            <optgroup label="Local export dirs">
              {dirs.map((b) => (
                <option key={b.id} value={b.id} title={b.ref}>
                  {b.label}
                </option>
              ))}
            </optgroup>
          )}
        </select>
        <input
          className="overlay-input"
          value={overlay}
          placeholder="overlay dir (optional) — auto-detected for gateway sidecar images"
          onChange={(e) => setOverlay(e.target.value)}
          title="Path to a task's environment/data/overlay. Leave blank to use an image's baked overlay."
        />
        <button className="primary" onClick={doLoad} disabled={!baseId || !!busy}>
          Load
        </button>
      </div>

      {/* Section 2 — fetch an image from the registry */}
      <div className="seedbar-section-label">Fetch from registry (GHCR)</div>
      <div className="seedbar-row">
        <input
          className="pull-input"
          value={pullRef}
          placeholder="ghcr.io/abundant-ai/slack-gateway:<tag>  (the gateway sidecar holds the data)"
          onChange={(e) => setPullRef(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && doPull()}
        />
        <button onClick={doPull} disabled={!pullRef.trim() || !!busy}>
          Pull
        </button>
      </div>

      {/* status line on its own row, always readable */}
      <div className="seedbar-status">
        {busy && <span className="hint">⏳ {busy}</span>}
        {err && <span className="err">⚠ {err}</span>}
        {!busy && !err && meta && (
          <span className="hint">
            Loaded <b title={meta.base}>{prettyRef(meta.base || "")}</b>
            {meta.overlay_path ? (
              <>
                {" "}
                + overlay <b title={meta.overlay_path}>{shortPath(meta.overlay_path)}</b>
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
  );
}
