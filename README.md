# WWG Server Reporter

Reference reporters for the **Watu Wa Gaming Game Server Presence API**.

A reporter is a small piece of code that runs inside or next to a game server
and tells [watuwagaming.site](https://watuwagaming.site) every 30 seconds that
the server is up: what game, what it is called, how many people are on, who,
and how to join. The site then shows the server live on
[/servers](https://watuwagaming.site/servers), on the game's hub page, on your
profile and in the community Discord. Members can like it, follow it to be
told when it comes online, and leave you comments. You edit the title, the
description, how to join and the rules on the site.

This repo gives you three things:

1. **A key in two minutes and a way to test it** (`docs/GETTING_A_KEY.md`,
   `tools/check-key.sh`).
2. **Working examples to copy** for Minecraft (Paper plugin and Fabric mod),
   FiveM, and a generic sidecar that covers any Steam-query game (CS2, Valheim,
   Palworld, ARK, Rust, Garry's Mod), Minecraft without a plugin, Palworld's
   REST API, or a status file.
3. **The contract and a recipe** for building a reporter for a game not
   covered (`docs/API.md`, `docs/TEMPLATES.md`, `docs/BUILDING_A_REPORTER.md`).

## The whole model in six lines

- You create a key on your WWG Developer page. It looks like `wwg_gs_` followed by 40
  characters and is shown once. WWG keeps only a hash.
- Your reporter POSTs a JSON heartbeat to
  `https://watuwagaming.site/api/gs/v1/heartbeat` every 30 seconds, with the
  key as a bearer token.
- A server is **live** while its last heartbeat is under 90 seconds old. Stop
  the heartbeats and it shows offline within 90 seconds. POST `/offline` on
  shutdown to flip it at once.
- The same `external_id` always updates the same server. A new id is a new
  server. Ten servers per key, twenty per member.
- The heartbeat carries the live facts. You add the rest on the site: a title,
  a description, how to join, rules, Discord and website links, icon, banner.
- Unknown fields are ignored and fields are only ever added, so a reporter
  written today keeps working.

The site's own walkthrough, per game, is at
<https://watuwagaming.site/servers/setup>.

## Two minutes to a live server

```bash
# 1. Get a key: https://watuwagaming.site/developer#game-server-api (see docs/GETTING_A_KEY.md)
export WWG_GS_KEY=wwg_gs_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 2. Confirm the key works
bash tools/check-key.sh

# 3. Run the generic sidecar against your server
cd examples/python-sidecar
cp config.example.json config.json      # edit external_id, game, name, join_address, source
python reporter.py --check              # the key, and what WWG already has for it
python reporter.py --once               # one heartbeat; prints the server's URL
python reporter.py                      # every 30 s until stopped; sends /offline on Ctrl+C
```

Then open the URL, and on the Developer page press **Edit details** to give
the server a title, join instructions and rules.

## Pick an example

| Your server | Use | Notes |
|---|---|---|
| Minecraft, Paper or Purpur | [`examples/minecraft-paper`](examples/minecraft-paper) | Plugin. Player names, world day, weather, difficulty. Java 21. |
| Minecraft, Fabric | [`examples/minecraft-fabric`](examples/minecraft-fabric) | Server-side mod. Same data as the plugin. |
| Minecraft, anything (no plugin access) | [`examples/python-sidecar`](examples/python-sidecar) source `minecraft_ping` | Uses the server list ping the client uses. Count, max, version, sample names. |
| CS2, CS:GO, TF2, Garry's Mod, Valheim, Palworld, ARK, Rust, any Source game | [`examples/python-sidecar`](examples/python-sidecar) source `a2s` | Steam query protocol. Map, counts, names, scores. |
| Palworld with the REST API on | [`examples/python-sidecar`](examples/python-sidecar) source `palworld` | Names, levels, in-game day. |
| Project Zomboid | [`examples/python-sidecar`](examples/python-sidecar) source `rcon` with `format: zomboid` | Names and count over RCON. A native WWG mod is in progress. |
| Anything with Source RCON | [`examples/python-sidecar`](examples/python-sidecar) source `rcon` | Minecraft `list`, CS2 `status`, or one name per line. |
| FiveM | [`examples/fivem-resource`](examples/fivem-resource) | A resource. Config through `server.cfg` convars. |
| A server with a status page or a CLI | [`examples/python-sidecar`](examples/python-sidecar) source `fivem` or `command`, or [`examples/node-sidecar`](examples/node-sidecar) | Run any command that prints JSON. |
| Anything else | [`examples/status-file`](examples/status-file) | Have the server write `status.json`; a sidecar posts it. |

## What the site shows

The heartbeat picks a **template** so the card reads right for the game:
`players` (default), `match` (score, round, clock, teams), `world` (day,
weather, difficulty), `lobby` (queue), `race` and `custom` (your own
headline numbers). Every template is documented with a full payload in
[`docs/TEMPLATES.md`](docs/TEMPLATES.md).

On top of what you send, the site adds what members do with the server
(likes, followers, comments, an all-time peak player count) and what you
write about it on the Developer page (title, description, how to join, rules,
links, icon and banner). Nothing on the site can fight the heartbeat: the mod
owns the live facts, you own the words.

## Rules every reporter here follows

- One heartbeat per server every 30 seconds. Never faster than one per 15
  seconds (that is a `429`). Respect `Retry-After`.
- A stable `external_id` per running instance, never reused for a different
  server.
- POST `/offline` in the shutdown hook.
- `401` or `403` means the key was revoked or the account is inactive: stop
  and tell the operator. Do not retry a dead key every 30 seconds.
- A failed heartbeat never affects the game server. Log once, try next tick.
- Publishing player names is an operator setting that can be turned off.
  Never send IPs, Steam IDs, Discord IDs or chat.
- The key lives in a server-side config or an environment variable, never in
  a client mod, a public config repo or a shared backup.

## Docs

- [`docs/GETTING_A_KEY.md`](docs/GETTING_A_KEY.md): where the key comes from,
  how to store it, how to test it, how to rotate it, what each error means.
- [`docs/API.md`](docs/API.md): the full v1 contract, field by field.
- [`docs/TEMPLATES.md`](docs/TEMPLATES.md): the six card layouts with example
  payloads.
- [`docs/BUILDING_A_REPORTER.md`](docs/BUILDING_A_REPORTER.md): the recipe for
  a new game, where each popular game exposes its state, and the completion
  checklist.

## Status

The API described here ships with WWG's release of 18 September 2026. If
`https://watuwagaming.site/servers` does not load yet, that release is not
deployed; the examples run against it unchanged the moment it is. The two
sidecars were tested end to end against the WWG backend. The Paper plugin,
the Fabric mod and the FiveM resource were written against their documented
APIs and reviewed, not built in this repository's CI; see each example's
README for the pinned versions to build with.

## Support

Ask in the WWG Discord (link at [watuwagaming.site/discord](https://watuwagaming.site/discord))
or open an issue here. When reporting a problem, include the HTTP status and
the `error` and `code` fields from the response, never your key.

## License

MIT. See [`LICENSE`](LICENSE).
