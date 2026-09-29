import { useEffect, useState } from "react";
import { api, Channel, Msg, User } from "../api";

// Fallback view for any active adapter without a bespoke UI (e.g. the echo demo, or a future clone
// before its dedicated view is built). Proves the generic routes render with zero Slack assumptions.
export function GenericApp({ appId }: { appId: string }) {
  const [containers, setContainers] = useState<Channel[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [active, setActive] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    (async () => {
      try {
        await api.load(appId, "fixture");
        const [c, u] = await Promise.all([api.containers(appId), api.entities(appId)]);
        setContainers(c);
        setUsers(u);
        if (c.length) setActive(c[0].id);
      } catch (e) {
        setErr(String(e));
      }
    })();
  }, [appId]);

  useEffect(() => {
    if (active) api.messages(appId, active).then(setMsgs);
  }, [appId, active]);

  if (err) return <div className="fatal">{err}</div>;
  return (
    <div className="generic">
      <div className="generic-side">
        <h3>{appId}</h3>
        <div className="generic-sub">{users.length} entities</div>
        <ul>
          {containers.map((c) => (
            <li key={c.id} className={c.id === active ? "active" : ""} onClick={() => setActive(c.id)}>
              {c.name}
            </li>
          ))}
        </ul>
      </div>
      <div className="generic-main">
        {msgs.map((m) => (
          <div key={m.ts} className="generic-msg">
            <b>{m.user}</b>: {m.text}
          </div>
        ))}
      </div>
    </div>
  );
}
