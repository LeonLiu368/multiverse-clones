"""R6.1: every covered HTTP endpoint — happy path + at least one error path.

Runs against the live seeded gateway over HTTP (the same surface the agent uses).
Asserts real Discord envelopes: stringified snowflake ids, ISO-8601 timestamps,
the message/channel/guild/member shapes, snowflake pagination, and the
``{"code":…, "message":…}`` error body with the right HTTP status + error code.
"""

from __future__ import annotations

UNKNOWN = "999999999999999999"


# --------------------------------------------------------------- auth
def test_auth_required(live_server):
    import httpx

    r = httpx.get(f"{live_server}/users/@me")  # no Authorization header
    assert r.status_code == 401
    body = r.json()
    assert body["code"] == 0 and "Unauthorized" in body["message"]


# --------------------------------------------------------------- users
def test_users_me(client, ids):
    r = client.get("/users/@me")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == ids["bot_user_id"] and body["bot"] is True


def test_users_me_guilds(client, ids):
    r = client.get("/users/@me/guilds")
    assert r.status_code == 200
    guilds = r.json()
    assert any(g["id"] == ids["guild_id"] for g in guilds)


def test_users_get(client, ids):
    r = client.get(f"/users/{ids['mira_id']}")
    assert r.status_code == 200 and r.json()["id"] == ids["mira_id"]


def test_users_get_unknown(client):
    r = client.get(f"/users/{UNKNOWN}")
    assert r.status_code == 404 and r.json()["code"] == 10013


# --------------------------------------------------------------- guilds
def test_guild_get(client, ids):
    r = client.get(f"/guilds/{ids['guild_id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == ids["guild_id"] and body["owner_id"] == ids["mira_id"]


def test_guild_get_unknown(client):
    r = client.get(f"/guilds/{UNKNOWN}")
    assert r.status_code == 404 and r.json()["code"] == 10004


def test_guild_channels(client, ids):
    r = client.get(f"/guilds/{ids['guild_id']}/channels")
    assert r.status_code == 200
    chans = r.json()
    names = {c["name"] for c in chans}
    assert {"incidents", "general", "engineering"} <= names
    # channel envelope shape
    inc = next(c for c in chans if c["name"] == "incidents")
    assert inc["type"] == 0 and inc["guild_id"] == ids["guild_id"] and "position" in inc


def test_guild_channels_unknown(client):
    r = client.get(f"/guilds/{UNKNOWN}/channels")
    assert r.status_code == 404 and r.json()["code"] == 10004


def test_guild_members(client, ids):
    r = client.get(f"/guilds/{ids['guild_id']}/members", params={"limit": 100})
    assert r.status_code == 200
    members = r.json()
    assert len(members) >= 5
    assert all("user" in m and "joined_at" in m and "roles" in m for m in members)


def test_guild_members_pagination(client, ids):
    first = client.get(f"/guilds/{ids['guild_id']}/members", params={"limit": 2}).json()
    assert len(first) == 2
    after = first[-1]["user"]["id"]
    nxt = client.get(f"/guilds/{ids['guild_id']}/members",
                     params={"limit": 2, "after": after}).json()
    assert all(int(m["user"]["id"]) > int(after) for m in nxt)


def test_guild_member(client, ids):
    r = client.get(f"/guilds/{ids['guild_id']}/members/{ids['mira_id']}")
    assert r.status_code == 200 and r.json()["user"]["id"] == ids["mira_id"]


def test_guild_member_unknown(client, ids):
    r = client.get(f"/guilds/{ids['guild_id']}/members/{UNKNOWN}")
    assert r.status_code == 404 and r.json()["code"] == 10007


# --------------------------------------------------------------- channels
def test_channel_get(client, ids):
    r = client.get(f"/channels/{ids['incidents_channel_id']}")
    assert r.status_code == 200 and r.json()["name"] == "incidents"


def test_channel_get_unknown(client):
    r = client.get(f"/channels/{UNKNOWN}")
    assert r.status_code == 404 and r.json()["code"] == 10003


def test_channel_messages(client, ids):
    r = client.get(f"/channels/{ids['incidents_channel_id']}/messages", params={"limit": 50})
    assert r.status_code == 200
    msgs = r.json()
    # newest-first (descending snowflake)
    assert [m["id"] for m in msgs] == sorted((m["id"] for m in msgs), key=int, reverse=True)
    m0 = msgs[0]
    assert {"id", "channel_id", "author", "content", "timestamp", "reactions", "type"} <= set(m0)
    assert m0["author"]["id"] and "username" in m0["author"]


def test_channel_messages_before_after(client, ids):
    cid = ids["incidents_channel_id"]
    allm = client.get(f"/channels/{cid}/messages", params={"limit": 100}).json()
    pivot = allm[len(allm) // 2]["id"]
    before = client.get(f"/channels/{cid}/messages", params={"before": pivot}).json()
    after = client.get(f"/channels/{cid}/messages", params={"after": pivot}).json()
    assert all(int(m["id"]) < int(pivot) for m in before)
    assert all(int(m["id"]) > int(pivot) for m in after)


def test_channel_messages_unknown(client):
    r = client.get(f"/channels/{UNKNOWN}/messages")
    assert r.status_code == 404 and r.json()["code"] == 10003


def test_channel_message_get(client, ids):
    r = client.get(f"/channels/{ids['incidents_channel_id']}/messages/{ids['decision_message_id']}")
    assert r.status_code == 200
    body = r.json()
    assert "PRICING_CACHE_TTL" in body["content"] and body["pinned"] is True
    assert body["reactions"] and body["reactions"][0]["count"] == 2


def test_channel_message_get_unknown(client, ids):
    r = client.get(f"/channels/{ids['incidents_channel_id']}/messages/{UNKNOWN}")
    assert r.status_code == 404 and r.json()["code"] == 10008


def test_send_message_roundtrip(client, ids):
    cid = ids["general_channel_id"]
    r = client.post(f"/channels/{cid}/messages", json={"content": "hello from the verifier"})
    assert r.status_code == 200
    posted = r.json()
    # hydrated derived fields
    assert posted["id"].isdigit()
    assert posted["author"]["id"] == ids["bot_user_id"]
    assert posted["type"] == 0 and posted["reactions"] == [] and posted["timestamp"]
    # read it back
    got = client.get(f"/channels/{cid}/messages/{posted['id']}").json()
    assert got["content"] == "hello from the verifier"


def test_send_message_empty_400(client, ids):
    r = client.post(f"/channels/{ids['general_channel_id']}/messages", json={"content": ""})
    assert r.status_code == 400 and r.json()["code"] == 50006


def test_send_message_unknown_channel(client):
    r = client.post(f"/channels/{UNKNOWN}/messages", json={"content": "x"})
    assert r.status_code == 404 and r.json()["code"] == 10003


def test_channel_pins(client, ids):
    r = client.get(f"/channels/{ids['incidents_channel_id']}/pins")
    assert r.status_code == 200
    pins = r.json()
    assert pins and all(m["pinned"] for m in pins)


# --------------------------------------------------------------- reactions
def test_add_and_list_reaction(client, ids):
    cid = ids["general_channel_id"]
    posted = client.post(f"/channels/{cid}/messages", json={"content": "react to me"}).json()
    mid = posted["id"]
    r = client.put(f"/channels/{cid}/messages/{mid}/reactions/%F0%9F%91%8D/@me")
    assert r.status_code == 204
    reactors = client.get(f"/channels/{cid}/messages/{mid}/reactions/%F0%9F%91%8D").json()
    assert any(u["id"] == ids["bot_user_id"] for u in reactors)


def test_add_reaction_unknown_message(client, ids):
    r = client.put(
        f"/channels/{ids['general_channel_id']}/messages/{UNKNOWN}/reactions/%F0%9F%91%8D/@me")
    assert r.status_code == 404 and r.json()["code"] == 10008


# --------------------------------------------------------------- search (T2)
def test_search_content(client, ids):
    r = client.get(f"/guilds/{ids['guild_id']}/messages/search",
                   params={"content": "PRICING_CACHE_TTL"})
    assert r.status_code == 200
    body = r.json()
    assert body["total_results"] >= 2
    assert all(len(hit) == 1 for hit in body["messages"])  # each match wrapped in a 1-array
    # real Discord marks each matched message with "hit": true
    assert all(hit[0].get("hit") is True for hit in body["messages"])
    # newest-first
    top_ids = [hit[0]["id"] for hit in body["messages"]]
    assert top_ids == sorted(top_ids, key=int, reverse=True)


def test_search_channel_and_pinned(client, ids):
    r = client.get(f"/guilds/{ids['guild_id']}/messages/search",
                   params={"channel_id": ids["incidents_channel_id"], "pinned": "true"})
    body = r.json()
    assert body["total_results"] == 1
    assert "DECISION" in body["messages"][0][0]["content"]


def test_search_author(client, ids):
    r = client.get(f"/guilds/{ids['guild_id']}/messages/search",
                   params={"author_id": ids["lena_id"], "content": "DECISION"})
    body = r.json()
    assert body["total_results"] == 1
    assert body["messages"][0][0]["author"]["id"] == ids["lena_id"]


def test_search_multi_token_content(client, ids):
    # both tokens must appear (AND)
    r = client.get(f"/guilds/{ids['guild_id']}/messages/search",
                   params={"content": "redeploy checkout-service"})
    assert r.json()["total_results"] >= 1
    r2 = client.get(f"/guilds/{ids['guild_id']}/messages/search",
                    params={"content": "PRICING_CACHE_TTL nonexistenttoken"})
    assert r2.json()["total_results"] == 0


def test_search_has_invalid_400(client, ids):
    r = client.get(f"/guilds/{ids['guild_id']}/messages/search",
                   params={"has": "bogus"})
    assert r.status_code == 400 and r.json()["code"] == 50035


def test_search_unknown_guild(client):
    r = client.get(f"/guilds/{UNKNOWN}/messages/search", params={"content": "x"})
    assert r.status_code == 404 and r.json()["code"] == 10004


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"
