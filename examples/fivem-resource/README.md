# FiveM resource

A server-only resource that heartbeats to WWG every 30 seconds with the
player count and names, and marks the server offline when the resource stops.

## Install

1. Copy this folder to `resources/[wwg]/wwg-reporter`.
2. In `server.cfg`, before `ensure`:

   ```
   set wwg_gs_key "wwg_gs_..."               # from https://watuwagaming.site/developer#game-server-api
   set wwg_external_id "fivem-rp"            # stable id for this server; changing it makes a new server on WWG
   set wwg_game "Grand Theft Auto V"
   set wwg_server_name "WWG Roleplay"        # defaults to sv_projectName
   set wwg_join_url "https://cfx.re/join/xxxxxx"
   set wwg_region "Nairobi"
   set wwg_tags "roleplay,whitelist"
   set wwg_show_player_names 1               # 0 sends only the count
   ensure wwg-reporter
   ```

3. Restart, and watch the console for `[wwg-reporter] reporting as
   https://watuwagaming.site/servers/<id>`.

The key stays in `server.cfg`, which is private to the box, so the resource
folder can be shared or committed. Never put the key in the resource.

## What it sends

`template: players`, `player_count`, `max_players` (from `sv_maxClients`),
player names (unless `wwg_show_player_names 0`), `motd` from
`sv_projectDesc`, your join URL or address, region and tags. Nothing about
identifiers: no Steam, license, Discord or IP identifiers ever leave the box.

## Alternative: no resource

FiveM already publishes `/info.json` and `/players.json` on the game port.
The Python or Node sidecar's `fivem` source reads those and needs nothing
installed in the server. Use the resource when you want the offline call
on stop and the names switch inside the server.
