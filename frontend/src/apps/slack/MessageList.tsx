import { Msg, User } from "../../api";

const PALETTE = ["#e8912d", "#4a154b", "#2eb67d", "#1264a3", "#e01e5a", "#36c5f0", "#ecb22e"];

function avatarColor(id: string) {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

export function displayName(u: User | undefined, id: string) {
  return u?.display_name || u?.real_name || u?.name || id;
}

function fmtTime(ts: string) {
  const secs = parseFloat(ts);
  if (!isFinite(secs)) return ts;
  const d = new Date(secs * 1000);
  return d.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// Minimal Slack mrkdwn: <@U…> mentions -> @name, *bold*, render newlines.
function renderText(text: string, userMap: Record<string, User>) {
  const withMentions = (text || "").replace(/<@([A-Z0-9]+)>/g, (_, id) => {
    const u = userMap[id];
    return "@" + (u ? displayName(u, id) : id);
  });
  return withMentions;
}

export function MessageList({
  appId,
  messages,
  userMap,
  channelMap,
  showChannel,
  onOpenThread,
}: {
  appId: string;
  messages: Msg[];
  userMap: Record<string, User>;
  channelMap?: Record<string, string>;
  showChannel?: boolean;
  onOpenThread: (m: Msg) => void;
}) {
  return (
    <ul className="msg-list">
      {messages.map((m, i) => {
        const u = userMap[m.user];
        const name = displayName(u, m.user);
        const isReply = m.thread_ts && m.thread_ts !== m.ts;
        return (
          <li
            key={`${m.channel_id}:${m.ts}:${i}`}
            className={`msg ${m.origin === "overlay" ? "msg-seed" : ""}`}
          >
            <div className="avatar" style={{ background: avatarColor(m.user) }}>
              {name[0]?.toUpperCase()}
            </div>
            <div className="msg-body">
              <div className="msg-head">
                <span className="msg-author">{name}</span>
                {u?.is_bot ? <span className="badge bot">APP</span> : null}
                <span className="msg-time">{fmtTime(m.ts)}</span>
                {showChannel && channelMap && (
                  <span className="msg-channel">#{channelMap[m.channel_id] ?? m.channel_id}</span>
                )}
                {m.origin === "overlay" && <span className="badge seed">seeded</span>}
                {isReply && <span className="msg-reply-tag">↳ reply</span>}
              </div>
              {m.subtype === "channel_join" ? (
                <div className="msg-system">{renderText(m.text, userMap)}</div>
              ) : (
                <div className="msg-text">{renderText(m.text, userMap)}</div>
              )}
              {m.reactions?.length ? (
                <div className="reactions">
                  {m.reactions.map((r) => (
                    <span className="reaction" key={r.name}>
                      :{r.name}: {r.count ?? r.users?.length ?? 1}
                    </span>
                  ))}
                </div>
              ) : null}
              {m.reply_count ? (
                <button className="thread-link" onClick={() => onOpenThread(m)}>
                  💬 {m.reply_count} {m.reply_count === 1 ? "reply" : "replies"}
                </button>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
