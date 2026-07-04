import { useMemo, useState } from "react";
import { api } from "../../api";
import { SeedFileBar } from "../SeedFileBar";

type Node = {
  id: string;
  name?: string;
  type: string;
  characters?: string;
  children?: Node[];
  fills?: { type: string; color?: { r: number; g: number; b: number; a: number } }[];
  strokes?: any[];
  cornerRadius?: number;
  style?: { fontSize?: number; fontWeight?: number; fontFamily?: string; textAlignHorizontal?: string };
  absoluteBoundingBox?: { x: number; y: number; width: number; height: number };
};
type FigmaFile = { key: string; name: string; document: Node; comments?: any[]; thumbnailUrl?: string; images?: Record<string, string> };
type FigmaView = { team: any; projects: any[]; files: FigmaFile[] };

const NODE_ICON: Record<string, string> = {
  DOCUMENT: "▦", CANVAS: "▤", FRAME: "▭", GROUP: "▢", COMPONENT: "◈", INSTANCE: "◇",
  TEXT: "T", RECTANGLE: "▭", VECTOR: "✎", ELLIPSE: "◯",
};

function solid(n?: Node) {
  const f = n?.fills?.find((x) => x.type === "SOLID" && x.color);
  if (!f?.color) return null;
  const { r, g, b, a } = f.color;
  return { rgba: `rgba(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)},${a})`, color: f.color };
}
const hex = (c: { r: number; g: number; b: number }) =>
  "#" + [c.r, c.g, c.b].map((x) => Math.round(x * 255).toString(16).padStart(2, "0")).join("").toUpperCase();

function descendants(n: Node): Node[] {
  const out: Node[] = [];
  const walk = (x: Node) => {
    out.push(x);
    (x.children || []).forEach(walk);
  };
  (n.children || []).forEach(walk);
  return out;
}

export function FigmaApp({ appId }: { appId: string }) {
  const [v, setV] = useState<FigmaView | null>(null);
  const [fileKey, setFileKey] = useState("");
  const [canvasId, setCanvasId] = useState("");
  const [selId, setSelId] = useState("");
  const [tab, setTab] = useState<"inspect" | "comments">("inspect");
  const [mode, setMode] = useState<"thumbnail" | "canvas">("canvas");

  async function load() {
    const data: FigmaView = await api.view(appId);
    setV(data);
    const f = data.files[0];
    setFileKey(f?.key ?? "");
    const cv = (f?.document.children || []).find((c) => c.type === "CANVAS");
    setCanvasId(cv?.id ?? "");
    setSelId("");
    // big real corpora carry a live thumbnail image and are too large to draw faithfully as boxes —
    // default to the thumbnail; small fixtures (placeholder thumb) default to the canvas render.
    setMode(String(f?.thumbnailUrl || "").startsWith("http") ? "thumbnail" : "canvas");
  }

  const file = v?.files.find((f) => f.key === fileKey) ?? null;
  const canvases = (file?.document.children || []).filter((c) => c.type === "CANVAS");
  const canvas = canvases.find((c) => c.id === canvasId) ?? canvases[0] ?? null;
  const NODE_CAP = 1500;

  const { nodes, bounds, truncated } = useMemo(() => {
    if (!canvas) return { nodes: [] as Node[], bounds: null as any, truncated: 0 };
    let ns = descendants(canvas).filter((n) => n.absoluteBoundingBox);
    const truncated = Math.max(0, ns.length - NODE_CAP);
    ns = ns.slice(0, NODE_CAP);
    if (!ns.length) return { nodes: ns, bounds: null, truncated };
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of ns) {
      const b = n.absoluteBoundingBox!;
      if (b.x < minX) minX = b.x;
      if (b.y < minY) minY = b.y;
      if (b.x + b.width > maxX) maxX = b.x + b.width;
      if (b.y + b.height > maxY) maxY = b.y + b.height;
    }
    return { nodes: ns, bounds: { minX, minY, w: maxX - minX, h: maxY - minY }, truncated };
  }, [canvas]);

  const scale = bounds ? Math.min(1, 880 / bounds.w) : 1;
  const allById = useMemo(() => {
    const m: Record<string, Node> = {};
    file && descendants({ children: [file.document] } as Node).forEach((n) => (m[n.id] = n));
    return m;
  }, [file]);
  const sel = allById[selId] ?? null;

  return (
    <div className="fig">
      <SeedFileBar
        appId={appId}
        accept=".json,application/json"
        onLoaded={load}
        allowPull
        pullHint="ghcr.io/abundant-ai/figma-service-mv:prod-v1"
      />
      {!v ? (
        <div className="empty-state">
          Load a Figma <b>fixture.json</b> to inspect the file's canvas, layers and node tree.
        </div>
      ) : (
        <div className="fig-body">
          {/* left: pages + layers */}
          <aside className="fig-left">
            {v.files.length > 1 && (
              <select className="fig-fileselect" value={fileKey} onChange={(e) => setFileKey(e.target.value)}>
                {v.files.map((f) => (
                  <option key={f.key} value={f.key}>
                    {f.name}
                  </option>
                ))}
              </select>
            )}
            <div className="fig-section">Pages</div>
            {canvases.map((c) => (
              <div
                key={c.id}
                className={`fig-page ${c.id === canvas?.id ? "active" : ""}`}
                onClick={() => {
                  setCanvasId(c.id);
                  setSelId("");
                }}
              >
                ▤ {c.name}
              </div>
            ))}
            <div className="fig-section">Layers</div>
            <div className="fig-layers">
              {(canvas?.children || []).map((n) => (
                <Layer key={n.id} node={n} depth={0} selId={selId} onSelect={setSelId} />
              ))}
            </div>
          </aside>

          {/* middle: canvas / thumbnail */}
          <main className="fig-center">
            <div className="fig-modebar">
              <button className={mode === "canvas" ? "active" : ""} onClick={() => setMode("canvas")}>
                Canvas
              </button>
              <button className={mode === "thumbnail" ? "active" : ""} onClick={() => setMode("thumbnail")}>
                Thumbnail
              </button>
              {mode === "canvas" && truncated > 0 && (
                <span className="fig-trunc">showing {nodes.length} of {nodes.length + truncated} nodes</span>
              )}
            </div>
            {mode === "thumbnail" ? (
              <div className="fig-thumb-wrap">
                {file?.thumbnailUrl ? (
                  <img
                    className="fig-thumb"
                    src={file.thumbnailUrl}
                    alt={file.name}
                    onError={(e) => ((e.currentTarget.style.display = "none"),
                      e.currentTarget.insertAdjacentHTML("afterend",
                        '<div class="hint">Thumbnail image unavailable (URL expired or service-relative).</div>'))}
                  />
                ) : (
                  <div className="hint">This file has no thumbnail.</div>
                )}
              </div>
            ) : (
            <div className="fig-canvas-wrap" onClick={() => setSelId("")}>
            {bounds ? (
              <div className="fig-canvas" style={{ width: bounds.w * scale, height: bounds.h * scale }}>
                {nodes.map((n) => {
                  const b = n.absoluteBoundingBox!;
                  const fill = solid(n);
                  const isText = n.type === "TEXT";
                  const st: React.CSSProperties = {
                    left: (b.x - bounds.minX) * scale,
                    top: (b.y - bounds.minY) * scale,
                    width: b.width * scale,
                    height: b.height * scale,
                    borderRadius: (n.cornerRadius || 0) * scale,
                    background: isText ? "transparent" : fill?.rgba,
                    outline: n.id === selId ? "2px solid #0d99ff" : undefined,
                    outlineOffset: n.id === selId ? "0" : undefined,
                    border: n.strokes?.length ? "1px solid rgba(0,0,0,.15)" : undefined,
                  };
                  if (isText) {
                    st.color = fill?.rgba ?? "#111";
                    st.fontSize = (n.style?.fontSize || 14) * scale;
                    st.fontWeight = n.style?.fontWeight || 400;
                    st.fontFamily = n.style?.fontFamily;
                    st.textAlign = (n.style?.textAlignHorizontal || "left").toLowerCase() as any;
                    st.display = "flex";
                    st.alignItems = "center";
                  }
                  return (
                    <div
                      key={n.id}
                      className={`fig-node ${isText ? "fig-text" : ""}`}
                      style={st}
                      title={`${n.type} · ${n.name}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelId(n.id);
                      }}
                    >
                      {isText ? n.characters : null}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="hint">This page has no positioned nodes.</div>
            )}
            </div>
            )}
          </main>

          {/* right: inspector / comments */}
          <aside className="fig-right">
            <div className="fig-tabs">
              <button className={tab === "inspect" ? "active" : ""} onClick={() => setTab("inspect")}>
                Inspect
              </button>
              <button className={tab === "comments" ? "active" : ""} onClick={() => setTab("comments")}>
                Comments {file?.comments?.length ? `(${file.comments.length})` : ""}
              </button>
            </div>
            {tab === "inspect" ? (
              <Inspector node={sel} />
            ) : (
              <div className="fig-comments">
                {(file?.comments || []).map((c: any) => (
                  <div
                    className="fig-comment"
                    key={c.id}
                    onClick={() => c.client_meta?.node_id && setSelId(c.client_meta.node_id)}
                  >
                    <div className="fig-comment-h">
                      <b>{c.user?.handle ?? c.user?.id}</b>
                      {c.client_meta?.node_id && <span className="fig-node-ref">{c.client_meta.node_id}</span>}
                    </div>
                    <div className="fig-comment-b">{c.message}</div>
                  </div>
                ))}
                {!file?.comments?.length && <div className="hint">No comments.</div>}
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}

function Layer({
  node,
  depth,
  selId,
  onSelect,
}: {
  node: Node;
  depth: number;
  selId: string;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(depth < 2);
  const kids = node.children || [];
  return (
    <>
      <div
        className={`fig-layer ${node.id === selId ? "sel" : ""}`}
        style={{ paddingLeft: 8 + depth * 14 }}
        onClick={() => onSelect(node.id)}
      >
        {kids.length ? (
          <span
            className="fig-caret"
            onClick={(e) => {
              e.stopPropagation();
              setOpen((o) => !o);
            }}
          >
            {open ? "▾" : "▸"}
          </span>
        ) : (
          <span className="fig-caret" />
        )}
        <span className="fig-icon">{NODE_ICON[node.type] ?? "•"}</span>
        <span className="fig-layer-name">{node.name || node.type}</span>
      </div>
      {open && kids.map((c) => <Layer key={c.id} node={c} depth={depth + 1} selId={selId} onSelect={onSelect} />)}
    </>
  );
}

function Inspector({ node }: { node: Node | null }) {
  if (!node) return <div className="fig-inspect hint">Select a layer to inspect it.</div>;
  const b = node.absoluteBoundingBox;
  return (
    <div className="fig-inspect">
      <div className="fig-i-type">
        {NODE_ICON[node.type] ?? "•"} {node.type}
      </div>
      <div className="fig-i-name">{node.name}</div>
      <div className="fig-i-id">{node.id}</div>

      {b && (
        <div className="fig-i-grid">
          <span>X</span><b>{b.x}</b><span>Y</span><b>{b.y}</b>
          <span>W</span><b>{b.width}</b><span>H</span><b>{b.height}</b>
        </div>
      )}
      {node.cornerRadius != null && (
        <div className="fig-i-row"><span>Radius</span><b>{node.cornerRadius}</b></div>
      )}
      {node.style?.fontSize && (
        <div className="fig-i-row">
          <span>Font</span>
          <b>{node.style.fontFamily} {node.style.fontWeight} · {node.style.fontSize}px</b>
        </div>
      )}
      {node.characters && (
        <div className="fig-i-text">“{node.characters}”</div>
      )}
      {node.fills?.length ? (
        <div className="fig-i-fills">
          <div className="fig-i-label">Fills</div>
          {node.fills.map((f, i) =>
            f.color ? (
              <div className="fig-swatch" key={i}>
                <span
                  className="fig-chip"
                  style={{ background: `rgba(${Math.round(f.color.r * 255)},${Math.round(f.color.g * 255)},${Math.round(f.color.b * 255)},${f.color.a})` }}
                />
                {hex(f.color)} <span className="fig-muted">{Math.round((f.color.a ?? 1) * 100)}%</span>
              </div>
            ) : null
          )}
        </div>
      ) : null}
    </div>
  );
}
