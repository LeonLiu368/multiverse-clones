import { useEffect, useMemo, useRef, useState } from "react";
import { api, Base, Channel, Meta, Msg, User } from "../../api";
import { SeedBar } from "./SeedBar";
import { MessageList } from "./MessageList";
import { ThreadPanel } from "./ThreadPanel";

export function SlackApp({ appId }: { appId: string }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [active, setActive] = useState<string>("");
  const [thread, setThread] = useState<Msg | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Msg[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [rev, setRev] = useState(0); // bump to force the open channel to re-fetch after an edit
  const [editErr, setEditErr] = useState("");

  const userMap = useMemo(() => {
    const m: Record<string, User> = {};
    users.forEach((u) => (m[u.id] = u));
    return m;
  }, [users]);

  function flash(e: unknown) {
    setEditErr(String(e));
    setTimeout(() => setEditErr(""), 4000);
  }

  // ---- overlay edit handlers (task-seed layer only) ----
  async function addChannel() {
    const name = window.prompt("New overlay channel name (e.g. launch-room):")?.trim();
    if (!name) return;
    try {
      await api.addContainer(appId, name);
      await refresh();
      setActive(name);
      setResults(null);
    } catch (e) {
      flash(e);
    }
  }
  async function deleteChannel(c: Channel) {
    if (!window.confirm(`Delete overlay channel #${c.name} and its messages?`)) return;
    try {
      await api.removeContainer(appId, c.id);
      if (active === c.name) setActive("");
      await refresh();
    } catch (e) {
      flash(e);
    }
  }
  async function deleteMessage(m: Msg) {
    try {
      await api.overlayOp(appId, "delete_message", { channel: m.channel_id, ts: m.ts });
      setRev((v) => v + 1);
      refresh();
    } catch (e) {
      flash(e);
    }
  }
  async function editMessage(m: Msg) {
    const text = window.prompt("Edit message text:", m.text);
    if (text == null || text === m.text) return;
    try {
      await api.overlayOp(appId, "edit_message", { channel: m.channel_id, ts: m.ts, text });
      setRev((v) => v + 1);
      refresh();
    } catch (e) {
      flash(e);
    }
  }
  async function sendMessage(author: string, text: string, timestamp?: string) {
    await api.addMessage(appId, active, author, text, timestamp);
    setRev((v) => v + 1);
    refresh();
  }
  async function downloadOverlay() {
    const name = window.prompt("Name the export directory:", "overlay")?.trim();
    if (!name) return;
    try {
      const blob = await api.exportOverlayZip(appId, name);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${name}.zip`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      flash(e);
    }
  }
  async function downloadPatch() {
    const name = window.prompt("Name the patch file:", "slack-patch")?.trim();
    if (!name) return;
    try {
      const data = await api.exportPatch(appId); // {version, ops} mutations of base messages
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${name}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      flash(e);
    }
  }

  async function refresh() {
    const [mt, ch, us] = await Promise.all([
      api.meta(appId),
      api.containers(appId),
      api.entities(appId),
    ]);
    setMeta(mt);
    setChannels(ch);
    setUsers(us);
    setLoaded(true);
    if (!active && ch.length) setActive(ch.find((c) => c.has_overlay)?.name ?? ch[0].name);
  }

  async function onLoaded() {
    setActive("");
    setThread(null);
    setResults(null);
    await refresh();
  }

  async function runSearch() {
    if (!query.trim()) {
      setResults(null);
      return;
    }
    setBusy(true);
    try {
      setResults(await api.search(appId, query));
    } finally {
      setBusy(false);
    }
  }

  const activeChannel = channels.find((c) => c.name === active);

  return (
    <div className="slack">
      <SeedBar appId={appId} meta={meta} onLoaded={onLoaded} />
      {!loaded ? (
        <div className="empty-state">
          Pick a base image and (optionally) an overlay above, then <b>Load</b> to inspect the
          merged workspace.
        </div>
      ) : (
        <div className="slack-body">
          {/* workspace rail */}
          <div className="rail">
            <div className="rail-team" title={meta?.workspace}>
              {(meta?.workspace ?? "W")[0]?.toUpperCase()}
            </div>
          </div>

          {/* channel sidebar */}
          <aside className="sidebar">
            <div className="sidebar-head">
              <div className="ws-name">{meta?.workspace ?? "workspace"}</div>
              <div className="ws-sub">
                {channels.length} channels · {users.length} members
              </div>
            </div>
            <div className="sidebar-section">
              <span>Channels</span>
              <button className="add-ch" title="Add an overlay channel" onClick={addChannel}>
                +
              </button>
            </div>
            <ul className="channel-list">
              {channels.map((c) => (
                <li
                  key={c.id}
                  className={c.name === active && !results ? "active" : ""}
                  onClick={() => {
                    setActive(c.name);
                    setResults(null);
                    setThread(null);
                  }}
                >
                  <span className="hash">#</span>
                  <span className="ch-name">{c.name}</span>
                  {c.origin === "overlay" && <span className="badge ov">overlay</span>}
                  {c.origin === "base" && c.has_overlay && <span className="dot ov" title="overlay messages" />}
                  {c.origin === "overlay" && (
                    <button
                      className="ch-del"
                      title="Delete this overlay channel"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteChannel(c);
                      }}
                    >
                      🗑
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </aside>

          {/* main column */}
          <main className="main">
            <header className="main-head">
              <div className="main-title">
                {results ? (
                  <>Search: “{query}”</>
                ) : (
                  <>
                    <span className="hash">#</span>
                    {active}
                    {activeChannel?.has_overlay && <span className="badge ov">overlay</span>}
                  </>
                )}
              </div>
              <div className="search-box">
                <input
                  value={query}
                  placeholder="Search messages…"
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && runSearch()}
                />
                {results && (
                  <button
                    className="link"
                    onClick={() => {
                      setResults(null);
                      setQuery("");
                    }}
                  >
                    clear
                  </button>
                )}
                <button
                  className="ghost-btn"
                  title="Download added channels/messages as a zipped Slack-export directory"
                  onClick={downloadOverlay}
                >
                  ⬇ export dir
                </button>
                <button
                  className="ghost-btn"
                  title="Download base-message edits/deletes as an import_export --patch op-list"
                  onClick={downloadPatch}
                >
                  ⬇ patch.json
                </button>
              </div>
            </header>

            {editErr && <div className="edit-err">⚠ {editErr}</div>}

            <div className="main-scroll">
              {busy && <div className="hint">searching…</div>}
              {results ? (
                <MessageList
                  appId={appId}
                  messages={results}
                  userMap={userMap}
                  channelMap={Object.fromEntries(channels.map((c) => [c.id, c.name]))}
                  showChannel
                  onOpenThread={setThread}
                />
              ) : (
                active && (
                  <ChannelMessages
                    appId={appId}
                    channel={active}
                    rev={rev}
                    userMap={userMap}
                    onOpenThread={setThread}
                    onDelete={deleteMessage}
                    onEdit={editMessage}
                  />
                )
              )}
            </div>

            {!results && active && <ComposeBar channel={active} users={users} onSend={sendMessage} />}
          </main>

          {thread && (
            <ThreadPanel
              appId={appId}
              root={thread}
              userMap={userMap}
              onClose={() => setThread(null)}
            />
          )}
        </div>
      )}
    </div>
  );
}

function ChannelMessages({
  appId,
  channel,
  rev,
  userMap,
  onOpenThread,
  onDelete,
  onEdit,
}: {
  appId: string;
  channel: string;
  rev: number;
  userMap: Record<string, User>;
  onOpenThread: (m: Msg) => void;
  onDelete: (m: Msg) => void;
  onEdit: (m: Msg) => void;
}) {
  const [msgs, setMsgs] = useState<Msg[] | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setMsgs(null);
    api.messages(appId, channel, 200).then((m) => setMsgs(m.slice().reverse()));
  }, [appId, channel, rev]);
  // Open at the bottom (newest), like Slack. Pin the scroll container after paint so it lands fully
  // at the bottom even once avatars/wrapping settle the layout.
  useEffect(() => {
    if (!msgs?.length) return;
    const pin = () => {
      const c = bottomRef.current?.closest(".main-scroll") as HTMLElement | null;
      if (c) c.scrollTop = c.scrollHeight;
    };
    requestAnimationFrame(() => requestAnimationFrame(pin));
  }, [msgs]);
  if (!msgs) return <div className="hint">loading…</div>;
  if (!msgs.length) return <div className="hint">No messages in #{channel} yet — add one below.</div>;
  return (
    <>
      <MessageList
        appId={appId}
        messages={msgs}
        userMap={userMap}
        onOpenThread={onOpenThread}
        onDelete={onDelete}
        onEdit={onEdit}
      />
      <div ref={bottomRef} />
    </>
  );
}

// Compose box pinned to the bottom of a channel — every message it adds is overlay (task-seed).
// The author field is a picker over existing workspace users: choosing one sends the message AS that
// user (the server resolves the username to the real id); a name not in the list creates a new
// overlay user.
function ComposeBar({
  channel,
  users,
  onSend,
}: {
  channel: string;
  users: User[];
  onSend: (author: string, text: string, timestamp?: string) => Promise<void>;
}) {
  const [author, setAuthor] = useState("");
  const [text, setText] = useState("");
  const [date, setDate] = useState("");
  const [tm, setTm] = useState("");
  const [busy, setBusy] = useState(false);

  // Resolve what was typed to an existing user by username / real name / display name (the server
  // matches on username, so we send that). Falls back to a new user when nothing matches.
  const byLabel = useMemo(() => {
    const m: Record<string, User> = {};
    users.forEach((u) => {
      [u.name, u.real_name, u.display_name].forEach((l) => {
        if (l) m[l.toLowerCase()] = u;
      });
    });
    return m;
  }, [users]);
  const matched = byLabel[author.trim().toLowerCase()];

  function timestamp(): string | undefined {
    if (!date) return undefined;
    return `${date}T${tm || "00:00"}:00`;
  }

  async function submit() {
    if (!author.trim() || !text.trim()) return;
    setBusy(true);
    try {
      await onSend(matched ? matched.name : author.trim(), text.trim(), timestamp());
      setText("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="compose">
      <div className="compose-author-wrap">
        <input
          className="compose-author"
          value={author}
          list="compose-users"
          placeholder="author"
          autoComplete="off"
          onChange={(e) => setAuthor(e.target.value)}
        />
        <datalist id="compose-users">
          {users.map((u) => (
            <option key={u.id} value={u.name}>
              {u.real_name || u.display_name || u.name}
            </option>
          ))}
        </datalist>
        {author.trim() && (
          <span className={`author-hint ${matched ? "known" : "new"}`}>
            {matched ? `as @${matched.name}` : "new user"}
          </span>
        )}
      </div>
      <input
        className="compose-text"
        value={text}
        placeholder={`Add an overlay message to #${channel}…`}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
      />
      <input
        className="compose-date"
        type="date"
        value={date}
        title="Optional date — blank posts at 'now'"
        onChange={(e) => setDate(e.target.value)}
      />
      <input
        className="compose-time"
        type="time"
        value={tm}
        title="Optional time of day"
        onChange={(e) => setTm(e.target.value)}
      />
      <button className="primary" onClick={submit} disabled={busy || !author.trim() || !text.trim()}>
        Add
      </button>
    </div>
  );
}
