# Building a reporter for a new game

A reporter is anything that runs next to (or inside) the game server, reads
its state every 30 seconds and POSTs a heartbeat. This is the recipe the
examples in this repo follow. Start with the shape that fits your game, then
work down the target list.

## Three shapes, in order of preference

1. **Inside the server: a plugin or mod.** The truest data and the least
   glue. Minecraft Paper and Fabric, Rust Oxide or Carbon, FiveM resources,
   Garry's Mod addons, Source plugins, Terraria TShock plugins. Examples:
   `minecraft-paper`, `minecraft-fabric`, `fivem-resource`.
2. **A sidecar asking the server.** A script on the same box that polls the
   server over a query protocol every 30 seconds. Steam A2S (`status` on any
   Source or GoldSrc game, Valheim, Palworld, ARK, Rust), RCON, the game's
   own HTTP API, or the server list ping in Minecraft's case. Example:
   `python-sidecar` with the `a2s`, `minecraft_ping`, `fivem` or `palworld`
   source.
3. **A status file.** The server, a plugin, or your launcher writes
   `status.json` in the heartbeat shape; a tiny watcher posts it. The
   fallback for games that expose nothing, and the quickest way to prototype
   a new template before writing the real plugin. Example: `status-file` with
   either sidecar.

## Where popular games expose their state

| Game | Best source | Gives you | Template |
|---|---|---|---|
| Minecraft (Java) | Paper plugin or Fabric mod | names, UUIDs, max, version, MOTD, day, time, weather, difficulty | `world` (survival), `players` (creative, minigames), `lobby` (hub) |
| Minecraft (Java), no plugin access | Server list ping on the game port (`minecraft_ping`), or RCON `list` (`rcon` source, `format: minecraft`) for the full name list | online, max, version, MOTD, names | `players` |
| Minecraft (Bedrock) | RakNet unconnected ping (not in this repo yet) or a plugin on the proxy | online, max, version | `players` |
| CS2, CS:GO, TF2, L4D2, Garry's Mod, any Source game | A2S on the game port (`a2s`); RCON `status` (`rcon` source, `format: source`) for names and map | map, counts, names, scores; teams via a SourceMod plugin | `match` |
| Valheim | A2S on game port + 1 (`a2s`) | name, counts, version; day from the log if you want it | `world` |
| Palworld | REST API on 8212 when `RESTAPIEnabled=True` (`palworld`), else A2S | names, levels, in-game day, version | `world` |
| ARK | A2S on query port (`a2s`) | map, counts, names | `world` |
| Rust | Oxide or Carbon plugin (best), else RCON `playerlist` | names, counts, wipe day | `world` |
| FiveM | Its own `/info.json` and `/players.json` (`fivem`), or a resource (`fivem-resource`) | project name, max clients, names | `players` |
| Terraria | TShock REST API `/v2/server/status` | names, counts, world name, time | `world` |
| Satisfactory | HTTPS API on the game port (`/api/v1`, `QueryServerState`) | counts, tech tier, game phase | `custom` |
| 7 Days to Die | Web API or telnet | counts, day, time | `world` |
| Project Zomboid | RCON `players` (`rcon` source, `format: zomboid`); a native WWG mod is in progress | names, count | `custom` |
| Assetto Corsa | HTTP `/INFO` and `/JSON|` on the server's http port | track, session, cars, names | `race` |
| Anything with a CLI or a status page | `command` source: any command that prints JSON | whatever you print | any |

If your game is not here, the `command` source turns any script into a
reporter: print a JSON object with heartbeat fields and the sidecar merges
it with the identity fields from its config.

## What to target, in this order

1. **A stable `external_id`.** One per running instance, never reused for a
   different server. `smp-1`, `cs2-scrim-eu`, `valheim-main`. Changing it
   creates a new server on WWG and orphans the old one's likes and comments.
2. **`game`.** The WWG slug when you know it (open the game's hub on the
   site; the slug is the last part of the URL), else the game's name.
   Unresolved names still work; they group under the name you sent.
3. **Cadence.** Every 30 seconds while up. Not faster than one per 15
   seconds per server (a `429`). Respect `Retry-After`. Sleep the
   `next_heartbeat_in` the response gives you.
4. **Shutdown.** POST `/offline` in your stop hook. Not required, but the
   card flips immediately instead of 90 seconds later.
5. **Template first, then the fields that template headlines.** See
   `TEMPLATES.md`. A `match` reporter without a score or round is a players
   card with extra work.
6. **Players.** Names as the game shows them, at most 100. Send `team` when
   the game has sides, `score` when it keeps one (a level, a lap time, a
   kill count all work). Make names an operator switch that can be turned
   off; then send only `player_count`.
7. **Size.** Under 32 KB body, 100 players, 4 KB of `state`, 2 KB of
   `meta`. Trim the player list before the body, never the other way round.
8. **Privacy.** A reporter publishes a join address and player names to a
   public page. Never send IPs, Steam IDs, Discord IDs or chat. The API
   drops a `discord_id` today; do not rely on that to be your filter.
9. **Failure.** A failed heartbeat must not affect the game server. Network
   calls off the main thread (the Paper plugin uses an async task and a
   synchronous snapshot; the Fabric mod snapshots on the tick and posts from
   an executor). Log once, retry next tick. Treat `401` and `403` as "stop
   and tell the operator": the key is dead. Treat `400` as "fix the config".
10. **Test with `GET /me`** before wiring the timer: it confirms the key and
    lists what the site already has for it.

## The completion checklist

A reporter is done when all of these hold:

- [ ] `GET /me` with its key returns the key's name.
- [ ] The server appears on `/servers` within one heartbeat, with the right
      game, and on that game's hub under Live servers.
- [ ] The card reads correctly for its template: a `match` shows a score or
      round, a `world` shows day and weather, a `lobby` shows the queue.
- [ ] Player names appear, and turning the names switch off leaves only the
      count.
- [ ] Killing the server makes the card read offline within 90 seconds;
      stopping it cleanly flips it at once (`/offline`).
- [ ] A second instance with a different `external_id` appears as a second
      server; restarting the first keeps the same server (same id, same
      likes and comments).
- [ ] Revoking the key stops the reporter with a clear log line and no
      retries.
- [ ] A `400` (try a `template` typo) is logged with the API's `error`
      sentence.
- [ ] The key is in an environment variable or a server-side config file
      that is not in version control.
- [ ] The heartbeat body stays under 32 KB with a full server.

## Adding a source to the generic sidecar

`examples/python-sidecar/reporter.py` keeps its sources in one dictionary. A
source is a function that takes the source config and the server config and
returns a dict of heartbeat fields (`player_count`, `players`, `map`,
`version`, `motd`, `state`, anything from `docs/API.md`). Raise
`SourceUnavailable` when the game server cannot be reached: the sidecar skips
that heartbeat and WWG shows the server offline within 90 seconds, which is
the truth. Identity fields from the config (`external_id`, `game`, `name`,
`template`, `join_address`, `tags`, `links`) always win over what the source
returns, so operators name their own servers.

```python
def src_mygame(src: dict, server: dict) -> dict:
    try:
        data = json.loads(_http_get(src.get("url", "http://127.0.0.1:9000/status")))
    except (OSError, ValueError) as exc:
        raise SourceUnavailable(f"mygame: {exc}")
    return {
        "player_count": data["online"],
        "players": [{"name": p["nick"]} for p in data["players"]][:MAX_PLAYERS],
        "state": {"stats": [{"label": "Wave", "value": data["wave"]}]},
    }

SOURCES["mygame"] = src_mygame
```

Send a pull request with the source and a line in the table above.
