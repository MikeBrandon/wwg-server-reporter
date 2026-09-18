# Getting a key, keeping it safe, testing it

A key is what lets a reporter speak for you. Anything holding it can put a
server on your profile, so treat it like a password.

## 1. Create the key

1. Sign in at [watuwagaming.site](https://watuwagaming.site). Any member
   account works; there is no application step.
2. Open your profile settings and scroll to **Game server API**, or go
   straight to <https://watuwagaming.site/profile#game-server-api>.
3. Type a name for the key. Name it after the box or the server it will run
   on (`Minecraft SMP box`, `CS2 scrims`), not after yourself: when you have
   three keys you will want to know which one to revoke.
4. Press **Create key**. The key appears once, in a yellow panel:

   ```
   wwg_gs_ab12cd34ef56gh78ij90kl12mn34op56qr78st90
   ```

   Copy it now. When you press **Done** it is gone for good. WWG stores only a
   hash, so nobody, including staff, can show it to you again. If you lose
   it, revoke it and create another.

Limits: five active keys per member, ten servers per key, twenty servers per
member.

## 2. Store it

Pick one, in this order of preference:

- **An environment variable** on the server box: `WWG_GS_KEY`. Every example
  here reads it. For a systemd service put it in an `EnvironmentFile` with
  mode `600`.
- **A server-side config file** the game server reads (`config.yml` for the
  Paper plugin, `config/wwg-reporter.json` for Fabric, `server.cfg` for
  FiveM). Keep the file out of any backup or archive you share.
- **A secrets manager**, if your host has one.

Never:

- put it in a client-side mod or anything players download;
- commit it to a repository, public or private (`config.json` is in this
  repo's `.gitignore` for that reason);
- paste it in Discord, a screenshot or a bug report. Reports need the HTTP
  status and the `error` field, never the key.

## 3. Test it before wiring anything

```bash
export WWG_GS_KEY=wwg_gs_...
bash tools/check-key.sh
```

which is just:

```bash
curl -s https://watuwagaming.site/api/gs/v1/me -H "Authorization: Bearer $WWG_GS_KEY"
```

A working key answers with its name and prefix and every server it has
reported so far (none, on a new key):

```json
{"key":{"id":12,"name":"Minecraft SMP box","prefix":"ab12cd34","created_at":"2026-09-18T10:00:00Z"},"servers":[]}
```

Then send one real heartbeat with the generic sidecar (`python reporter.py
--once`) or the curl in `docs/API.md`. The response carries the server's URL:

```json
{"ok":true,"server_id":12,"url":"https://watuwagaming.site/servers/12","next_heartbeat_in":30,"live_window_seconds":90,"hidden":false}
```

Open it. Your server is live for the next 90 seconds.

## 4. After the first heartbeat

Back on your profile, the server is listed under **My servers** with:

- a **Public** switch (off means only you and staff see it; it keeps
  reporting);
- **Edit details**: a title on WWG (the mod's own name stays visible as
  "reported as"), a description, how to join, the rules, a Discord invite, a
  website, an icon and a banner. This is where join instructions such as
  "install version 1.21.4, ask in Discord for the whitelist" belong. The mod
  never sends these, so they never get overwritten by a heartbeat;
- **Remove**, which deletes the server on WWG. The mod recreates it on its
  next heartbeat unless you revoke the key.

## 5. Rotate or revoke

On the same card every key has **Revoke**. Revoking is immediate: every
server that key reported goes offline now, and the next heartbeat gets a
`403 key_revoked`. Reporters in this repo stop and log a clear message on
that status instead of retrying.

Rotate by creating the new key first, moving it into the config, restarting
the reporter, then revoking the old one. The server keeps its `external_id`,
so it stays the same server on WWG with its likes, followers and comments.

If a key leaks, revoke it first and ask questions later.

## 6. What each error means

| Response | Cause | Do |
|---|---|---|
| `401 invalid_key` | No `Authorization` header, wrong prefix, a copy with a stray space or line break, or a key that never existed | Check the header reads `Bearer wwg_gs_...` with nothing else in it |
| `403 key_revoked` | The key was revoked on the profile | Create a new key |
| `403 owner_inactive` | The account that owns the key is deactivated | Contact WWG staff |
| `400 validation` | A field failed the contract; `error` says which (an unknown `template`, an `http://` link, a bad `external_id`) | Fix the config; the first heartbeat catches typos on purpose |
| `409 server_limit` | Ten servers on this key or twenty on your account | Remove a server on your profile |
| `413 body_too_large` | Over 32 KB | Trim the player list or `meta` |
| `429 rate_limited` | More than one heartbeat per 15 s for one server, or 60 calls a minute on the key | Wait `Retry-After` seconds |
| `200` with `"hidden": true` | The name or MOTD tripped the word screen; staff will look before it shows | Nothing, or rename and wait |

## 7. Privacy, in one paragraph

A reporter publishes your server's join address and your players' names on a
public page. Every example here has a switch to send only the count. Players'
IPs, Steam IDs and Discord IDs are never sent; the API would drop a Discord
id anyway. Who likes or follows your server is never listed, only counted.
