package shop;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;

/**
 * 課程提供的 HTTP 層與靜態頁面。學生只需完成 ShopService，不必修改這個類別。
 * 使用 JDK 內建 HttpServer，沒有任何外部相依套件。
 */
public final class ShopServer {
    private ShopServer() { }

    public static HttpServer start(int port) throws IOException {
        ShopService service = new ShopService(new ShopRepository());
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 0);
        server.setExecutor(Executors.newFixedThreadPool(8));
        server.createContext("/api/products", exchange -> handle(exchange, () -> {
            if (!"GET".equals(exchange.getRequestMethod())) return response(405, Json.error("METHOD", "只接受 GET"));
            String keyword = query(exchange).get("keyword");
            List<String> items = service.listProducts(keyword).stream().map(Json::product).toList();
            return response(200, Json.array("products", items));
        }));
        server.createContext("/api/orders", exchange -> handle(exchange, () -> {
            Map<String, String> query = query(exchange);
            String customerId = query.getOrDefault("customerId", "guest");
            if ("GET".equals(exchange.getRequestMethod())) {
                List<String> items = service.listOrders(customerId).stream().map(Json::order).toList();
                return response(200, Json.array("orders", items));
            }
            if ("POST".equals(exchange.getRequestMethod())) {
                String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
                String productId = Json.stringField(body, "productId");
                Integer quantity = Json.intField(body, "quantity");
                if (productId == null || quantity == null) return response(400, Json.error("INVALID_BODY", "需要 productId 與整數 quantity"));
                Order order = service.createOrder(customerId, productId, quantity);
                return response(201, "{\"order\":" + Json.order(order) + "}");
            }
            return response(405, Json.error("METHOD", "只接受 GET 或 POST"));
        }));
        server.createContext("/api/orders/", exchange -> handle(exchange, () -> {
            if (!"GET".equals(exchange.getRequestMethod())) return response(405, Json.error("METHOD", "只接受 GET"));
            String orderId = exchange.getRequestURI().getPath().substring("/api/orders/".length());
            String customerId = query(exchange).getOrDefault("customerId", "guest");
            return response(200, "{\"order\":" + Json.order(service.findOrder(customerId, orderId)) + "}");
        }));
        server.createContext("/", exchange -> {
            String path = exchange.getRequestURI().getPath();
            if (path.equals("/")) path = "/index.html";
            Path file = Path.of("web").resolve(path.substring(1)).normalize();
            if (!file.startsWith(Path.of("web")) || !Files.isRegularFile(file)) {
                exchange.sendResponseHeaders(404, -1);
                exchange.close();
                return;
            }
            byte[] bytes = Files.readAllBytes(file);
            exchange.getResponseHeaders().set("Content-Type", path.endsWith(".html") ? "text/html; charset=utf-8" : "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        });
        server.start();
        return server;
    }

    public static void main(String[] args) throws IOException {
        start(8080);
        System.out.println("模擬商店已啟動：http://127.0.0.1:8080 （商品與訂單皆為模擬資料）");
    }

    private record Response(int status, String body) { }

    private static Response response(int status, String body) {
        return new Response(status, body);
    }

    private interface Handler { Response run() throws Exception; }

    private static void handle(HttpExchange exchange, Handler handler) throws IOException {
        Response result;
        try {
            result = handler.run();
        } catch (ShopException e) {
            result = response(e.status(), Json.error(e.code(), e.getMessage()));
        } catch (UnsupportedOperationException e) {
            result = response(501, Json.error("NOT_IMPLEMENTED", String.valueOf(e.getMessage())));
        } catch (Exception e) {
            result = response(500, Json.error("INTERNAL", e.getClass().getSimpleName()));
        }
        byte[] bytes = result.body().getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.sendResponseHeaders(result.status(), bytes.length);
        exchange.getResponseBody().write(bytes);
        exchange.close();
    }

    private static Map<String, String> query(HttpExchange exchange) {
        Map<String, String> values = new HashMap<>();
        String raw = exchange.getRequestURI().getRawQuery();
        if (raw == null) return values;
        for (String pair : raw.split("&")) {
            String[] parts = pair.split("=", 2);
            values.put(URLDecoder.decode(parts[0], StandardCharsets.UTF_8),
                    parts.length > 1 ? URLDecoder.decode(parts[1], StandardCharsets.UTF_8) : "");
        }
        return values;
    }
}
