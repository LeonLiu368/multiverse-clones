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
  onDelete,
  onEdit,
}: {
  appId: string;
  messages: Msg[];
  userMap: Record<string, User>;
  channelMap?: Record<string, string>;
  showChannel?: boolean;
  onOpenThread: (m: Msg) => void;
  onDelete?: (m: Msg) => void;
  onEdit?: (m: Msg) => void;
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
            <UserHover u={u} id={m.user}>
              <div className="avatar" style={{ background: avatarColor(m.user) }}>
                {name[0]?.toUpperCase()}
              </div>
            </UserHover>
            <div className="msg-body">
              <div className="msg-head">
                <UserHover u={u} id={m.user}>
                  <span className="msg-author">{name}</span>
                </UserHover>
                {u?.is_bot ? <span className="badge bot">APP</span> : null}
                <span className="msg-time">{fmtTime(m.ts)}</span>
                {showChannel && channelMap && (
                  <span className="msg-channel">#{channelMap[m.channel_id] ?? m.channel_id}</span>
                )}
                {m.origin === "overlay" && <span className="badge ov">overlay</span>}
                {m.edited && <span className="badge edited">edited</span>}
                {isReply && <span className="msg-reply-tag">↳ reply</span>}
                {onEdit && (
                  <button className="msg-act" title="Edit this message" onClick={() => onEdit(m)}>
                    ✎
                  </button>
                )}
                {onDelete && (
                  <button
                    className="msg-act"
                    title={m.origin === "base" ? "Delete (recorded as a patch delete op)" : "Delete overlay message"}
                    onClick={() => onDelete(m)}
                  >
                    🗑
                  </button>
                )}
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

// Hover any author name/avatar to see the full user profile (real name, @username, email, tz, id).
function UserHover({ u, id, children }: { u?: User; id: string; children: React.ReactNode }) {
  return (
    <span className="user-hover">
      {children}
      <span className="user-card">
        <span className="uc-avatar" style={{ background: avatarColor(id) }}>
          {displayName(u, id)[0]?.toUpperCase()}
        </span>
        <span className="uc-body">
          <span className="uc-name">
            {u?.real_name || u?.display_name || u?.name || id}
            {u?.is_bot ? <span className="badge bot">APP</span> : null}
            <span className={`badge ${u?.origin === "overlay" ? "ov" : "base-tag"}`}>
              {u?.origin ?? "?"}
            </span>
          </span>
          {u?.name && <span className="uc-row">@{u.name}</span>}
          {u?.display_name && u.display_name !== u.name && (
            <span className="uc-row">display: {u.display_name}</span>
          )}
          {u?.email && <span className="uc-row">✉ {u.email}</span>}
          {u?.tz && <span className="uc-row">🕑 {u.tz}</span>}
          {u?.deleted ? <span className="uc-row uc-muted">deactivated</span> : null}
          <span className="uc-row uc-id">{id}</span>
        </span>
      </span>
    </span>
  );
}
