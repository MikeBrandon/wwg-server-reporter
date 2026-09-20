#!/usr/bin/env node
/**
 * WWG Server Reporter, Node sidecar. No dependencies, Node 18 or newer.
 *
 *   node reporter.mjs --check      confirm the key (GET /me)
 *   node reporter.mjs --once       one heartbeat per server, then exit
 *   node reporter.mjs              every 30 s until SIGINT/SIGTERM; then /offline
 *   node reporter.mjs --offline    mark every configured server offline, then exit
 *   node reporter.mjs --dry-run    print payloads, send nothing
 *
 * Same config.json as the Python sidecar. Sources: static, statusfile, command, fivem.
 */
import fs from 'node:fs';
import { execSync } from 'node:child_process';

const VERSION = '1.0.0';
const DEFAULT_BASE = 'https://watuwagaming.site/api/gs/v1';
const MAX_PLAYERS = 100;
const MAX_BODY = 32 * 1024;
const MIN_INTERVAL = 15;
const UA = `wwg-server-reporter/${VERSION} node`;

const args = new Set(process.argv.slice(2));
const flag = (name) => args.has(name);
const opt = (name, def) => { const i = process.argv.indexOf(name); return i > -1 ? process.argv[i + 1] : def; };
const log = (level, msg) => console[level === 'error' ? 'error' : 'log'](`${new Date().toISOString().slice(11, 19)} ${level.toUpperCase()} ${msg}`);

class SourceUnavailable extends Error {}
class StopReporter extends Error {}

function loadConfig(path) {
  let cfg;
  try { cfg = JSON.parse(fs.readFileSync(path, 'utf8')); }
  catch (e) { console.error(`Cannot read ${path}: ${e.message}. Copy config.example.json to config.json and edit it.`); process.exit(2); }
  const key = (cfg.key || process.env[cfg.key_env || 'WWG_GS_KEY'] || '').trim();
  if (!key) { console.error('No key. Set WWG_GS_KEY (preferred) or "key" in the config. Create one at https://watuwagaming.site/developer#game-server-api'); process.exit(2); }
  if (!key.startsWith('wwg_gs_') || key.length < 47) { console.error('That does not look like a WWG key (wwg_gs_ followed by 40 characters).'); process.exit(2); }
  cfg._key = key;
  cfg.api_base = (cfg.api_base || DEFAULT_BASE).replace(/\/+$/, '');
  cfg.interval_seconds = Math.max(MIN_INTERVAL, Number(cfg.interval_seconds) || 30);
  if (!Array.isArray(cfg.servers) || cfg.servers.length === 0) { console.error('Config has no "servers".'); process.exit(2); }
  for (const s of cfg.servers) {
    for (const k of ['external_id', 'game', 'name']) if (!String(s[k] || '').trim()) { console.error(`Server ${s.external_id || '?'} is missing "${k}".`); process.exit(2); }
    if (!/^[A-Za-z0-9_.-]{1,80}$/.test(s.external_id)) { console.error(`external_id ${s.external_id} must be 1 to 80 of A-Z a-z 0-9 _ . -`); process.exit(2); }
    s.source = s.source || { type: 'static' };
    if (!SOURCES[s.source.type || 'static']) { console.error(`Server ${s.external_id}: unknown source type ${s.source.type}. Known: ${Object.keys(SOURCES).join(', ')}`); process.exit(2); }
  }
  return cfg;
}

async function call(cfg, method, path, body) {
  const res = await fetch(cfg.api_base + path, {
    method,
    headers: { Authorization: `Bearer ${cfg._key}`, 'Content-Type': 'application/json', Accept: 'application/json', 'User-Agent': UA },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(10_000),
  });
  let data = {};
  try { data = await res.json(); } catch { data = { error: 'non-JSON response' }; }
  return { status: res.status, headers: res.headers, data };
}

async function getJSON(url) {
  const res = await fetch(url, { headers: { 'User-Agent': UA }, signal: AbortSignal.timeout(5_000) });
  if (!res.ok) throw new SourceUnavailable(`${url}: HTTP ${res.status}`);
  return res.json();
}

const SOURCES = {
  static: async (src) => Object.fromEntries(Object.entries(src).filter(([k]) => k !== 'type')),
  statusfile: async (src) => {
    const path = src.path || 'status.json';
    const maxAge = Number(src.max_age_seconds) || 120;
    let st;
    try { st = fs.statSync(path); } catch (e) { throw new SourceUnavailable(`statusfile ${path}: ${e.message}`); }
    const age = (Date.now() - st.mtimeMs) / 1000;
    if (age > maxAge) throw new SourceUnavailable(`${path} is ${Math.round(age)}s old (max ${maxAge}); is the server writing it?`);
    try { const d = JSON.parse(fs.readFileSync(path, 'utf8')); if (!d || typeof d !== 'object' || Array.isArray(d)) throw new Error('not an object'); return d; }
    catch (e) { throw new SourceUnavailable(`statusfile ${path}: ${e.message}`); }
  },
  command: async (src) => {
    if (!src.command) throw new SourceUnavailable('command source needs "command"');
    let out;
    try { out = execSync(src.command, { timeout: (Number(src.timeout) || 10) * 1000, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }); }
    catch (e) { throw new SourceUnavailable(`command failed: ${(e.stderr || e.message || '').toString().trim().slice(0, 200)}`); }
    try { const d = JSON.parse(out); if (!d || typeof d !== 'object' || Array.isArray(d)) throw new Error('not an object'); return d; }
    catch (e) { throw new SourceUnavailable(`command did not print a JSON object: ${e.message}`); }
  },
  fivem: async (src) => {
    const base = (src.base || 'http://127.0.0.1:30120').replace(/\/+$/, '');
    let info, players;
    try { [info, players] = await Promise.all([getJSON(base + '/info.json'), getJSON(base + '/players.json')]); }
    catch (e) { throw new SourceUnavailable(`fivem ${base}: ${e.message}`); }
    const vars = info.vars || {};
    const out = {
      player_count: players.length,
      players: players.filter((p) => p && p.name).slice(0, MAX_PLAYERS).map((p) => ({ name: p.name })),
    };
    if (vars.sv_maxClients) out.max_players = Number(vars.sv_maxClients) || undefined;
    if (vars.sv_projectName) out.name = String(vars.sv_projectName).replace(/\^\d/g, '').slice(0, 80);
    if (vars.sv_projectDesc) out.motd = String(vars.sv_projectDesc).replace(/\^\d/g, '').slice(0, 200);
    if (info.server) out.version = String(info.server).slice(0, 40);
    return out;
  },
};

function buildPayload(server, dynamic) {
  const body = {};
  for (const [k, v] of Object.entries(dynamic)) if (v !== null && v !== undefined) body[k] = v;
  for (const [k, v] of Object.entries(server)) {
    if (k === 'source' || v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0)) continue;
    body[k] = v; // identity from the config wins
  }
  if (Array.isArray(body.players)) {
    body.players = body.players.slice(0, MAX_PLAYERS);
    if (body.player_count === undefined) body.player_count = body.players.length;
  }
  for (const trim of ['players', 'meta', 'state']) {
    while (Buffer.byteLength(JSON.stringify(body)) > MAX_BODY && body[trim]) {
      if (trim === 'players' && body.players.length > 10) body.players = body.players.slice(0, Math.floor(body.players.length / 2));
      else delete body[trim];
    }
  }
  return body;
}

const announced = new Set();

async function heartbeatAll(cfg, dry) {
  let nextIn = cfg.interval_seconds;
  for (const server of cfg.servers) {
    const ext = server.external_id;
    let dynamic;
    try { dynamic = await SOURCES[server.source.type || 'static'](server.source, server); }
    catch (e) {
      if (e instanceof SourceUnavailable) { log('warn', `${ext}: ${e.message}. Skipping this heartbeat; WWG shows offline after 90 s.`); continue; }
      throw e;
    }
    const body = buildPayload(server, dynamic);
    if (dry) { console.log(JSON.stringify(body, null, 2)); continue; }
    let r;
    try { r = await call(cfg, 'POST', '/heartbeat', body); }
    catch (e) { log('warn', `${ext}: WWG unreachable (${e.message}). Trying again next tick.`); continue; }
    if (r.status === 200) {
      if (!announced.has(ext)) { log('info', `${ext}: reporting as server #${r.data.server_id}, ${r.data.url}`); announced.add(ext); }
      log('info', `${ext}: ok, ${body.player_count ?? 0} on`);
      if (r.data.hidden) log('warn', `${ext}: held by the word screen (name or MOTD); staff will look before it shows.`);
      nextIn = Math.max(MIN_INTERVAL, Number(r.data.next_heartbeat_in) || nextIn);
    } else if (r.status === 429) {
      const retry = Number(r.headers.get('retry-after')) || MIN_INTERVAL;
      log('warn', `${ext}: rate limited, waiting ${retry}s`); nextIn = Math.max(nextIn, retry);
    } else if (r.status === 401 || r.status === 403) {
      throw new StopReporter(`${r.data.code || r.status}: ${r.data.error || 'key rejected'}`);
    } else if (r.status === 409) {
      log('error', `${ext}: ${r.data.error} Remove a server on your Developer page to free a slot.`);
    } else if (r.status === 400) {
      log('error', `${ext}: rejected: ${r.data.error} (fix the config)`);
    } else {
      log('error', `${ext}: HTTP ${r.status}: ${r.data.error || JSON.stringify(r.data)}`);
    }
  }
  return nextIn;
}

async function offlineAll(cfg) {
  for (const s of cfg.servers) {
    try { const r = await call(cfg, 'POST', '/offline', { external_id: s.external_id }); log('info', `${s.external_id}: offline sent (HTTP ${r.status}, ended=${r.data.ended})`); }
    catch (e) { log('warn', `${s.external_id}: offline not sent (${e.message}); WWG shows offline after 90 s anyway.`); }
  }
}

async function check(cfg) {
  const r = await call(cfg, 'GET', '/me');
  if (r.status !== 200) { console.log(`HTTP ${r.status}: ${r.data.error || JSON.stringify(r.data)} (${r.data.code || ''})`); return 1; }
  const k = r.data.key || {};
  console.log(`Key OK: ${k.name} (wwg_gs_${k.prefix}...), created ${k.created_at}`);
  const servers = r.data.servers || [];
  console.log(`Servers reported by this key: ${servers.length}`);
  for (const s of servers) console.log(`  #${s.id} ${s.external_id}: ${s.name} (${s.game_name || s.game_slug}), ${s.is_live ? 'LIVE' : s.status}, ${s.player_count} on`);
  const known = new Set(servers.map((s) => s.external_id));
  for (const s of cfg.servers) if (!known.has(s.external_id)) console.log(`  ${s.external_id}: not reported yet (first heartbeat creates it)`);
  return 0;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const cfg = loadConfig(opt('--config', process.env.WWG_REPORTER_CONFIG || 'config.json'));
  if (flag('--check')) process.exit(await check(cfg));
  if (flag('--offline')) { await offlineAll(cfg); process.exit(0); }
  if (flag('--dry-run')) { await heartbeatAll(cfg, true); process.exit(0); }
  if (flag('--once')) {
    try { await heartbeatAll(cfg, false); process.exit(0); }
    catch (e) { if (e instanceof StopReporter) { log('error', `Key rejected (${e.message})`); process.exit(2); } throw e; }
  }
  let stop = false;
  const onSignal = (sig) => { log('info', `Stopping (${sig})`); stop = true; };
  process.on('SIGINT', onSignal); process.on('SIGTERM', onSignal);
  log('info', `Reporting ${cfg.servers.length} server(s) to ${cfg.api_base} every ${cfg.interval_seconds}s`);
  try {
    while (!stop) {
      const wait = await heartbeatAll(cfg, false);
      for (let i = 0; i < wait && !stop; i++) await sleep(1000);
    }
  } catch (e) {
    if (e instanceof StopReporter) { log('error', `Key rejected (${e.message}). Stopping. Create a new key at https://watuwagaming.site/developer#game-server-api`); process.exit(2); }
    throw e;
  }
  await offlineAll(cfg);
  process.exit(0);
}

main().catch((e) => { log('error', e.stack || e.message); process.exit(1); });
