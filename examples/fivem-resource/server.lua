-- WWG Server Reporter for FiveM. Server side only.
--
-- Configure in server.cfg (never in this file, so the resource can be shared):
--   set wwg_gs_key "wwg_gs_..."                 -- from https://watuwagaming.site/developer#game-server-api
--   set wwg_external_id "fivem-rp"              -- stable id for THIS server
--   set wwg_game "Grand Theft Auto V"           -- WWG game slug or name
--   set wwg_server_name "WWG Roleplay"          -- defaults to sv_projectName
--   set wwg_join_url "https://cfx.re/join/xxxxxx"
--   set wwg_join_address ""                     -- ip:port, if you prefer
--   set wwg_region "Nairobi"
--   set wwg_tags "roleplay,whitelist"
--   set wwg_show_player_names 1                 -- 0 sends only the count
--   set wwg_interval_seconds 30
--   ensure wwg-reporter

local API_BASE   = GetConvar('wwg_api_base', 'https://watuwagaming.site/api/gs/v1')
local KEY        = GetConvar('wwg_gs_key', '')
local EXTERNAL   = GetConvar('wwg_external_id', 'fivem-1')
local GAME       = GetConvar('wwg_game', 'Grand Theft Auto V')
local NAME       = GetConvar('wwg_server_name', GetConvar('sv_projectName', 'FiveM server'))
local JOIN_URL   = GetConvar('wwg_join_url', '')
local JOIN_ADDR  = GetConvar('wwg_join_address', '')
local REGION     = GetConvar('wwg_region', '')
local TAGS       = GetConvar('wwg_tags', '')
local SHOW_NAMES = GetConvarInt('wwg_show_player_names', 1) == 1
local INTERVAL   = math.max(15, GetConvarInt('wwg_interval_seconds', 30))
local MAX_PLAYERS = 100

local stopped = false
local announced = false

local function stripColours(s)
  return (tostring(s or ''):gsub('%^%d', ''))
end

local function headers()
  return {
    ['Authorization'] = 'Bearer ' .. KEY,
    ['Content-Type'] = 'application/json',
    ['User-Agent'] = 'wwg-server-reporter/1.0.0 fivem',
  }
end

local function splitTags(s)
  local out = {}
  for tag in tostring(s):gmatch('[^,]+') do
    tag = tag:gsub('^%s+', ''):gsub('%s+$', '')
    if tag ~= '' and #out < 8 then out[#out + 1] = tag:sub(1, 24) end
  end
  return out
end

local function payload()
  local ids = GetPlayers()
  local players = {}
  if SHOW_NAMES then
    for _, id in ipairs(ids) do
      if #players >= MAX_PLAYERS then break end
      players[#players + 1] = { name = stripColours(GetPlayerName(id)):sub(1, 40) }
    end
  end
  local body = {
    external_id = EXTERNAL,
    game = GAME,
    name = stripColours(NAME):sub(1, 80),
    template = 'players',
    player_count = #ids,
    max_players = GetConvarInt('sv_maxClients', 32),
    players = players,
  }
  local desc = GetConvar('sv_projectDesc', '')
  if desc ~= '' then body.motd = stripColours(desc):sub(1, 200) end
  if JOIN_URL ~= '' then body.join_url = JOIN_URL end
  if JOIN_ADDR ~= '' then body.join_address = JOIN_ADDR end
  if REGION ~= '' then body.region = REGION end
  local tags = splitTags(TAGS)
  if #tags > 0 then body.tags = tags end
  return body
end

local function heartbeat()
  PerformHttpRequest(API_BASE .. '/heartbeat', function(status, text, _)
    if status == 200 then
      if not announced then
        local ok, data = pcall(json.decode, text or '{}')
        if ok and data and data.url then print(('[wwg-reporter] reporting as %s'):format(data.url)) end
        if ok and data and data.hidden then print('[wwg-reporter] held by the word screen (name or description); staff will look before it shows.') end
        announced = true
      end
    elseif status == 401 or status == 403 then
      print(('^1[wwg-reporter] key rejected (HTTP %s). Stopping. Check wwg_gs_key in server.cfg or create a new key.^0'):format(status))
      stopped = true
    elseif status == 429 then
      print('^3[wwg-reporter] rate limited; trying again next tick.^0')
    elseif status == 400 then
      print(('^1[wwg-reporter] rejected: %s (fix the convars)^0'):format(tostring(text)))
    elseif status == 0 then
      print('^3[wwg-reporter] WWG unreachable; trying again next tick.^0')
    else
      print(('^1[wwg-reporter] HTTP %s: %s^0'):format(tostring(status), tostring(text)))
    end
  end, 'POST', json.encode(payload()), headers())
end

CreateThread(function()
  if KEY == '' or KEY:sub(1, 7) ~= 'wwg_gs_' then
    print('^1[wwg-reporter] set wwg_gs_key in server.cfg: set wwg_gs_key "wwg_gs_..." (https://watuwagaming.site/developer#game-server-api)^0')
    return
  end
  Wait(5000)
  while not stopped do
    heartbeat()
    Wait(INTERVAL * 1000)
  end
end)

AddEventHandler('onResourceStop', function(res)
  if res ~= GetCurrentResourceName() or KEY == '' or stopped then return end
  PerformHttpRequest(API_BASE .. '/offline', function() end, 'POST', json.encode({ external_id = EXTERNAL }), headers())
end)
