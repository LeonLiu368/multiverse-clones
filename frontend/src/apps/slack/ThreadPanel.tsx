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

  return (
    <aside className="thread-panel">
      <header className="thread-head">
        <span>Thread</span>
        <button className="link" onClick={onClose}>
          ✕
        </button>
      </header>
      <div className="thread-scroll">
        {!msgs ? (
          <div className="hint">loading…</div>
        ) : (
          <MessageList appId={appId} messages={msgs} userMap={userMap} onOpenThread={() => {}} />
        )}
      </div>
    </aside>
  );
}
