import { useEffect, useRef, useState } from "react";
import { api, Base } from "../api";

// Shared loader for the read-only single-file clones (gauge / sentry / github): pick a bundled sample
// or upload a seed file, then it loads.
export function SeedFileBar({
  appId,
  accept,
  onLoaded,
  allowPull = false,
  pullHint = "",
  allowOverlay = false,
}: {
  appId: string;
  accept: string;
  onLoaded: () => Promise<void> | void;
  allowPull?: boolean;
  pullHint?: string;
  allowOverlay?: boolean;
}) {
  const [bases, setBases] = useState<Base[]>([]);
  const [baseId, setBaseId] = useState("");
  const [fileName, setFileName] = useState("");
  const [overlayFile, setOverlayFile] = useState<File | null>(null);
  const [pullRef, setPullRef] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const overlayRef = useRef<HTMLInputElement>(null);

  async function loadBases(selectId?: string) {
    const b = await api.bases(appId);
    setBases(b);
    setBaseId(selectId ?? (b[0]?.id || ""));
  }
  useEffect(() => {
    loadBases().catch((e) => setErr(String(e)));
  }, [appId]);

  const images = bases.filter((b) => b.kind === "image");
  const others = bases.filter((b) => b.kind !== "image");

  async function run(label: string, fn: () => Promise<any>) {
    setErr("");
    setBusy(label);
    try {
      await fn();
      await onLoaded();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy("");
    }
  }

  function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setFileName(f.name);
    run(`Uploading ${f.name}…`, () => api.loadFile(appId, f));
  }

  async function doPull() {
    const ref = pullRef.trim();
    if (!ref) return;
    setErr("");
    setBusy(`Pulling ${ref} (amd64)…`);
    try {
      const b = await api.pull(appId, ref);
      await loadBases(b.id);
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
        <span className="field-label">{allowPull ? "Base" : "Sample"}</span>
        <select className="base-select" value={baseId} onChange={(e) => setBaseId(e.target.value)} title={baseId}>
          {images.length > 0 && (
            <optgroup label="Images">
              {images.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.label.replace(/^ghcr\.io\/abundant-ai\//, "")}
                </option>
              ))}
            </optgroup>
          )}
          {others.length > 0 && (
            <optgroup label="Samples">
              {others.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.label}
                </option>
              ))}
            </optgroup>
          )}
          {!bases.length && <option value="">(none — upload a file →)</option>}
        </select>
        <button
          className="primary"
          disabled={!baseId || !!busy}
          onClick={() =>
            run("Loading…", () =>
              overlayFile ? api.loadOverlay(appId, baseId, overlayFile) : api.load(appId, baseId)
            )
          }
        >
          Load
        </button>

        {allowOverlay && (
          <>
            <span className="field-label muted">+ overlay</span>
            <input
              ref={overlayRef}
              type="file"
              accept={accept}
              className="overlay-file-hidden"
              onChange={(e) => setOverlayFile(e.target.files?.[0] ?? null)}
            />
            <button className="overlay-pick" disabled={!!busy} onClick={() => overlayRef.current?.click()}>
              {overlayFile ? `📄 ${overlayFile.name}` : "Overlay file…"}
            </button>
            {overlayFile && (
              <button className="icon-btn" title="clear overlay" onClick={() => setOverlayFile(null)}>
                ✕
              </button>
            )}
          </>
        )}

        <span className="field-label muted">or upload</span>
        <input ref={fileRef} type="file" accept={accept} className="overlay-file-hidden" onChange={onPick} />
        <button className="overlay-pick" disabled={!!busy} onClick={() => fileRef.current?.click()}>
          {fileName ? `📄 ${fileName}` : "Choose file…"}
        </button>

        <div className="seedbar-status">
          {busy && <span className="hint">⏳ {busy}</span>}
          {err && <span className="err">⚠ {err}</span>}
        </div>
      </div>
      {allowPull && (
        <div className="seedbar-row sub">
          <span className="field-label muted">Pull</span>
          <input
            className="pull-input"
            value={pullRef}
            placeholder={pullHint}
            onChange={(e) => setPullRef(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && doPull()}
          />
          <button onClick={doPull} disabled={!pullRef.trim() || !!busy}>
            Pull from GHCR
          </button>
        </div>
      )}
    </div>
  );
}
