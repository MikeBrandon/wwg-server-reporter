# Node sidecar

The Python sidecar's twin for boxes that have Node and not Python. No
dependencies, Node 18 or newer, the same `config.json`.

```bash
export WWG_GS_KEY=wwg_gs_...
cp ../python-sidecar/config.example.json config.json   # edit
node reporter.mjs --check
node reporter.mjs --once
node reporter.mjs
```

Sources: `static`, `statusfile`, `command`, `fivem`. For `minecraft_ping`,
`a2s` and `palworld` use the Python sidecar, or point a `command` source at
any script that prints JSON.

Run it under `pm2` or systemd (`ExecStart=/usr/bin/node reporter.mjs`,
`RestartPreventExitStatus=2`). Exit code `2` means the key was rejected.
