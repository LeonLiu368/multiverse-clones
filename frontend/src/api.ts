// Tiny typed client for the generic backend. Every call is namespaced by app id.

export type AppInfo = { id: string; display_name: string; status: string; ui_module: string };
export type Base = { id: string; kind: string; ref: string; label: string; detail: string };
export type Msg = {
  ts: string;
  channel_id: string;
  user: string;
  text: string;
  subtype?: string;
  thread_ts?: string;
  reply_count?: number;
  reactions: { name: string; users?: string[]; count?: number }[];
  origin: "base" | "overlay";
};
export type Channel = {
  id: string;
  name: string;
  topic?: string;
  purpose?: string;
  num_members?: number;
  is_archived?: number;
  origin: "base" | "overlay";
  has_overlay?: boolean;
};
export type User = {
  id: string;
  name: string;
  real_name?: string;
  display_name?: string;
  is_bot?: number;
  origin: "base" | "overlay";
};
export type Meta = {
  workspace: string;
  team_id: string;
  base?: string;
  overlay_path?: string | null;
  stats?: any;
};

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail ?? detail;
    } catch {}
    throw new Error(detail);
  }
  return r.json();
}

export const api = {
  apps: () => fetch("/api/apps").then(j<AppInfo[]>),
  bases: (app: string) => fetch(`/api/${app}/bases`).then(j<Base[]>),
  pull: (app: string, ref: string) =>
    fetch(`/api/${app}/pull`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ref }),
    }).then(j<Base>),
  load: (app: string, base_id: string, overlay_path?: string) =>
    fetch(`/api/${app}/load`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ base_id, overlay_path: overlay_path || null }),
    }).then(j<any>),
  // Load with an overlay uploaded from the browser (a picked file or folder).
  loadUpload: (app: string, base_id: string, files: File[]) => {
    const fd = new FormData();
    fd.append("base_id", base_id);
    fd.append(
      "paths",
      JSON.stringify(files.map((f) => (f as any).webkitRelativePath || f.name))
    );
    files.forEach((f) => fd.append("files", f));
    return fetch(`/api/${app}/load_upload`, { method: "POST", body: fd }).then(j<any>);
  },
  meta: (app: string) => fetch(`/api/${app}/meta`).then(j<Meta>),
  containers: (app: string) => fetch(`/api/${app}/containers`).then(j<Channel[]>),
  entities: (app: string) => fetch(`/api/${app}/entities`).then(j<User[]>),
  messages: (app: string, container: string, limit = 100) =>
    fetch(`/api/${app}/messages?container=${encodeURIComponent(container)}&limit=${limit}`).then(
      j<Msg[]>
    ),
  thread: (app: string, container: string, root_ts: string) =>
    fetch(
      `/api/${app}/thread?container=${encodeURIComponent(container)}&root_ts=${encodeURIComponent(
        root_ts
      )}`
    ).then(j<Msg[]>),
  search: (app: string, q: string, limit = 100) =>
    fetch(`/api/${app}/search?q=${encodeURIComponent(q)}&limit=${limit}`).then(j<Msg[]>),

  // ---- overlay editor (operates only on the task-seed layer) ----
  addContainer: (app: string, name: string, purpose = "") =>
    fetch(`/api/${app}/overlay/container/add`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name, purpose }),
    }).then(j<any>),
  removeContainer: (app: string, container_id: string) =>
    fetch(`/api/${app}/overlay/container/remove`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ container_id }),
    }).then(j<any>),
  addMessage: (app: string, container: string, author: string, text: string, timestamp?: string) =>
    fetch(`/api/${app}/overlay/message/add`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ container, author, text, timestamp: timestamp || null }),
    }).then(j<Msg>),
  removeMessage: (app: string, container_id: string, ts: string) =>
    fetch(`/api/${app}/overlay/message/remove`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ container_id, ts }),
    }).then(j<any>),
  exportOverlay: (app: string) => fetch(`/api/${app}/overlay/export`).then(j<any>),
};
