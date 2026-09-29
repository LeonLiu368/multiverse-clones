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
  edited?: boolean;
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
  email?: string;
  tz?: string;
  is_bot?: number;
  deleted?: number;
  origin: "base" | "overlay";
};
export type Meta = {
  workspace: string;
  team_id: string;
  base?: string;
  overlay_path?: string | null;
  stats?: any;
};

// ---- Jira (ticketvector state.json) shapes ----
export type JiraUser = { id: string; handle: string; name: string };
export type JiraState = { id: string; name: string; category?: string };
export type JiraLabel = { id: string; name: string };
export type JiraProject = { id: string; key: string; name: string; origin?: "base" | "overlay" };
export type JiraIssue = {
  id: string;
  identifier: string;
  project?: JiraProject;
  title: string;
  description?: string;
  state: JiraState;
  priority: string;
  assignees: JiraUser[];
  labels: JiraLabel[];
  comments_count?: number;
  created_at?: string;
  updated_at?: string;
  origin: "base" | "overlay";
  edited?: boolean;
};
export type JiraComment = {
  id: string;
  author: JiraUser;
  body: string;
  created_at?: string;
  origin: "base" | "overlay";
};
export type JiraChanges = {
  added: string[];
  edited: string[];
  deleted: { identifier: string; title: string }[];
  comments_added: number;
  comments_deleted: number;
  ops: number;
};
export type JiraMeta = {
  workspace: string;
  project: JiraProject;
  states: JiraState[];
  labels: JiraLabel[];
  base?: string;
  stats?: { issues: number; comments: number; users: number };
  changes?: JiraChanges;
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
  // read-only whole-seed payload (gauge / sentry / github)
  view: (app: string) => fetch(`/api/${app}/view`).then(j<any>),
  loadFile: (app: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(`/api/${app}/load_file`, { method: "POST", body: fd }).then(j<any>);
  },
  loadOverlay: (app: string, base_id: string, overlay: File) => {
    const fd = new FormData();
    fd.append("base_id", base_id);
    fd.append("overlay", overlay);
    return fetch(`/api/${app}/load_overlay`, { method: "POST", body: fd }).then(j<any>);
  },
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
  exportPatch: (app: string) => fetch(`/api/${app}/overlay/patch`).then(j<any>),
  overlayOp: (app: string, op: string, payload: Record<string, any>) =>
    fetch(`/api/${app}/overlay/op`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ op, payload }),
    }).then(j<any>),
  exportOverlayZip: async (app: string, name: string): Promise<Blob> => {
    const r = await fetch(`/api/${app}/overlay/export.zip?name=${encodeURIComponent(name)}`);
    if (!r.ok) {
      let detail = r.statusText;
      try {
        detail = (await r.json()).detail ?? detail;
      } catch {}
      throw new Error(detail);
    }
    return r.blob();
  },

  // ---- Jira-typed views over the generic routes ----
  jira: {
    meta: (app: string) => fetch(`/api/${app}/meta`).then(j<JiraMeta>),
    projects: (app: string) => fetch(`/api/${app}/containers`).then(j<JiraProject[]>),
    users: (app: string) => fetch(`/api/${app}/entities`).then(j<JiraUser[]>),
    issues: (app: string, container: string, limit = 1000) =>
      fetch(`/api/${app}/messages?container=${encodeURIComponent(container)}&limit=${limit}`).then(
        j<JiraIssue[]>
      ),
    comments: (app: string, container: string, identifier: string) =>
      fetch(
        `/api/${app}/thread?container=${encodeURIComponent(container)}&root_ts=${encodeURIComponent(
          identifier
        )}`
      ).then(j<JiraComment[]>),
    search: (app: string, q: string, limit = 1000) =>
      fetch(`/api/${app}/search?q=${encodeURIComponent(q)}&limit=${limit}`).then(j<JiraIssue[]>),
  },
};
