package site.watuwagaming.reporter;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import net.fabricmc.api.DedicatedServerModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.server.world.ServerWorld;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Server-side Fabric mod that reports this server to watuwagaming.site.
 *
 * Every N ticks (30 seconds by default) the heartbeat body is snapshotted on
 * the server thread, then posted from a single background thread so the
 * network never touches the tick. SERVER_STOPPING posts /offline.
 */
public final class WwgReporterMod implements DedicatedServerModInitializer {

    static final Logger LOG = LoggerFactory.getLogger("wwg-reporter");
    private static final int MAX_PLAYERS = 100;

    private ReporterConfig cfg;
    private WwgClient client;
    private final ExecutorService io = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "wwg-reporter");
        t.setDaemon(true);
        return t;
    });
    private int ticks;
    private volatile boolean stopped;
    private volatile boolean announced;

    @Override
    public void onInitializeServer() {
        cfg = ReporterConfig.load(FabricLoader.getInstance().getConfigDir().resolve("wwg-reporter.json"));
        if (!cfg.keyLooksValid()) {
            LOG.error("Set \"key\" in config/wwg-reporter.json (create one at "
                    + "https://watuwagaming.site/profile#game-server-api). Reporter disabled.");
            return;
        }
        client = new WwgClient(cfg.api_base, cfg.key, LOG);
        int period = Math.max(15, cfg.interval_seconds) * 20;

        ServerTickEvents.END_SERVER_TICK.register(server -> {
            if (stopped || ++ticks < period) {
                return;
            }
            ticks = 0;
            JsonObject body = snapshot(server);   // server thread: safe to read state
            io.submit(() -> send(body));          // network off the server thread
        });
        ServerLifecycleEvents.SERVER_STOPPING.register(server -> {
            if (!stopped) {
                client.offline(cfg.external_id);
            }
            io.shutdownNow();
        });
        LOG.info("Reporting to WWG every {}s as '{}'.", period / 20, cfg.external_id);
    }

    private void send(JsonObject body) {
        WwgClient.Result r = client.post("/heartbeat", body);
        switch (r.status()) {
            case 200 -> {
                if (!announced) {
                    LOG.info("Reporting as {}", r.string("url"));
                    announced = true;
                }
                if (r.bool("hidden")) {
                    LOG.warn("Held by the word screen (name or MOTD); staff will look before it shows.");
                }
            }
            case 401, 403 -> {
                LOG.error("WWG rejected the key ({}). Stopping. Create a new key at "
                        + "https://watuwagaming.site/profile#game-server-api", r.string("code"));
                stopped = true;
            }
            case 429 -> LOG.warn("Rate limited by WWG; trying again next tick.");
            case 400 -> LOG.error("WWG rejected the heartbeat: {} (fix config/wwg-reporter.json)", r.string("error"));
            case 409 -> LOG.error("{} Remove a server on your profile to free a slot.", r.string("error"));
            case 0 -> { /* unreachable, already logged by the client */ }
            default -> LOG.warn("WWG answered HTTP {}: {}", r.status(), r.string("error"));
        }
    }

    /** Server thread only. */
    private JsonObject snapshot(MinecraftServer server) {
        JsonObject b = new JsonObject();
        b.addProperty("external_id", cfg.external_id);
        b.addProperty("game", cfg.game);
        b.addProperty("name", cfg.name);
        b.addProperty("template", cfg.template);
        putIfSet(b, "join_address", cfg.join_address);
        putIfSet(b, "join_url", cfg.join_url);
        putIfSet(b, "region", cfg.region);
        putIfSet(b, "icon_url", cfg.icon_url);
        String motd = server.getServerMotd();
        if (motd != null) {
            putIfSet(b, "motd", motd.replaceAll("(?i)§[0-9a-fk-orx]", "").trim());
        }
        String mode = cfg.mode == null || cfg.mode.isBlank()
                ? capitalise(server.getDefaultGameMode().getName())
                : cfg.mode;
        b.addProperty("mode", mode);
        b.addProperty("version", server.getVersion());
        b.addProperty("max_players", server.getMaxPlayerCount());

        List<ServerPlayerEntity> online = server.getPlayerManager().getPlayerList();
        b.addProperty("player_count", online.size());
        JsonArray players = new JsonArray();
        if (cfg.show_player_names) {
            int n = 0;
            for (ServerPlayerEntity p : online) {
                if (n++ >= MAX_PLAYERS) {
                    break;
                }
                JsonObject o = new JsonObject();
                o.addProperty("name", p.getGameProfile().getName());
                o.addProperty("uuid", p.getUuidAsString());
                players.add(o);
            }
        }
        b.add("players", players);

        if (cfg.tags != null && cfg.tags.length > 0) {
            JsonArray a = new JsonArray();
            for (int i = 0; i < Math.min(8, cfg.tags.length); i++) {
                a.add(cfg.tags[i]);
            }
            b.add("tags", a);
        }
        if (cfg.links != null && cfg.links.length > 0) {
            JsonArray a = new JsonArray();
            for (ReporterConfig.Link l : cfg.links) {
                if (a.size() >= 4 || l == null || l.label == null || l.url == null) {
                    continue;
                }
                JsonObject o = new JsonObject();
                o.addProperty("label", l.label);
                o.addProperty("url", l.url);
                a.add(o);
            }
            b.add("links", a);
        }

        ServerWorld w = server.getOverworld();
        if (w != null) {
            JsonObject world = new JsonObject();
            world.addProperty("day", w.getTime() / 24000L);
            world.addProperty("time_of_day", clock(w.getTimeOfDay()));
            world.addProperty("weather", w.isThundering() ? "Thunder" : w.isRaining() ? "Rain" : "Clear");
            world.addProperty("difficulty", capitalise(w.getDifficulty().getName()));
            JsonObject state = new JsonObject();
            state.add("world", world);
            b.add("state", state);
        }
        return b;
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
