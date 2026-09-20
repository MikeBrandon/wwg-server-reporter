# Minecraft: Fabric mod (server side)

A dedicated-server Fabric mod that reports the server to WWG every 30
seconds: player names and UUIDs, max players, version, MOTD, and the
overworld's day, time, weather and difficulty for the `world` card. Posts
`/offline` when the server stops. Needs Fabric API.

## Build

Java 21 and Gradle 8. Refresh the four version lines at the top of
`gradle.properties` from <https://fabricmc.net/develop> for your Minecraft
version (they are pinned to 1.21.4 here), then:

```bash
cd examples/minecraft-fabric
gradle build        # build/libs/wwg-reporter-1.0.0.jar
```

## Install

1. Put the jar (and Fabric API) in `mods/` and start the server once. It
   writes `config/wwg-reporter.json` and logs that the key is missing.
2. Create a key at <https://watuwagaming.site/developer#game-server-api> and
   paste it into `"key"`. Set `external_id`, `name`, `join_address`, and pick
   `"template": "world"` (survival) or `"players"` (creative, minigames).
3. Restart. The log reads `Reporting as https://watuwagaming.site/servers/<id>`.
4. On the Developer page, press **Edit details** to set the title, how to join and
   the rules.

```json
{
  "key": "wwg_gs_...",
  "api_base": "https://watuwagaming.site/api/gs/v1",
  "external_id": "smp-1",
  "game": "minecraft",
  "name": "My WWG server",
  "template": "world",
  "join_address": "play.example.co.ke:25565",
  "join_url": "",
  "region": "Nairobi",
  "mode": "",
  "icon_url": "",
  "tags": ["survival"],
  "links": [{"label": "Rules", "url": "https://example.co.ke/rules"}],
  "interval_seconds": 30,
  "show_player_names": true
}
```

## Behaviour

- The body is snapshotted on the server thread at the end of a tick every
  `interval_seconds`, then posted from one daemon thread, so the network
  never blocks the tick and no Minecraft state is read off-thread.
- A `401` or `403` (revoked key) stops the reporter with one clear log line.
- A `400` logs the API's exact sentence: fix the config.
- `"show_player_names": false` sends only the count.

Client-side installs do nothing: the entrypoint is `server` only.
