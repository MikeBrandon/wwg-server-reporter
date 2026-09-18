# WWG Game Server Presence API, v1

Base URL: `https://watuwagaming.site/api/gs/v1`

Three calls. Every one carries the key as a bearer token:

```
Authorization: Bearer wwg_gs_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

| Call | Purpose |
|---|---|
| `POST /heartbeat` | "This server is up, here is its state." Every 30 seconds. |
| `POST /offline` | "This server is stopping." On shutdown. Optional. |
| `GET /me` | "Does this key work, and what does WWG have for it?" |

## POST /heartbeat

`Content-Type: application/json`. Body up to 32 KB. Unknown fields are
ignored.

### Identity and facts

| Field | Type | Required | Limits and notes |
|---|---|---|---|
| `external_id` | string | yes | Your stable id for this server, 1 to 80 of `A-Z a-z 0-9 _ . -`. Unique per key; the same id always updates the same server, a new id creates a new one. |
| `game` | string | yes | A WWG game slug (`minecraft`, `counter-strike-2`, the last part of the game's hub URL on the site) or the game's name. Unresolved names are kept as free text and still work. |
| `name` | string | yes | Up to 80. The owner can override it with a title on the site; yours stays visible as "reported as". |
| `motd` | string | no | Up to 200. Shown under the name. |
| `join_address` | string | no | Up to 120, e.g. `play.example.co.ke:25565`. Shown with a copy button. |
| `join_url` | string | no | `https://` only, up to 300. Shown as an Open button (FiveM `cfx.re/join` links, Steam connect pages). |
| `region` | string | no | Up to 40, e.g. `Nairobi`. Filterable. |
| `mode` | string | no | Up to 60, e.g. `Survival`, `Competitive 5v5`. |
| `map` | string | no | Up to 80. |
| `version` | string | no | Up to 40. |
| `max_players` | number | no | |
| `player_count` | number | no | Defaults to the length of `players` when omitted. |
| `players` | array | no | Up to 100 of `{name, uuid, team, score, role, discord_id, wwg_username}`. `name` up to 40; `uuid` up to 40; `team` and `role` up to 24; `score` a number or a string up to 20. `discord_id` and `wwg_username` are accepted and dropped today (identity linking is a later phase); a Discord id is never stored or shown. |
| `meta` | object | no | Up to 20 keys, scalar values only (strings up to 120, numbers, booleans), 2 KB total. Free-form, shown as a table on the detail page. |

### Presentation

| Field | Type | Limits and notes |
|---|---|---|
| `template` | string | `players` (default), `match`, `world`, `lobby`, `race`, `custom`. An unknown value is a `400`, so a typo is caught on the first heartbeat. See `TEMPLATES.md`. |
| `icon_url` | string | `https://`, up to 300. Small square image next to the name. The owner can override it on the site. |
| `banner_url` | string | `https://`, up to 300. Wide image behind the detail page header. Overridable. |
| `tags` | array of strings | Up to 8, each up to 24. Shown as `#tag` chips and filterable. |
| `links` | array of `{label, url}` | Up to 4, `https://` only, labels up to 24. Extra buttons: a rules page, a map download, a mod pack. |
| `state` | object | Structured live state, keys below, 4 KB total. Unknown keys are dropped. |

`state` keys:

| Key | Type | Drawn as |
|---|---|---|
| `phase` | string, up to 24 | Pill next to the name while live: `warmup`, `live`, `halftime`, `ended`, `waiting`. |
| `round`, `rounds_total` | numbers | "Round 7 of 24". The headline on `match` when there is no score. |
| `time_left_seconds` | number | `mm:ss` under the headline on `match`. |
| `score` | string, up to 40 | `"13 - 9"`. The headline on `match`. |
| `teams` | array, up to 8, of `{name (24), score, color "#rrggbb", players [names, up to 32]}` | Team blocks with score and members. Overrides grouping by `players[].team`. |
| `world` | `{day, time_of_day, weather, difficulty, seed}` | Chips on the card, a table on the detail page. `day` is a number; the rest strings. |
| `queue` | `{waiting, eta_seconds}` | "3 in the queue, about 2:00 wait" on `lobby`. |
| `stats` | array, up to 8, of `{label (24), value (40)}` | Headline numbers on `race` and `custom`, a row on the others. |

### Response

`200`:

```json
{
  "ok": true,
  "server_id": 12,
  "url": "https://watuwagaming.site/servers/12",
  "next_heartbeat_in": 30,
  "live_window_seconds": 90,
  "hidden": false
}
```

Sleep `next_heartbeat_in` seconds. `hidden: true` means the name or MOTD
tripped the same word screen the rest of the site uses; the server exists but
stays off the public list until staff look.

### Errors

Every error body is `{"error": "<human sentence>", "code": "<one of these>"}`.

| Code | HTTP | Meaning |
|---|---|---|
| `invalid_key` | 401 | No bearer, wrong prefix, or unknown key. Stop and tell the operator. |
| `key_revoked` | 403 | The key was revoked. Stop and tell the operator. |
| `owner_inactive` | 403 | The key's owner account is deactivated. Stop. |
| `validation` | 400 | Body not JSON, or a field failed the tables above; `error` says which. Fix the config. |
| `server_limit` | 409 | Ten servers on this key or twenty on the account. |
| `body_too_large` | 413 | Over 32 KB. Trim `players`, then `meta`, then `state`. |
| `rate_limited` | 429 | See rate limits. Wait `Retry-After` seconds. |

## POST /offline

```json
{"external_id": "smp-1"}
```

Marks the server offline now instead of 90 seconds after its last heartbeat.
`200 {"ok": true, "ended": 1}` (`ended` is 0 when it was already offline).
Call it in your shutdown hook. It is politeness, not a requirement.

## GET /me

Returns the key's name and prefix and every server it has reported, in the
same shape the public API uses. Use it to confirm a key before wiring the
timer, and to find a server's `id` and URL.

```json
{
  "key": {"id": 12, "name": "Minecraft SMP box", "prefix": "ab12cd34", "created_at": "2026-09-18T10:00:00Z"},
  "servers": [{"id": 12, "external_id": "smp-1", "name": "WWG SMP", "status": "online", "is_live": true, "player_count": 3, "...": "..."}]
}
```

## Liveness

A server is **live** when its last heartbeat is under 90 seconds old. The
public pages filter on that timestamp directly, so a stopped server leaves
"live" within 90 seconds whatever else happens. Send a heartbeat every 30
seconds: that survives one lost request. Servers that went quiet stay
visible as "last seen" for 24 hours, then leave the public list; a server
offline for 60 days is deleted.

## Rate limits

| Scope | Limit | On breach |
|---|---|---|
| Per server (key plus `external_id`) | 1 heartbeat per 15 s | `429`, `Retry-After: 15` |
| Per key | 60 requests per minute | `429` |
| Per IP | 120 requests per minute | `429` |

Ten servers on one key at 30-second cadence is 20 requests a minute, well
inside all three.

## Caps

5 active keys per member. 10 servers per key. 20 servers per member. Removing
a server on the profile frees a slot; the mod recreates it on its next
heartbeat unless its key is revoked.

## What the public sees

`GET https://watuwagaming.site/api/servers` (with `status`, `game`,
`template`, `region`, `tag`, `owner`, `q`, `sort`, `limit`, `offset`) and
`GET /api/servers/:id`, both without a key: the name (the owner's title when
set), game, mode, map, version, region, counts, player names and their team,
score and role, join address and URL, tags, links, state, the owner's public
profile card, when the last heartbeat arrived, plus the site's own fields:
likes, followers, comments, peak players, featured. Never the key, never a
Discord id, never a private server unless you are its owner or staff.

Members who are signed in can like a server, follow it (they get one
"Server online" notification per online run, at most every six hours) and
comment on it. Owners are notified of comments and can delete them.

## Versioning

`/api/gs/v1` is frozen: fields are only ever added, unknown fields are always
ignored, and a breaking change goes to `/v2` with at least 90 days where both
answer. Send a `User-Agent` naming your reporter and its version; it helps
when something needs to be traced.

## A complete heartbeat

```bash
curl -s -X POST https://watuwagaming.site/api/gs/v1/heartbeat \
  -H "Authorization: Bearer $WWG_GS_KEY" -H "Content-Type: application/json" \
  -d '{
    "external_id": "smp-1",
    "game": "minecraft",
    "name": "WWG SMP",
    "template": "world",
    "motd": "Survival, keep inventory on",
    "mode": "Survival",
    "version": "1.21.4",
    "region": "Nairobi",
    "join_address": "play.example.co.ke:25565",
    "max_players": 20,
    "player_count": 2,
    "players": [{"name": "Steve"}, {"name": "Alex"}],
    "tags": ["survival", "whitelist"],
    "links": [{"label": "Rules", "url": "https://example.co.ke/rules"}],
    "state": {"world": {"day": 412, "time_of_day": "14:20", "weather": "Clear", "difficulty": "Hard"}}
  }'
```
