#!/usr/bin/env python3
"""WWG Server Reporter, the generic sidecar.

Reads config.json, asks each configured source for the server's live state
every 30 seconds and POSTs a heartbeat to the WWG Game Server Presence API.
Standard library only. `python-a2s` is optional, for the `a2s` source.

    python reporter.py --check      confirm the key (GET /me) and list what WWG has
    python reporter.py --once       one heartbeat per server, print the result and exit
    python reporter.py              run until stopped; sends /offline on Ctrl+C or SIGTERM
    python reporter.py --offline    mark every configured server offline and exit
    python reporter.py --dry-run    print the payloads that would be sent, send nothing

Sources (config "source": {"type": ...}):
    static          nothing dynamic; extra fields in the source block are sent as-is
    statusfile      read a JSON file in heartbeat shape ("path", "max_age_seconds")
    command         run a command that prints a JSON object ("command", "timeout")
    minecraft_ping  Minecraft server list ping ("host", "port")
    a2s             Steam query: CS2, Valheim, Palworld, ARK, Rust, GMod ("host", "port")
    fivem           FiveM info.json and players.json ("base")
    palworld        Palworld REST API ("base", "user", "password_env")
    rcon            Source RCON: Project Zomboid, Minecraft, CS2 and other Source games
                    ("host", "port", "password_env", "format": zomboid|minecraft|source|lines, "command")

Identity fields in the server block (external_id, game, name, template,
join_address, tags, links ...) always win over what a source returns.
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import signal
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Optional, Tuple

VERSION = "1.0.0"
DEFAULT_BASE = "https://watuwagaming.site/api/gs/v1"
KEY_PREFIX = "wwg_gs_"
MAX_PLAYERS = 100
MAX_BODY = 32 * 1024
MIN_INTERVAL = 15
USER_AGENT = f"wwg-server-reporter/{VERSION} python"

log = logging.getLogger("wwg-reporter")


class StopReporter(Exception):
    """The key is dead (401/403). Stop and tell the operator; never retry."""


class SourceUnavailable(Exception):
    """The game server could not be read. Skip this heartbeat; WWG will show offline."""


# ── config ──────────────────────────────────────────────────────────────────

def load_config(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except FileNotFoundError:
        sys.exit(f"No config at {path}. Copy config.example.json to config.json and edit it.")
    except json.JSONDecodeError as exc:
        sys.exit(f"{path} is not valid JSON: {exc}")

    key = (cfg.get("key") or os.environ.get(cfg.get("key_env", "WWG_GS_KEY"), "")).strip()
    if not key:
        sys.exit("No key. Set the WWG_GS_KEY environment variable (preferred) or \"key\" in the config. "
                 "Create one at https://watuwagaming.site/developer#game-server-api")
    if not key.startswith(KEY_PREFIX) or len(key) < len(KEY_PREFIX) + 40:
        sys.exit("That does not look like a WWG key (wwg_gs_ followed by 40 characters). Check for a partial copy.")
    cfg["_key"] = key
    cfg["api_base"] = (cfg.get("api_base") or DEFAULT_BASE).rstrip("/")
    cfg["interval_seconds"] = max(MIN_INTERVAL, int(cfg.get("interval_seconds", 30)))

    servers = cfg.get("servers") or []
    if not servers:
        sys.exit("Config has no \"servers\". Add at least one with external_id, game and name.")
    for s in servers:
        for required in ("external_id", "game", "name"):
            if not str(s.get(required, "")).strip():
                sys.exit(f"Server {s.get('external_id', '?')!r} is missing \"{required}\".")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", s["external_id"]):
            sys.exit(f"external_id {s['external_id']!r} must be 1 to 80 of A-Z a-z 0-9 _ . -")
        src = s.setdefault("source", {"type": "static"})
        if src.get("type", "static") not in SOURCES:
            sys.exit(f"Server {s['external_id']}: unknown source type {src.get('type')!r}. Known: {', '.join(SOURCES)}")
    return cfg


# ── HTTP ────────────────────────────────────────────────────────────────────

class WwgClient:
    def __init__(self, base: str, key: str, timeout: float = 10.0):
        self.base, self.key, self.timeout = base, key, timeout

    def _call(self, method: str, path: str, body: Optional[dict] = None) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                return res.status, {k.lower(): v for k, v in res.headers.items()}, _json_or_text(res.read())
        except urllib.error.HTTPError as exc:
            return exc.code, {k.lower(): v for k, v in exc.headers.items()}, _json_or_text(exc.read())

    def me(self):
        return self._call("GET", "/me")

    def heartbeat(self, body: dict):
        return self._call("POST", "/heartbeat", body)

    def offline(self, external_id: str):
        return self._call("POST", "/offline", {"external_id": external_id})


def _json_or_text(raw: bytes) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw.decode("utf-8", "replace"))
        return parsed if isinstance(parsed, dict) else {"data": parsed}
    except ValueError:
        return {"error": raw.decode("utf-8", "replace")[:200]}


def _http_get(url: str, timeout: float = 5.0, headers: Optional[Dict[str, str]] = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read()


# ── sources ─────────────────────────────────────────────────────────────────

def src_static(src: dict, server: dict) -> dict:
    return {k: v for k, v in src.items() if k != "type"}


def src_statusfile(src: dict, server: dict) -> dict:
    path = src.get("path", "status.json")
    max_age = float(src.get("max_age_seconds", 120))
    try:
        age = time.time() - os.path.getmtime(path)
        if age > max_age:
            raise SourceUnavailable(f"{path} is {int(age)}s old (max {int(max_age)}); is the server writing it?")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise SourceUnavailable(f"statusfile {path}: {exc}")
    except ValueError as exc:
        raise SourceUnavailable(f"statusfile {path} is not JSON: {exc}")
    if not isinstance(data, dict):
        raise SourceUnavailable(f"statusfile {path} must hold a JSON object")
    return data


def src_command(src: dict, server: dict) -> dict:
    cmd = src.get("command")
    if not cmd:
        raise SourceUnavailable("command source needs \"command\"")
    try:
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=float(src.get("timeout", 10)))
    except subprocess.TimeoutExpired:
        raise SourceUnavailable(f"command timed out: {cmd}")
    if out.returncode != 0:
        raise SourceUnavailable(f"command exited {out.returncode}: {out.stderr.strip()[:200]}")
    try:
        data = json.loads(out.stdout)
    except ValueError as exc:
        raise SourceUnavailable(f"command did not print JSON: {exc}")
    if not isinstance(data, dict):
        raise SourceUnavailable("command must print a JSON object")
    return data


# Minecraft server list ping: the same query the client's multiplayer screen
# sends. Works on any Java server with no plugin. Gives online, max, version,
# MOTD and up to 12 sample names (what the server chooses to show).

def _varint(n: int) -> bytes:
    n &= 0xFFFFFFFF
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _read_varint(sock: socket.socket) -> int:
    num = shift = 0
    while True:
        b = sock.recv(1)
        if not b:
            raise SourceUnavailable("minecraft ping: connection closed")
        num |= (b[0] & 0x7F) << shift
        shift += 7
        if not b[0] & 0x80:
            return num
        if shift > 35:
            raise SourceUnavailable("minecraft ping: bad varint")


def _mc_packet(pid: int, payload: bytes) -> bytes:
    data = _varint(pid) + payload
    return _varint(len(data)) + data


def _mc_flatten(desc: Any) -> str:
    """A chat component (string, or {"text", "extra": [...]}) to plain text."""
    if isinstance(desc, str):
        return desc
    if isinstance(desc, dict):
        return str(desc.get("text", "")) + "".join(_mc_flatten(e) for e in desc.get("extra", []) or [])
    return ""


def _mc_text(desc: Any) -> str:
    return re.sub(r"§.", "", _mc_flatten(desc)).strip()


def src_minecraft_ping(src: dict, server: dict) -> dict:
    host, port = src.get("host", "127.0.0.1"), int(src.get("port", 25565))
    try:
        with socket.create_connection((host, port), timeout=float(src.get("timeout", 5))) as s:
            handshake = _varint(-1) + _varint(len(host.encode())) + host.encode() + struct.pack(">H", port) + _varint(1)
            s.sendall(_mc_packet(0x00, handshake))
            s.sendall(_mc_packet(0x00, b""))
            _read_varint(s)  # packet length
            if _read_varint(s) != 0x00:
                raise SourceUnavailable("minecraft ping: unexpected packet")
            size = _read_varint(s)
            buf = b""
            while len(buf) < size:
                chunk = s.recv(min(65536, size - len(buf)))
                if not chunk:
                    break
                buf += chunk
        status = json.loads(buf.decode("utf-8", "replace"))
    except (OSError, ValueError) as exc:
        raise SourceUnavailable(f"minecraft ping {host}:{port}: {exc}")
    players = status.get("players") or {}
    sample = players.get("sample") or []
    out: Dict[str, Any] = {
        "player_count": int(players.get("online", 0) or 0),
        "players": [{"name": p["name"]} for p in sample if isinstance(p, dict) and p.get("name")][:MAX_PLAYERS],
    }
    if players.get("max") is not None:
        out["max_players"] = int(players["max"])
    version = (status.get("version") or {}).get("name")
    if version:
        out["version"] = str(version)[:40]
    motd = _mc_text(status.get("description"))
    if motd:
        out["motd"] = motd[:200]
    return out


def src_a2s(src: dict, server: dict) -> dict:
    try:
        import a2s  # type: ignore
    except ImportError:
        raise SourceUnavailable("a2s source needs `pip install python-a2s`")
    addr = (src.get("host", "127.0.0.1"), int(src.get("port", 27015)))
    timeout = float(src.get("timeout", 3))
    try:
        info = a2s.info(addr, timeout=timeout)
    except Exception as exc:  # a2s raises several socket-level types
        raise SourceUnavailable(f"a2s {addr[0]}:{addr[1]}: {exc}")
    out: Dict[str, Any] = {
        "player_count": int(getattr(info, "player_count", 0) or 0),
        "max_players": int(getattr(info, "max_players", 0) or 0),
    }
    if getattr(info, "map_name", None):
        out["map"] = str(info.map_name)[:80]
    if getattr(info, "version", None):
        out["version"] = str(info.version)[:40]
    if getattr(info, "server_name", None):
        out["name"] = str(info.server_name)[:80]   # the config name wins if set
    if src.get("players", True):
        try:
            plist = a2s.players(addr, timeout=timeout)
            out["players"] = [{"name": p.name, "score": p.score} for p in plist if getattr(p, "name", "")][:MAX_PLAYERS]
        except Exception as exc:
            log.debug("a2s players failed: %s", exc)
    return out


def src_fivem(src: dict, server: dict) -> dict:
    base = (src.get("base") or "http://127.0.0.1:30120").rstrip("/")
    try:
        info = json.loads(_http_get(base + "/info.json"))
        players = json.loads(_http_get(base + "/players.json"))
    except (OSError, ValueError) as exc:
        raise SourceUnavailable(f"fivem {base}: {exc}")
    vars_ = info.get("vars") or {}
    out: Dict[str, Any] = {
        "player_count": len(players),
        "players": [{"name": p.get("name")} for p in players if isinstance(p, dict) and p.get("name")][:MAX_PLAYERS],
    }
    if vars_.get("sv_maxClients"):
        try:
            out["max_players"] = int(vars_["sv_maxClients"])
        except ValueError:
            pass
    if vars_.get("sv_projectName"):
        out["name"] = re.sub(r"\^\d", "", str(vars_["sv_projectName"]))[:80]
    if vars_.get("sv_projectDesc"):
        out["motd"] = re.sub(r"\^\d", "", str(vars_["sv_projectDesc"]))[:200]
    if info.get("server"):
        out["version"] = str(info["server"])[:40]
    return out


def src_palworld(src: dict, server: dict) -> dict:
    base = (src.get("base") or "http://127.0.0.1:8212").rstrip("/")
    user = src.get("user", "admin")
    password = os.environ.get(src.get("password_env", "PALWORLD_ADMIN_PASSWORD"), src.get("password", ""))
    auth = {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}
    try:
        info = json.loads(_http_get(base + "/v1/api/info", headers=auth))
        players = json.loads(_http_get(base + "/v1/api/players", headers=auth)).get("players", [])
    except (OSError, ValueError) as exc:
        raise SourceUnavailable(f"palworld {base}: {exc}")
    out: Dict[str, Any] = {
        "player_count": len(players),
        "players": [{"name": p.get("name"), "score": p.get("level")} for p in players if isinstance(p, dict) and p.get("name")][:MAX_PLAYERS],
    }
    if info.get("servername"):
        out["name"] = str(info["servername"])[:80]
    if info.get("version"):
        out["version"] = str(info["version"])[:40]
    if info.get("description"):
        out["motd"] = str(info["description"])[:200]
    try:
        metrics = json.loads(_http_get(base + "/v1/api/metrics", headers=auth))
        if metrics.get("maxplayernum") is not None:
            out["max_players"] = int(metrics["maxplayernum"])
        if metrics.get("days") is not None:
            out["state"] = {"world": {"day": int(metrics["days"])}}
    except (OSError, ValueError):
        pass
    return out


# Source RCON (Minecraft, Project Zomboid, CS2 and other Source games, 7 Days to
# Die's telnet is different, Rust uses WebRCON). Packet: int32 size, int32 id,
# int32 type, body, two NULs. Type 3 auth, 2 command, 0 response; an auth
# failure answers with id -1.

def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise SourceUnavailable("rcon: connection closed")
        buf += chunk
    return buf


def _rcon_packet(pid: int, ptype: int, body: str) -> bytes:
    payload = struct.pack("<ii", pid, ptype) + body.encode("utf-8") + b"\x00\x00"
    return struct.pack("<i", len(payload)) + payload


def _rcon_read(sock: socket.socket) -> Tuple[int, int, str]:
    (size,) = struct.unpack("<i", _recv_exact(sock, 4))
    if size < 10 or size > 1 << 20:
        raise SourceUnavailable(f"rcon: bad packet size {size}")
    data = _recv_exact(sock, size)
    pid, ptype = struct.unpack("<ii", data[:8])
    return pid, ptype, data[8:-2].decode("utf-8", "replace")


def rcon_command(host: str, port: int, password: str, command: str, timeout: float = 5.0) -> str:
    """Authenticate, run one command, return its text (all packets)."""
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(_rcon_packet(1, 3, password))
        pid, ptype, _ = _rcon_read(s)
        if ptype == 0:  # some servers send an empty response before the auth reply
            pid, ptype, _ = _rcon_read(s)
        if pid == -1:
            raise SourceUnavailable("rcon: wrong password")
        s.sendall(_rcon_packet(2, 2, command))
        _, _, body = _rcon_read(s)
        # Long answers arrive in several packets; take what arrives shortly after.
        s.settimeout(0.3)
        try:
            while True:
                _, _, more = _rcon_read(s)
                body += more
        except (socket.timeout, TimeoutError, SourceUnavailable):
            pass
        return body


def _players_zomboid(text: str) -> dict:
    # "Players connected (2): \n-Kip\n-Amani"
    names = [ln.strip()[1:].strip() for ln in text.splitlines() if ln.strip().startswith("-")]
    m = re.search(r"\((\d+)\)", text)
    return {"player_count": int(m.group(1)) if m else len(names), "players": [{"name": n} for n in names if n]}


def _players_minecraft(text: str) -> dict:
    # "There are 2 of a max of 20 players online: Steve, Alex"
    m = re.search(r"There are (\d+) of a max(?: of)? (\d+) players online:?\s*(.*)", text, re.S)
    if not m:
        return {"player_count": 0, "players": []}
    names = [n.strip() for n in m.group(3).split(",") if n.strip()]
    return {"player_count": int(m.group(1)), "max_players": int(m.group(2)), "players": [{"name": n} for n in names]}


def _players_source(text: str) -> dict:
    # CS2 / Source "status": 'players : 3 humans, 0 bots (10 max)', 'map : de_mirage', '#  2 1 "Kip" ...'
    out: Dict[str, Any] = {}
    m = re.search(r"players\s*:\s*(\d+)\s+humans?,\s*(\d+)\s+bots?\s*\((\d+)(?:/\d+)?\s*max\)", text)
    if m:
        out["player_count"], out["max_players"] = int(m.group(1)), int(m.group(3))
    names = re.findall(r'^#\s*\d+\s+\S+\s+"([^"]+)"', text, re.M)
    if names:
        out["players"] = [{"name": n} for n in names]
        out.setdefault("player_count", len(names))
    mm = re.search(r"^map\s*:\s*(\S+)", text, re.M)
    if mm:
        out["map"] = mm.group(1)
    return out


def _players_lines(text: str) -> dict:
    names = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return {"player_count": len(names), "players": [{"name": n} for n in names]}


RCON_FORMATS: Dict[str, Callable[[str], dict]] = {
    "zomboid": _players_zomboid, "minecraft": _players_minecraft, "source": _players_source, "lines": _players_lines,
}
RCON_DEFAULT_COMMAND = {"zomboid": "players", "minecraft": "list", "source": "status", "lines": "players"}


def src_rcon(src: dict, server: dict) -> dict:
    fmt = str(src.get("format", "lines")).lower()
    if fmt not in RCON_FORMATS:
        raise SourceUnavailable(f"rcon: unknown format {fmt!r}; use one of {', '.join(RCON_FORMATS)}")
    host, port = src.get("host", "127.0.0.1"), int(src.get("port", 27015))
    password = os.environ.get(src.get("password_env", "RCON_PASSWORD"), src.get("password", ""))
    command = src.get("command") or RCON_DEFAULT_COMMAND[fmt]
    try:
        text = rcon_command(host, port, password, command, float(src.get("timeout", 5)))
    except (OSError, ValueError, struct.error) as exc:
        raise SourceUnavailable(f"rcon {host}:{port}: {exc}")
    out = RCON_FORMATS[fmt](text)
    out["players"] = out.get("players", [])[:MAX_PLAYERS]
    return out


SOURCES: Dict[str, Callable[[dict, dict], dict]] = {
    "static": src_static,
    "statusfile": src_statusfile,
    "command": src_command,
    "minecraft_ping": src_minecraft_ping,
    "a2s": src_a2s,
    "fivem": src_fivem,
    "palworld": src_palworld,
    "rcon": src_rcon,
}


# ── payload ─────────────────────────────────────────────────────────────────

def build_payload(server: dict, dynamic: dict) -> dict:
    """Config (identity, chosen by the operator) wins over what the source saw."""
    static = {k: v for k, v in server.items() if k != "source" and v not in (None, "", [], {})}
    body: Dict[str, Any] = {k: v for k, v in dynamic.items() if v is not None}
    body.update(static)
    if isinstance(body.get("players"), list):
        body["players"] = body["players"][:MAX_PLAYERS]
        body.setdefault("player_count", len(body["players"]))
    # Stay under 32 KB: shorten the player list first, then drop meta, then state.
    for trim in ("players", "meta", "state"):
        while len(json.dumps(body).encode()) > MAX_BODY and body.get(trim):
            if trim == "players" and len(body["players"]) > 10:
                body["players"] = body["players"][: len(body["players"]) // 2]
            else:
                body.pop(trim, None)
    return body


# ── loop ────────────────────────────────────────────────────────────────────

class Reporter:
    def __init__(self, cfg: dict, client: WwgClient):
        self.cfg, self.client = cfg, client
        self.stop = False
        self.announced: set = set()

    def heartbeat_all(self, dry: bool = False) -> float:
        """One pass over every server. Returns how long to sleep."""
        next_in = float(self.cfg["interval_seconds"])
        for server in self.cfg["servers"]:
            ext = server["external_id"]
            src = server.get("source", {"type": "static"})
            try:
                dynamic = SOURCES[src.get("type", "static")](src, server)
            except SourceUnavailable as exc:
                log.warning("%s: %s. Skipping this heartbeat; WWG shows offline after 90 s.", ext, exc)
                continue
            body = build_payload(server, dynamic)
            if dry:
                print(json.dumps(body, indent=2))
                continue
            try:
                status, headers, data = self.client.heartbeat(body)
            except (urllib.error.URLError, socket.timeout, OSError) as exc:
                log.warning("%s: WWG unreachable (%s). Trying again next tick.", ext, exc)
                continue
            if status == 200:
                if ext not in self.announced:
                    log.info("%s: reporting as server #%s, %s", ext, data.get("server_id"), data.get("url"))
                    self.announced.add(ext)
                log.info("%s: ok, %s on", ext, body.get("player_count", 0))
                if data.get("hidden"):
                    log.warning("%s: held by the word screen (name or MOTD); staff will look before it shows.", ext)
                next_in = max(MIN_INTERVAL, float(data.get("next_heartbeat_in", next_in)))
            elif status == 429:
                retry = int(headers.get("retry-after", MIN_INTERVAL) or MIN_INTERVAL)
                log.warning("%s: rate limited, waiting %ss", ext, retry)
                next_in = max(next_in, retry)
            elif status in (401, 403):
                raise StopReporter(f"{data.get('code', status)}: {data.get('error', 'key rejected')}")
            elif status == 409:
                log.error("%s: %s Remove a server on your Developer page to free a slot.", ext, data.get("error"))
            elif status == 400:
                log.error("%s: rejected: %s (fix the config)", ext, data.get("error"))
            else:
                log.error("%s: HTTP %s: %s", ext, status, data.get("error") or data)
        return next_in

    def offline_all(self) -> None:
        for server in self.cfg["servers"]:
            try:
                status, _, data = self.client.offline(server["external_id"])
                log.info("%s: offline sent (HTTP %s, ended=%s)", server["external_id"], status, data.get("ended"))
            except (urllib.error.URLError, OSError) as exc:
                log.warning("%s: offline not sent (%s); WWG shows offline after 90 s anyway.", server["external_id"], exc)

    def run(self) -> int:
        def on_signal(signum, frame):
            log.info("Stopping (signal %s)", signum)
            self.stop = True
        signal.signal(signal.SIGINT, on_signal)
        signal.signal(signal.SIGTERM, on_signal)
        log.info("Reporting %d server(s) to %s every %ss", len(self.cfg["servers"]), self.cfg["api_base"], self.cfg["interval_seconds"])
        try:
            while not self.stop:
                wait = self.heartbeat_all()
                for _ in range(int(wait)):
                    if self.stop:
                        break
                    time.sleep(1)
        except StopReporter as exc:
            log.error("Key rejected (%s). Stopping. Create a new key at https://watuwagaming.site/developer#game-server-api", exc)
            return 2
        self.offline_all()
        return 0


def cmd_check(cfg: dict, client: WwgClient) -> int:
    status, _, data = client.me()
    if status != 200:
        print(f"HTTP {status}: {data.get('error', data)} ({data.get('code', '')})")
        return 1
    k = data.get("key", {})
    print(f"Key OK: {k.get('name')} (wwg_gs_{k.get('prefix')}...), created {k.get('created_at')}")
    servers = data.get("servers", [])
    print(f"Servers reported by this key: {len(servers)}")
    for s in servers:
        state = "LIVE" if s.get("is_live") else s.get("status", "?")
        print(f"  #{s.get('id')} {s.get('external_id')}: {s.get('name')} ({s.get('game_name') or s.get('game_slug')}), {state}, {s.get('player_count')} on")
    configured = {s["external_id"] for s in cfg["servers"]}
    known = {s.get("external_id") for s in servers}
    for ext in sorted(configured - known):
        print(f"  {ext}: not reported yet (first heartbeat creates it)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Report game servers to watuwagaming.site")
    ap.add_argument("--config", default=os.environ.get("WWG_REPORTER_CONFIG", "config.json"))
    ap.add_argument("--check", action="store_true", help="confirm the key and list servers (GET /me)")
    ap.add_argument("--once", action="store_true", help="one heartbeat per server, then exit")
    ap.add_argument("--offline", action="store_true", help="mark every configured server offline, then exit")
    ap.add_argument("--dry-run", action="store_true", help="print payloads, send nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    cfg = load_config(args.config)
    client = WwgClient(cfg["api_base"], cfg["_key"])
    rep = Reporter(cfg, client)
    if args.check:
        return cmd_check(cfg, client)
    if args.offline:
        rep.offline_all()
        return 0
    if args.dry_run:
        rep.heartbeat_all(dry=True)
        return 0
    if args.once:
        try:
            rep.heartbeat_all()
        except StopReporter as exc:
            log.error("Key rejected (%s)", exc)
            return 2
        return 0
    return rep.run()


if __name__ == "__main__":
    sys.exit(main())
