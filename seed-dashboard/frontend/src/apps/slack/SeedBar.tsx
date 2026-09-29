import { useEffect, useMemo, useRef, useState } from "react";
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
  const [overlayFiles, setOverlayFiles] = useState<File[]>([]);
  const [overlayLabel, setOverlayLabel] = useState("");
  const [pullRef, setPullRef] = useState("");
  const [busy, setBusy] = useState<string>("");
  const [err, setErr] = useState("");
  const dirRef = useRef<HTMLInputElement>(null);

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

  // Folder pickers need the non-standard `webkitdirectory` attribute, which JSX/TS won't accept
  // directly — set it on the DOM node so the picker chooses a directory (an overlay export dir).
  useEffect(() => {
    if (dirRef.current) {
      dirRef.current.setAttribute("webkitdirectory", "");
      dirRef.current.setAttribute("directory", "");
    }
  }, []);

  function onPickOverlay(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    setOverlayFiles(files);
    const top = (files[0] as any)?.webkitRelativePath?.split("/")[0];
    setOverlayLabel(top ? `${top}/ (${files.length} files)` : files[0]?.name ?? "");
  }

  function clearOverlay() {
    setOverlayFiles([]);
    setOverlayLabel("");
    if (dirRef.current) dirRef.current.value = "";
  }

  async function doLoad() {
    setErr("");
    setBusy("Loading & merging…");
    try {
      if (overlayFiles.length) await api.loadUpload(appId, baseId, overlayFiles);
      else await api.load(appId, baseId);
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
      <div className="seedbar-row">
        <span className="field-label">Base</span>
        <select className="base-select" value={baseId} onChange={(e) => setBaseId(e.target.value)} title={baseId}>
          {images.length > 0 && (
            <optgroup label="Images">
              {images.map((b) => (
                <option key={b.id} value={b.id} title={b.ref}>
                  {prettyRef(b.ref)}
                </option>
              ))}
            </optgroup>
          )}
          {dirs.length > 0 && (
            <optgroup label="Local dirs">
              {dirs.map((b) => (
                <option key={b.id} value={b.id} title={b.ref}>
                  {b.label}
                </option>
              ))}
            </optgroup>
          )}
        </select>

        <span className="field-label">Overlay</span>
        <input ref={dirRef} type="file" multiple className="overlay-file-hidden" onChange={onPickOverlay} />
        <button
          className="overlay-pick"
          onClick={() => dirRef.current?.click()}
          title="Pick a task's overlay export folder (environment/data/overlay). Leave empty to use a sidecar image's baked overlay."
        >
          {overlayLabel ? `📁 ${overlayLabel}` : "Choose folder…"}
        </button>
        {overlayLabel && (
          <button className="icon-btn" onClick={clearOverlay} title="clear overlay">
            ✕
          </button>
        )}

        <button className="primary" onClick={doLoad} disabled={!baseId || !!busy}>
          Load
        </button>

        <div className="seedbar-status">
          {busy && <span className="hint">⏳ {busy}</span>}
          {err && <span className="err">⚠ {err}</span>}
          {!busy && !err && meta && (
            <span className="hint">
              <b title={meta.base}>{prettyRef(meta.base || "")}</b>
              {meta.overlay_path ? (
                <> + <b title={meta.overlay_path}>{shortPath(meta.overlay_path)}</b></>
              ) : null}{" "}
              · {meta.stats?.channels} ch · {meta.stats?.users} users
              {meta.stats?.overlay ? (
                <> · <span className="badge ov">+{meta.stats.overlay.messages} overlay</span></>
              ) : null}
            </span>
          )}
        </div>
      </div>

      <div className="seedbar-row sub">
        <span className="field-label muted">Pull</span>
        <input
          className="pull-input"
          value={pullRef}
          placeholder="ghcr.io/abundant-ai/slack-gateway-mv:<tag>"
          onChange={(e) => setPullRef(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && doPull()}
        />
        <button onClick={doPull} disabled={!pullRef.trim() || !!busy}>
          Pull from GHCR
        </button>
      </div>
    </div>
  );
}
