# Discord REST API coverage matrix

## Real service
- name: Discord REST API v10
- api_base: https://discord.com/api/v10
- reference: https://discord.com/developers/docs/reference
- version: v10
- snapshot_date: 2026-07-02

Faithful to the agent-used surface of the [Discord REST API](https://discord.com/developers/docs/reference).
Auth mirrors a Discord **bot token**: requests carry `Authorization: Bot <token>`;
a non-empty token is accepted (presence == valid, like a real integration secret).
Ids are stringified **snowflakes** (e.g. `"175928847299117063"`); timestamps are
**ISO-8601** (`…+00:00`). List endpoints are **not** cursor-enveloped — message
history uses `?before=/after=/around=&limit=` **snowflake pagination**, newest-first.
Errors are the real shape `{"code": <int>, "message": "<str>", "errors": {…}}` with
the matching HTTP status: 401 `{code:0,"401: Unauthorized"}`, 404 with a JSON error
code (`10003` Unknown Channel / `10008` Unknown Message / `10004` Unknown Guild /
`10013` Unknown User / `10007` Unknown Member), 400 `50035`/`50006` validation.

One capability = one HTTP endpoint = one `discord` CLI command = one `discord-mcp`
tool, all generated from this matrix over the shared `discordclone.client`
(`DiscordClient`), so the CLI and MCP cannot drift (R3).

| Capability | HTTP endpoint | CLI command | MCP tool | Envelope | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| Identity (self) | `GET /users/@me` | `users me` | `discord_get_self` | user object (`bot:true`) | – | ✅ happy+401 |
| List my guilds | `GET /users/@me/guilds` | `users guilds` | `discord_list_my_guilds` | partial guild list | – | ✅ happy |
| Get user | `GET /users/{id}` | `users get <id>` | `discord_get_user` | user object | – | ✅ happy+404(10013) |
| Get guild | `GET /guilds/{id}` | `guilds get <id>` | `discord_get_guild` | `{id,name,owner_id,…}` | – | ✅ happy+404(10004) |
| List guild channels | `GET /guilds/{id}/channels` | `guilds channels <id>` | `discord_get_guild_channels` | list of channel objects | – | ✅ happy+404 |
| List guild members | `GET /guilds/{id}/members?limit=&after=` | `guilds members <id>` | `discord_list_members` | list of member objects | **★** multi-step, pagination | ✅ happy+pagination |
| Get member | `GET /guilds/{id}/members/{user}` | `guilds member <id> <user>` | `discord_get_member` | `{user,nick,roles,joined_at}` | **★** multi-step resolution, real errors | ✅ happy+404(10007) |
| **Search messages (grammar)** | `GET /guilds/{id}/messages/search?content=&channel_id=&author_id=&mentions=&has=&pinned=&before=&after=` | `guilds search <id> --content …` | `discord_search_messages` | `{total_results,messages:[[msg+"hit":true]]}` | **★** query grammar, multi-step, real errors, filter/pagination | ✅ happy×5+400(50035)+404 |
| Get channel | `GET /channels/{id}` | `channels get <id>` | `discord_get_channel` | channel object | – | ✅ happy+404(10003) |
| **Message history (read)** | `GET /channels/{id}/messages?before=&after=&around=&limit=` | `channels messages <id>` | `discord_get_messages` | list of message objects, newest-first | **★** snowflake pagination, multi-step | ✅ happy+before/after+404 |
| Get one message | `GET /channels/{id}/messages/{message}` | `channels message <id> <msg>` | `discord_get_message` | message object | – | ✅ happy+404(10008) |
| **Send message (write→read)** | `POST /channels/{id}/messages` | `channels send <id> -m` | `discord_send_message` | created message object | **★** stateful round-trip, devops shape | ✅ happy+400(50006)+404 |
| List pins | `GET /channels/{id}/pins` | `channels pins <id>` | `discord_get_pins` | list of pinned messages | – | ✅ happy |
| **Add reaction (write)** | `PUT /channels/{id}/messages/{msg}/reactions/{emoji}/@me` | `reactions add <id> <msg> <emoji>` | `discord_add_reaction` | 204 No Content | **★** stateful round-trip | ✅ happy+404(10008) |
| List reactors | `GET /channels/{id}/messages/{msg}/reactions/{emoji}` | `reactions list <id> <msg> <emoji>` | `discord_list_reactions` | list of user objects | – | ✅ happy (via round-trip) |
| Health | `GET /health` | – | – | `{"status":"ok"}` | – | ✅ |
| **Control plane** (operator only) | `POST/GET /_control/{seed,reset,status}` | `discord seed …` (offline) | — (never exposed) | token-gated, 404 when disabled | – (operator) | – |

★ = labelled **assessment-grade**. 15 agent capabilities, all in CLI⇄MCP parity.

## Assessment-grade capabilities (R5)

An endpoint is assessment-grade when it has ≥3 of: stateful round-trip · multi-step ·
realistic errors · query grammar · side-effecting devops shape. **6 endpoint rows
carry the ★ marker** in the matrix above (≥5 required), one per item below:

1. **Search messages** (`GET /guilds/{id}/messages/search`) — the headline T2
   surface. A real param grammar: `content` (whitespace-tokenized, AND-ed,
   case-insensitive), `channel_id`, `author_id`, `mentions` (a user id in the
   message's mentions), `has` (`link`/`embed`/…), `pinned` (`true`/`false`), and
   `before`/`after` snowflake bounds, paginated by `limit`/`offset`, newest-first,
   returning Discord's `{"total_results":N,"messages":[[msg],…]}` shape — each matched
   message carrying `"hit": true` like the real API. An invalid
   `has` → `50035` validation (400, not 500). Stateful (a posted message is
   searchable), multi-step (search → open → act), query grammar, realistic errors,
   filter/pagination → **5/5**.
2. **Message history** (`GET /channels/{id}/messages`) — snowflake pagination
   (`before`/`after`/`around` + `limit`), always newest-first, the exact Discord
   read shape. Multi-step (paginate → locate → act), non-trivial pagination. **3/5**.
3. **Send message** (`POST /channels/{id}/messages`) — the write→read round-trip.
   Derived fields are hydrated on write (snowflake `id`, ISO `timestamp`, `author`
   object, `type:0`, empty `reactions`), so a verifier reading a posted message back
   gets a real Discord-shaped object. Stateful, devops shape (post a notice), real
   `50006` error on empty. **3/5**.
4. **Add reaction** (`PUT …/reactions/{emoji}/@me`) — stateful round-trip: the
   reactor appears in a later `GET …/reactions/{emoji}` and the message's
   `reactions` rollup increments. 204 on success, `10008` on unknown message.
   Devops shape (acknowledge). **3/5**.
5. **List guild members** (`GET /guilds/{id}/members`) — ascending-snowflake
   pagination with `limit`/`after`; multi-step member resolution (list → resolve →
   act). Filtering/pagination + multi-step. **3/5** (with realistic 404).
6. **Get member** (`GET /guilds/{id}/members/{user}`) — member resolution: realistic
   use chains `users/@me/guilds → guilds/{id}/channels`/`members` → act, so resolving
   a member (nick/roles/joined_at) before acting is a multi-step step with a realistic
   `10007` Unknown Member error (and `10004` Unknown Guild upstream). Multi-step,
   realistic errors, stateful downstream. **3/5**.

**Write→read round-trip exercised by a bundled task** (R5.2):
`discord-incident-triage` makes the agent **search** the guild / **read** the
incident channel to recover the agreed `PRICING_CACHE_TTL=300` remediation for
INC-4471, **fix** the checkout-service config, and **post** a remediation notice to
`#deploys` — then the verifier **reads that message back through the API** and checks
the code. (`nop=0`, `oracle=1`, validated locally via the `REWARD_DIR` path.)

## Intentionally out of scope

Gateway (websocket) events, voice, guild/channel/role **creation & edit**, message
edit/delete, threads, attachments/embeds upload, slash-command registration, OAuth2
flows, and audit logs. The corpus is authored/generated; agents read it, search it,
post messages, and react. This is the surface a coding/ops agent actually touches.
