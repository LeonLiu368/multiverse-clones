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

  const userMap = useMemo(() => {
    const m: Record<string, User> = {};
    users.forEach((u) => (m[u.id] = u));
    return m;
  }, [users]);

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
            <div className="sidebar-section">Channels</div>
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
              </div>
            </header>

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
                    userMap={userMap}
                    onOpenThread={setThread}
                  />
                )
              )}
            </div>
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
  userMap,
  onOpenThread,
}: {
  appId: string;
  channel: string;
  userMap: Record<string, User>;
  onOpenThread: (m: Msg) => void;
}) {
  const [msgs, setMsgs] = useState<Msg[] | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setMsgs(null);
    api.messages(appId, channel, 200).then((m) => setMsgs(m.slice().reverse()));
  }, [appId, channel]);
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
  if (!msgs.length) return <div className="hint">No messages in #{channel}.</div>;
  return (
    <>
      <MessageList appId={appId} messages={msgs} userMap={userMap} onOpenThread={onOpenThread} />
      <div ref={bottomRef} />
    </>
  );
}
