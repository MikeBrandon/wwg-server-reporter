#!/usr/bin/env bash
# Confirm a WWG Game Server API key works: GET /me and print what WWG has for it.
#   export WWG_GS_KEY=wwg_gs_...   then   bash tools/check-key.sh
# Optional: WWG_API_BASE to point at another instance (default https://watuwagaming.site/api/gs/v1).
set -u
BASE="${WWG_API_BASE:-https://watuwagaming.site/api/gs/v1}"
KEY="${WWG_GS_KEY:-}"

if [ -z "$KEY" ]; then
  echo "WWG_GS_KEY is not set. Create a key at https://watuwagaming.site/profile#game-server-api and export it." >&2
  exit 2
fi
case "$KEY" in
  wwg_gs_*) ;;
  *) echo "That does not look like a WWG key (they start with wwg_gs_). Check for a stray space or a partial copy." >&2; exit 2 ;;
esac

code=$(curl -s -o /tmp/wwg-me.json -w "%{http_code}" "$BASE/me" -H "Authorization: Bearer $KEY" -H "User-Agent: wwg-server-reporter/check-key")
case "$code" in
  200)
    echo "Key OK."
    if command -v python3 >/dev/null 2>&1; then
      python3 - <<'EOF'
import json
d = json.load(open("/tmp/wwg-me.json"))
k = d.get("key", {})
print(f"  name: {k.get('name')}   prefix: wwg_gs_{k.get('prefix')}...   created: {k.get('created_at')}")
servers = d.get("servers", [])
print(f"  servers reported by this key: {len(servers)}")
for s in servers:
    state = "LIVE" if s.get("is_live") else s.get("status", "?")
    print(f"    #{s.get('id')} {s.get('external_id')}: {s.get('name')} ({s.get('game_name') or s.get('game_slug')}), {state}, {s.get('player_count')} on")
EOF
    else
      cat /tmp/wwg-me.json; echo
    fi
    ;;
  401) echo "401 invalid_key: the key is not recognised. Copy it again from the profile; watch for spaces." >&2; exit 1 ;;
  403) echo "403: the key was revoked or the account is inactive. Create a new key." >&2; cat /tmp/wwg-me.json >&2; echo >&2; exit 1 ;;
  000) echo "Could not reach $BASE. Is the site up, and does this box have outbound HTTPS?" >&2; exit 1 ;;
  *) echo "HTTP $code from $BASE/me:" >&2; cat /tmp/wwg-me.json >&2; echo >&2; exit 1 ;;
esac
rm -f /tmp/wwg-me.json
