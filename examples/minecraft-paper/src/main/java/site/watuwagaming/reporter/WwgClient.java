package site.watuwagaming.reporter;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.logging.Logger;

/**
 * The WWG Game Server Presence API client: POST /heartbeat and POST /offline.
 * Status 0 means WWG was unreachable; the client already logged it.
 */
final class WwgClient {

    static final String DEFAULT_BASE = "https://watuwagaming.site/api/gs/v1";
    private static final String USER_AGENT = "wwg-server-reporter/1.0.0 paper";

    record Result(int status, JsonObject data) {
        String string(String key) {
            JsonElement e = data.get(key);
            return e == null || e.isJsonNull() ? "" : e.getAsString();
        }

        boolean bool(String key) {
            JsonElement e = data.get(key);
            return e != null && e.isJsonPrimitive() && e.getAsJsonPrimitive().isBoolean() && e.getAsBoolean();
        }
    }

    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    private final String base;
    private final String key;
    private final Logger log;

    WwgClient(String base, String key, Logger log) {
        this.base = base.replaceAll("/+$", "");
        this.key = key;
        this.log = log;
    }

    Result post(String path, JsonObject body) {
        HttpRequest req = HttpRequest.newBuilder(URI.create(base + path))
                .timeout(Duration.ofSeconds(10))
                .header("Authorization", "Bearer " + key)
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .header("User-Agent", USER_AGENT)
                .POST(HttpRequest.BodyPublishers.ofString(body.toString()))
                .build();
        try {
            HttpResponse<String> res = http.send(req, HttpResponse.BodyHandlers.ofString());
            return new Result(res.statusCode(), parse(res.body()));
        } catch (IOException e) {
            log.warning("WWG unreachable: " + e.getMessage() + " (trying again next tick)");
            return new Result(0, new JsonObject());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return new Result(0, new JsonObject());
        }
    }

    void offline(String externalId) {
        JsonObject b = new JsonObject();
        b.addProperty("external_id", externalId);
        post("/offline", b);
    }

    private static JsonObject parse(String body) {
        try {
            JsonElement e = JsonParser.parseString(body);
            return e.isJsonObject() ? e.getAsJsonObject() : new JsonObject();
        } catch (RuntimeException ignored) {
            JsonObject o = new JsonObject();
            o.addProperty("error", body == null ? "" : body.substring(0, Math.min(200, body.length())));
            return o;
        }
    }
}
