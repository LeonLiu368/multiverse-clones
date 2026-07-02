import { useMemo, useState } from "react";
import { api } from "../../api";
import { SeedFileBar } from "../SeedFileBar";

type DUser = { id: string; username: string; global_name?: string | null; bot?: boolean };
type DGuild = { id: string; name: string; description?: string | null; owner_id?: string };
type DChannel = { id: string; guild_id: string; name: string; topic?: string | null; position?: number };
type Reaction = { emoji: string; count: number; users: string[] };
type DMsg = {
  id: string;
  channel_id: string;
  content: string;
  timestamp?: string;
  edited_timestamp?: string | null;
  pinned?: boolean;
  mention_everyone?: boolean;
  mentions: string[];
  reactions: Reaction[];
  author: { id?: string; username: string; global_name?: string | null; bot?: boolean };
};
type DView = {
  guilds: DGuild[];
  channels: DChannel[];
  users: DUser[];
  members: any[];
  messages_by_channel: Record<string, DMsg[]>;
  stats: Record<string, number>;
};

const PALETTE = ["#5865f2", "#3ba55c", "#faa61a", "#ed4245", "#eb459e", "#00b0f4", "#9b59b6"];
function avColor(s: string) {
  let h = 0;
  for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}
function fmtWhen(ts?: string) {
  if (!ts) return "";
  const d = new Date(ts);
  if (isNaN(+d)) return ts;
  return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

// render @mentions / #channels / `code` with Discord styling
function Content({ text, mentions }: { text: string; mentions: string[] }) {
  const parts = text.split(/(@\w[\w.-]*|`[^`]+`)/g);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith("`") && p.endsWith("`"))
          return <code className="dc-code" key={i}>{p.slice(1, -1)}</code>;
        if (p.startsWith("@") && (mentions.includes(p.slice(1)) || p === "@everyone" || p === "@here"))
          return <span className="dc-mention" key={i}>{p}</span>;
        return <span key={i}>{p}</span>;
      })}
    </>
  );
}

export function DiscordApp({ appId }: { appId: string }) {
  const [v, setV] = useState<DView | null>(null);
  const [sel, setSel] = useState<string>("");

  async function load() {
    const data: DView = await api.view(appId);
    setV(data);
    setSel(data.channels[0]?.id ?? "");
  }

  const guild = v?.guilds[0];
  const channel = v?.channels.find((c) => c.id === sel);
  const msgs = (v && v.messages_by_channel[sel]) || [];

  const roster = useMemo(() => {
    if (!v) return { humans: [] as DUser[], bots: [] as DUser[] };
    const humans = v.users.filter((u) => !u.bot);
    const bots = v.users.filter((u) => u.bot);
    return { humans, bots };
  }, [v]);

  // group consecutive messages by the same author (Discord's compact grouping)
  const grouped = useMemo(() => {
    const out: { head: DMsg; rest: DMsg[] }[] = [];
    for (const m of msgs) {
      const last = out[out.length - 1];
      if (last && last.head.author.username === m.author.username && !m.pinned && !last.head.pinned)
        last.rest.push(m);
      else out.push({ head: m, rest: [] });
    }
    return out;
  }, [msgs]);

  return (
    <div className="discord">
      <SeedFileBar
        appId={appId}
        accept=".json,application/json"
        onLoaded={load}
        allowPull
        pullHint="ghcr.io/abundant-ai/discord-service:prod-v1"
      />
      {!v ? (
        <div className="empty-state">
          Load a Discord <b>fixture.json</b> (or a <b>discord.db</b> image) to browse the guild.
        </div>
      ) : (
        <div className="dc-body">
          {/* server rail */}
          <div className="dc-rail">
            <div className="dc-rail-guild" title={guild?.name}>
              {(guild?.name || "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join("")}
            </div>
          </div>

          {/* channel sidebar */}
          <aside className="dc-side">
            <header className="dc-guild-head">
              <span className="dc-guild-name">{guild?.name}</span>
              <span className="dc-guild-chevron">⌄</span>
            </header>
            <div className="dc-section">Text Channels</div>
            <ul className="dc-channels">
              {v.channels.map((c) => (
                <li key={c.id} className={c.id === sel ? "on" : ""} onClick={() => setSel(c.id)}>
                  <span className="dc-hash">#</span>
                  <span className="dc-ch-name">{c.name}</span>
                  <span className="dc-ch-count">{(v.messages_by_channel[c.id] || []).length || ""}</span>
                </li>
              ))}
            </ul>
          </aside>

          {/* chat */}
          <main className="dc-main">
            <header className="dc-chat-head">
              <span className="dc-hash big">#</span>
              <span className="dc-chat-name">{channel?.name}</span>
              {channel?.topic && (
                <>
                  <span className="dc-divider" />
                  <span className="dc-topic">{channel.topic}</span>
                </>
              )}
            </header>
            <div className="dc-msgs">
              {grouped.map(({ head, rest }) => (
                <div className={`dc-group ${head.pinned ? "pinned" : ""}`} key={head.id}>
                  {head.pinned && <div className="dc-pin">📌 Pinned</div>}
                  <div className="dc-msg-row">
                    <span className="dc-avatar" style={{ background: avColor(head.author.username) }}>
                      {(head.author.global_name || head.author.username)[0]?.toUpperCase()}
                    </span>
                    <div className="dc-msg-body">
                      <div className="dc-msg-head">
                        <span className="dc-author">{head.author.global_name || head.author.username}</span>
                        {head.author.bot && <span className="dc-bot">BOT</span>}
                        <span className="dc-when">{fmtWhen(head.timestamp)}</span>
                      </div>
                      <div className="dc-text">
                        <Content text={head.content} mentions={head.mentions} />
                        {head.edited_timestamp && <span className="dc-edited">(edited)</span>}
                      </div>
                      {head.reactions.length > 0 && (
                        <div className="dc-reactions">
                          {head.reactions.map((r) => (
                            <span className="dc-reaction" key={r.emoji} title={r.users.join(", ")}>
                              {r.emoji} <b>{r.count}</b>
                            </span>
                          ))}
                        </div>
                      )}
                      {rest.map((m) => (
                        <div className="dc-followup" key={m.id}>
                          <div className="dc-text">
                            <Content text={m.content} mentions={m.mentions} />
                            {m.edited_timestamp && <span className="dc-edited">(edited)</span>}
                          </div>
                          {m.reactions.length > 0 && (
                            <div className="dc-reactions">
                              {m.reactions.map((r) => (
                                <span className="dc-reaction" key={r.emoji} title={r.users.join(", ")}>
                                  {r.emoji} <b>{r.count}</b>
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
              {!msgs.length && <div className="dc-empty">No messages in #{channel?.name} yet.</div>}
            </div>
            <div className="dc-composer">
              <span>Message #{channel?.name}</span>
            </div>
          </main>

          {/* member list */}
          <aside className="dc-members">
            <div className="dc-mem-h">Members — {roster.humans.length}</div>
            {roster.humans.map((u) => (
              <div className="dc-mem" key={u.id}>
                <span className="dc-avatar sm" style={{ background: avColor(u.username) }}>
                  {(u.global_name || u.username)[0]?.toUpperCase()}
                </span>
                <span className="dc-mem-name">{u.global_name || u.username}</span>
              </div>
            ))}
            {roster.bots.length > 0 && <div className="dc-mem-h">Bots — {roster.bots.length}</div>}
            {roster.bots.map((u) => (
              <div className="dc-mem" key={u.id}>
                <span className="dc-avatar sm" style={{ background: avColor(u.username) }}>
                  {(u.global_name || u.username)[0]?.toUpperCase()}
                </span>
                <span className="dc-mem-name">{u.global_name || u.username}</span>
                <span className="dc-bot">BOT</span>
              </div>
            ))}
          </aside>
        </div>
      )}
    </div>
  );
}
