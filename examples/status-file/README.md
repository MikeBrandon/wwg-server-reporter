# Status file: the fallback for any game

When a game exposes nothing you can query, have it (or a plugin, or your
launcher script) write a JSON file in the heartbeat shape every few seconds,
and let a sidecar post it.

`status.example.json`:

```json
{
  "player_count": 5,
  "max_players": 16,
  "players": [{"name": "Kip"}, {"name": "Amani"}],
  "map": "Knox County",
  "version": "41.78",
  "state": {"stats": [{"label": "Day", "value": 63}, {"label": "Weather", "value": "Fog"}]}
}
```

Only the volatile fields go in the file. Identity (`external_id`, `game`,
`name`, `template`, `join_address`, `tags`) lives in the sidecar config:

```json
{
  "external_id": "zomboid-1", "game": "Project Zomboid", "name": "WWG Knox County", "template": "custom",
  "join_address": "pz.example.co.ke:16261",
  "source": {"type": "statusfile", "path": "/opt/zomboid/status.json", "max_age_seconds": 120}
}
```

If the file goes stale (older than `max_age_seconds`) the sidecar skips the
heartbeat and WWG shows the server offline within 90 seconds, which is what a
crashed server deserves. Write the file atomically (write to a temp name,
then rename) so the sidecar never reads half a file.

This is also the fastest way to prototype a new template: hand-edit the file,
run `python reporter.py --once`, look at the card, repeat.
