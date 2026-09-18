# Templates: making the card read right for your game

A heartbeat's `template` picks the card layout on `/servers` and the detail
page. Each template has a headline (the big number top right) and a set of
`state` keys it draws. Send the template first, then the fields it headlines;
everything else is optional and drawn if present.

| Template | Use it for | Headline | Send at least |
|---|---|---|---|
| `players` | Co-op worlds, sandbox, minigames, anything without a match structure | player count | `players` or `player_count` |
| `match` | Round or score based team games (CS2, Valorant customs, EA FC lobbies, Rocket League) | `state.score`, else `state.round` | `state.phase`, `state.score` or `round`, `teams` or `players[].team`, `time_left_seconds` if the game has a clock |
| `world` | Survival and persistent worlds (Minecraft, Valheim, Palworld, ARK, Rust) | player count | `state.world.day`, `weather`, `difficulty`, plus `mode`, `version` |
| `lobby` | Anything with a waiting room or matchmaking queue | player count plus the queue | `state.queue.waiting`, `eta_seconds`, `state.phase` |
| `race` | Racing and time-trial servers | first `state.stats` entry | `state.stats` (Track, Lap, Leader), `state.phase` |
| `custom` | Everything else | first `state.stats` entry | up to 8 `state.stats` you want shown large |

The `phase` pill shows while live for any template except when it says
`live` or `online` (the Live badge already says that).

## `players`

The default. A count, the names as chips, your chips for mode, map, version
and region.

```json
{
  "external_id": "creative-1", "game": "minecraft", "name": "WWG Creative",
  "template": "players", "mode": "Creative", "version": "1.21.4",
  "join_address": "creative.example.co.ke", "max_players": 40,
  "players": [{"name": "Steve"}, {"name": "Alex"}, {"name": "Wanjiru"}],
  "tags": ["creative", "plots"]
}
```

## `match`

Score or round as the headline, `mm:ss` clock, team blocks with members and
per-player scores.

```json
{
  "external_id": "cs2-scrim-1", "game": "counter-strike-2", "name": "WWG Scrims",
  "template": "match", "mode": "Competitive 5v5", "map": "de_mirage",
  "join_address": "cs.example.co.ke:27015", "max_players": 10, "player_count": 10,
  "players": [
    {"name": "Kip", "team": "CT", "score": 21}, {"name": "Wanjiru", "team": "CT", "score": 17},
    {"name": "Otieno", "team": "T", "score": 19}, {"name": "Amani", "team": "T", "score": 9}
  ],
  "state": {
    "phase": "live", "round": 14, "rounds_total": 24, "time_left_seconds": 95, "score": "9 - 5",
    "teams": [
      {"name": "CT", "score": 9, "color": "#5d79ae", "players": ["Kip", "Wanjiru"]},
      {"name": "T", "score": 5, "color": "#de9b35", "players": ["Otieno", "Amani"]}
    ]
  }
}
```

Between maps send `"phase": "warmup"` and drop `score`; the card falls back
to the round or the count. A finished match is `"phase": "ended"` until the
next one starts.

## `world`

Player count headline; day, time, weather and difficulty as chips on the
card and a table on the page.

```json
{
  "external_id": "valheim-main", "game": "valheim", "name": "WWG Valheim",
  "template": "world", "mode": "Normal", "version": "0.219.16",
  "join_address": "valheim.example.co.ke:2456", "max_players": 10, "player_count": 4,
  "players": [{"name": "Kip"}, {"name": "Amani"}, {"name": "Njeri"}, {"name": "Otieno"}],
  "state": {"world": {"day": 212, "time_of_day": "Evening", "weather": "Rain", "difficulty": "Normal", "seed": "wwg2026"}}
}
```

`day` is a number. `time_of_day` is any short string (`"14:20"`,
`"Evening"`). Leave out what your game does not have.

## `lobby`

Player count plus the queue: "3 in the queue, about 2:00 wait".

```json
{
  "external_id": "hub-1", "game": "minecraft", "name": "WWG Minigames Hub",
  "template": "lobby", "join_address": "play.example.co.ke", "max_players": 200, "player_count": 87,
  "state": {"phase": "waiting", "queue": {"waiting": 3, "eta_seconds": 120}}
}
```

## `race`

The first stat is the headline. Good stats: Track, Lap, Leader, Best lap.

```json
{
  "external_id": "ac-1", "game": "Assetto Corsa", "name": "WWG Track Nights",
  "template": "race", "map": "Brands Hatch GP", "max_players": 24, "player_count": 11,
  "players": [{"name": "Kip", "score": "1:24.883"}, {"name": "Amani", "score": "1:25.102"}],
  "state": {"phase": "live", "stats": [{"label": "Lap", "value": "7 / 12"}, {"label": "Leader", "value": "Kip"}, {"label": "Track", "value": "Brands Hatch GP"}]}
}
```

## `custom`

Up to eight of your own numbers, the first one large.

```json
{
  "external_id": "zomboid-1", "game": "Project Zomboid", "name": "WWG Knox County",
  "template": "custom", "max_players": 16, "player_count": 5,
  "state": {"stats": [{"label": "Day", "value": 63}, {"label": "Zombies killed", "value": 18422}, {"label": "Weather", "value": "Fog"}]}
}
```

## How the site adds to what you send

On top of the heartbeat, the card and the page show what the owner wrote on
the site (title, description, how to join, rules, Discord and website
buttons, icon and banner) and what members did (likes, followers, comments,
the all-time peak player count, and a Staff pick chip if staff featured it).
None of that comes from the heartbeat and none of it is overwritten by one.
