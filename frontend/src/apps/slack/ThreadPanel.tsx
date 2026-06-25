import { useEffect, useState } from "react";
import { api, Msg, User } from "../../api";
import { MessageList } from "./MessageList";

export function ThreadPanel({
  appId,
  root,
  userMap,
  onClose,
}: {
  appId: string;
  root: Msg;
  userMap: Record<string, User>;
  onClose: () => void;
}) {
  const [msgs, setMsgs] = useState<Msg[] | null>(null);
  useEffect(() => {
    setMsgs(null);
    api.thread(appId, root.channel_id, root.thread_ts || root.ts).then(setMsgs);
  }, [appId, root.channel_id, root.ts]);

  // Some scraped corpora record a parent's reply_count but not the reply bodies — the thread then
  // comes back as just the parent. Surface that rather than showing a silently empty thread.
  const replyCount = root.reply_count || 0;
  const bodiesMissing = !!msgs && msgs.length <= 1 && replyCount > 0;

  return (
    <aside className="thread-panel">
      <header className="thread-head">
        <span>Thread{replyCount ? ` · ${replyCount} ${replyCount === 1 ? "reply" : "replies"}` : ""}</span>
        <button className="link" onClick={onClose}>
          ✕
        </button>
      </header>
      <div className="thread-scroll">
        {!msgs ? (
          <div className="hint">loading…</div>
        ) : (
          <>
            <MessageList appId={appId} messages={msgs} userMap={userMap} onOpenThread={() => {}} />
            {bodiesMissing && (
              <div className="hint thread-missing">
                {replyCount} {replyCount === 1 ? "reply" : "replies"} recorded, but the reply
                messages aren’t included in this corpus.
              </div>
            )}
          </>
        )}
      </div>
    </aside>
  );
}
