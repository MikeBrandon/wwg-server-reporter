# Python sidecar

One file, standard library only, reports any number of servers from one
config. It asks each server for its live state through a **source** and
merges that with the identity you set in the config.

```bash
export WWG_GS_KEY=wwg_gs_...
cp config.example.json config.json     # keep only the servers you run; edit ids, names, addresses
python reporter.py --check             # the key, and what WWG already has for it
python reporter.py --dry-run           # the payloads it would send
python reporter.py --once              # one heartbeat each; prints each server's URL
python reporter.py                     # every 30 s until Ctrl+C or SIGTERM; then /offline
```

Python 3.8 or newer. `pip install python-a2s` only if you use the `a2s`
source.

## Sources

| `source.type` | For | Keys |
|---|---|---|
| `minecraft_ping` | Any Minecraft Java server, no plugin needed | `host`, `port` (25565) |
| `a2s` | CS2, CS:GO, TF2, Garry's Mod, Valheim (game port + 1), Palworld, ARK, Rust | `host`, `port`, `players` (true) |
| `fivem` | FiveM's own `info.json` and `players.json` | `base` (`http://127.0.0.1:30120`) |
| `palworld` | Palworld REST API (`RESTAPIEnabled=True`) | `base` (`http://127.0.0.1:8212`), `user`, `password_env` |
| `statusfile` | A JSON file the server or a plugin writes | `path`, `max_age_seconds` (120) |
| `command` | Any command that prints a JSON object | `command`, `timeout` (10) |
| `static` | Nothing dynamic; the fields in the block are sent as they are | any heartbeat field |

A source that cannot reach the game raises and the sidecar skips that
heartbeat, so WWG shows the server offline within 90 seconds. That is the
truth, and it is on purpose.

Identity fields in the server block (`external_id`, `game`, `name`,
`template`, `join_address`, `join_url`, `region`, `mode`, `tags`, `links`,
`icon_url`, `banner_url`) always win over what the source returns, so you
name your own servers. Volatile fields (`player_count`, `players`, `map`,
`version`, `motd`, `state`) come from the source.

## Run it as a service (systemd)

```ini
# /etc/systemd/system/wwg-reporter.service
[Unit]
Description=WWG Server Reporter
After=network-online.target

[Service]
User=games
WorkingDirectory=/opt/wwg-reporter
EnvironmentFile=/etc/wwg-reporter.env     # WWG_GS_KEY=wwg_gs_...   (chmod 600)
ExecStart=/usr/bin/python3 reporter.py --config /opt/wwg-reporter/config.json
Restart=on-failure
RestartSec=30
# Exit code 2 means the key was rejected; do not loop on it.
RestartPreventExitStatus=2

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now wwg-reporter
journalctl -u wwg-reporter -f
```

## Docker

```bash
docker build -t wwg-reporter .
docker run -d --name wwg-reporter --network host \
  -e WWG_GS_KEY=wwg_gs_... -v $PWD/config.json:/app/config.json:ro wwg-reporter
```

`--network host` so `127.0.0.1` in the config reaches the game server on the
same box.

## Exit codes

`0` stopped cleanly (offline sent), `2` the key was rejected (401 or 403):
create a new key, do not restart in a loop.
