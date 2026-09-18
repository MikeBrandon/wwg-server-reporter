package site.watuwagaming.reporter;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;

import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

/**
 * Reports this server to watuwagaming.site every 30 seconds.
 *
 * The network call runs on an async task; the server state is read on the
 * main thread through callSyncMethod, so nothing here touches Bukkit from
 * the wrong thread. A failed heartbeat is logged and retried next tick; a
 * rejected key (401/403) stops the task and says so once.
 */
public final class WwgReporterPlugin extends JavaPlugin {

    private static final Pattern LEGACY_COLOURS = Pattern.compile("(?i)§[0-9a-fk-orx]");
    private static final int MAX_PLAYERS = 100;

    private WwgClient client;
    private BukkitTask task;
    private volatile boolean stopped;
    private boolean announced;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        FileConfiguration c = getConfig();
        String key = c.getString("key", "").trim();
        if (!key.startsWith("wwg_gs_") || key.length() < 47) {
            getLogger().severe("Set 'key' in plugins/WwgReporter/config.yml. Create one at "
                    + "https://watuwagaming.site/profile#game-server-api. Reporter disabled.");
            return;
        }
        client = new WwgClient(c.getString("api_base", WwgClient.DEFAULT_BASE), key, getLogger());
        long periodTicks = Math.max(15, c.getInt("interval_seconds", 30)) * 20L;
        task = Bukkit.getScheduler().runTaskTimerAsynchronously(this, this::tick, 100L, periodTicks);
        getLogger().info("Reporting to WWG every " + (periodTicks / 20) + "s as '"
                + c.getString("external_id", "smp-1") + "'.");
    }

    @Override
    public void onDisable() {
        if (task != null) {
            task.cancel();
        }
        if (client != null && !stopped) {
            client.offline(getConfig().getString("external_id", "smp-1"));
        }
    }

    /** Async task. */
    private void tick() {
        if (stopped) {
            return;
        }
        JsonObject body;
        try {
            body = Bukkit.getScheduler().callSyncMethod(this, this::snapshot).get(5, TimeUnit.SECONDS);
        } catch (Exception e) {
            getLogger().warning("Could not snapshot server state: " + e.getMessage());
            return;
        }
        WwgClient.Result r = client.post("/heartbeat", body);
        switch (r.status()) {
            case 200 -> {
                if (!announced) {
                    getLogger().info("Reporting as " + r.string("url"));
                    announced = true;
                }
                if (r.bool("hidden")) {
                    getLogger().warning("Held by the word screen (name or MOTD); staff will look before it shows.");
                }
            }
            case 401, 403 -> {
                getLogger().severe("WWG rejected the key (" + r.string("code") + "). Stopping. Create a new key at "
                        + "https://watuwagaming.site/profile#game-server-api");
                stopped = true;
                if (task != null) {
                    task.cancel();
                }
            }
            case 429 -> getLogger().warning("Rate limited by WWG; trying again next tick.");
            case 400 -> getLogger().severe("WWG rejected the heartbeat: " + r.string("error") + " (fix config.yml)");
            case 409 -> getLogger().severe(r.string("error") + " Remove a server on your profile to free a slot.");
            case 0 -> { /* unreachable, already logged by the client */ }
            default -> getLogger().warning("WWG answered HTTP " + r.status() + ": " + r.string("error"));
        }
    }

    /** Main thread only: reads Bukkit state into the heartbeat body. */
    private JsonObject snapshot() {
        FileConfiguration c = getConfig();
        JsonObject b = new JsonObject();
        b.addProperty("external_id", c.getString("external_id", "smp-1"));
        b.addProperty("game", c.getString("game", "minecraft"));
        b.addProperty("name", c.getString("name", "Minecraft server"));
        b.addProperty("template", c.getString("template", "world"));
        putIfSet(b, "join_address", c.getString("join_address"));
        putIfSet(b, "join_url", c.getString("join_url"));
        putIfSet(b, "region", c.getString("region"));
        putIfSet(b, "icon_url", c.getString("icon_url"));
        putIfSet(b, "motd", LEGACY_COLOURS.matcher(legacyMotd()).replaceAll("").trim());

        String mode = c.getString("mode", "");
        if (mode == null || mode.isBlank()) {
            mode = capitalise(Bukkit.getDefaultGameMode().name());
        }
        b.addProperty("mode", mode);
        b.addProperty("version", Bukkit.getMinecraftVersion());
        b.addProperty("max_players", Bukkit.getMaxPlayers());

        Collection<? extends Player> online = Bukkit.getOnlinePlayers();
        b.addProperty("player_count", online.size());
        JsonArray players = new JsonArray();
        if (c.getBoolean("show_player_names", true)) {
            int n = 0;
            for (Player p : online) {
                if (n++ >= MAX_PLAYERS) {
                    break;
                }
                JsonObject o = new JsonObject();
                o.addProperty("name", p.getName());
                o.addProperty("uuid", p.getUniqueId().toString());
                players.add(o);
            }
        }
        b.add("players", players);

        List<String> tags = c.getStringList("tags");
        if (!tags.isEmpty()) {
            JsonArray a = new JsonArray();
            tags.stream().limit(8).forEach(a::add);
            b.add("tags", a);
        }
        List<Map<?, ?>> links = c.getMapList("links");
        if (!links.isEmpty()) {
            JsonArray a = new JsonArray();
            for (Map<?, ?> l : links) {
                Object label = l.get("label");
                Object url = l.get("url");
                if (a.size() >= 4 || label == null || url == null) {
                    continue;
                }
                JsonObject o = new JsonObject();
                o.addProperty("label", String.valueOf(label));
                o.addProperty("url", String.valueOf(url));
                a.add(o);
            }
            b.add("links", a);
        }

        List<World> worlds = Bukkit.getWorlds();
        if (!worlds.isEmpty()) {
            World w = worlds.get(0);
            JsonObject world = new JsonObject();
            world.addProperty("day", w.getFullTime() / 24000L);
            world.addProperty("time_of_day", clock(w.getTime()));
            world.addProperty("weather", w.isThundering() ? "Thunder" : w.hasStorm() ? "Rain" : "Clear");
            world.addProperty("difficulty", capitalise(w.getDifficulty().name()));
            JsonObject state = new JsonObject();
            state.add("world", world);
            b.add("state", state);
        }
        return b;
    }

    @SuppressWarnings("deprecation")
    private static String legacyMotd() {
        String motd = Bukkit.getMotd();
        return motd == null ? "" : motd;
    }

    private static void putIfSet(JsonObject o, String key, String value) {
        if (value != null && !value.isBlank()) {
            o.addProperty(key, value.trim());
        }
    }

    private static String capitalise(String s) {
        s = s.toLowerCase().replace('_', ' ');
        return s.isEmpty() ? s : Character.toUpperCase(s.charAt(0)) + s.substring(1);
    }

    /** Minecraft day ticks to a clock: 0 is 06:00, 6000 is noon, 18000 is midnight. */
    static String clock(long ticks) {
        long t = ((ticks % 24000) + 24000) % 24000;
        long hours = (t / 1000 + 6) % 24;
        long minutes = (t % 1000) * 60 / 1000;
        return String.format("%02d:%02d", hours, minutes);
    }
}
