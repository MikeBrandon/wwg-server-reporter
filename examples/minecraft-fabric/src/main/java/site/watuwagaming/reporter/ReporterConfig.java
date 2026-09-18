package site.watuwagaming.reporter;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

/** config/wwg-reporter.json. Written with defaults on first start. */
public final class ReporterConfig {

    public String key = "";
    public String api_base = "https://watuwagaming.site/api/gs/v1";
    public String external_id = "smp-1";
    public String game = "minecraft";
    public String name = "My WWG server";
    public String template = "world";
    public String join_address = "play.example.co.ke:25565";
    public String join_url = "";
    public String region = "";
    public String mode = "";
    public String icon_url = "";
    public String[] tags = {"survival"};
    public Link[] links = {};
    public int interval_seconds = 30;
    public boolean show_player_names = true;

    public static final class Link {
        public String label;
        public String url;
    }

    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

    static ReporterConfig load(Path path) {
        try {
            if (Files.exists(path)) {
                ReporterConfig c = GSON.fromJson(Files.readString(path), ReporterConfig.class);
                return c == null ? new ReporterConfig() : c;
            }
            ReporterConfig def = new ReporterConfig();
            Files.createDirectories(path.getParent());
            Files.writeString(path, GSON.toJson(def));
            WwgReporterMod.LOG.info("Wrote {}. Add your key and restart.", path);
            return def;
        } catch (IOException | RuntimeException e) {
            WwgReporterMod.LOG.error("Could not read {}: {}", path, e.getMessage());
            return new ReporterConfig();
        }
    }

    boolean keyLooksValid() {
        return key != null && key.startsWith("wwg_gs_") && key.length() >= 47;
    }
}
