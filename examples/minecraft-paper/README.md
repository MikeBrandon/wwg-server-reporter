# Minecraft: Paper plugin

A plugin for Paper (and Purpur, Pufferfish, anything Paper-based) that
reports the server to WWG every 30 seconds: player names and UUIDs, max
players, version, MOTD, and the overworld's day, time, weather and
difficulty for the `world` card. It posts `/offline` when the server stops.

## Build

Java 21 and Gradle 8. No wrapper is checked in; run `gradle wrapper` once if
you want one.

```bash
cd examples/minecraft-paper
gradle build        # build/libs/WwgReporter-1.0.0.jar
```

Change the `paper-api` version in `build.gradle.kts` to match your server
(`1.21.4-R0.1-SNAPSHOT` for 1.21.4).

## Install

1. Drop the jar in `plugins/` and start the server once. It writes
   `plugins/WwgReporter/config.yml` and logs that the key is missing.
2. Create a key at <https://watuwagaming.site/developer#game-server-api> and
   paste it into `key:`. Set `external_id`, `name`, `join_address`, and pick
   `template: world` (survival) or `players` (creative, minigames).
3. Restart. The log reads `Reporting as https://watuwagaming.site/servers/<id>`.
4. On the Developer page, press **Edit details** to set the title, how to join and
   the rules.

## Behaviour

- Heartbeats run on an async task; the state is read on the main thread
  through `callSyncMethod`, so the plugin never touches Bukkit off-thread and
  never blocks the tick on the network.
- A `401` or `403` (revoked key) cancels the task with one clear log line.
  Nothing retries a dead key.
- A `400` logs the API's exact sentence: fix `config.yml`.
- `show_player_names: false` sends only the count.
- The MOTD is sent with legacy colour codes stripped.

## What it does not do yet

Bedrock (Geyser) players appear with their Java-side name. There is no
`/wwgreporter` command; edit the config and restart. Pull requests welcome.
