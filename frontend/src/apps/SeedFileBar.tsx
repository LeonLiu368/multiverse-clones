import { useEffect, useRef, useState } from "react";
import { api, Base } from "../api";

// Shared loader for the read-only single-file clones (gauge / sentry / github): pick a bundled sample
// or upload a seed file, then it loads.
export function SeedFileBar({
  appId,
  accept,
  onLoaded,
}: {
  appId: string;
  accept: string;
  onLoaded: () => Promise<void> | void;
}) {
  const [bases, setBases] = useState<Base[]>([]);
  const [baseId, setBaseId] = useState("");
  const [fileName, setFileName] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .bases(appId)
      .then((b) => {
        setBases(b);
        if (b[0]) setBaseId(b[0].id);
      })
      .catch((e) => setErr(String(e)));
  }, [appId]);

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

  return (
    <div className="seedbar">
      <div className="seedbar-row">
        <span className="field-label">Sample</span>
        <select className="base-select" value={baseId} onChange={(e) => setBaseId(e.target.value)}>
          {bases.map((b) => (
            <option key={b.id} value={b.id}>
              {b.label}
            </option>
          ))}
          {!bases.length && <option value="">(none — upload a file →)</option>}
        </select>
        <button
          className="primary"
          disabled={!baseId || !!busy}
          onClick={() => run("Loading…", () => api.load(appId, baseId))}
        >
          Load
        </button>

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
    </div>
  );
}
