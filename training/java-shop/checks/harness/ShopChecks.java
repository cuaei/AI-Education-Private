import com.sun.net.httpserver.HttpServer;
import shop.ShopServer;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 商店實習的可信檢查：啟動學生的 HTTP 伺服器，實際發出請求並核對回應。
 * 依參數執行 products / orders-create / orders-list 其中一項工作，輸出 JSON 陣列。
 */
public final class ShopChecks {
    private static final List<String> RESULTS = new ArrayList<>();
    private static final HttpClient CLIENT = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    private static String base;

    public static void main(String[] args) throws Exception {
        String task = args.length > 0 ? args[0] : "products";
        int port = 18080;
        base = "http://127.0.0.1:" + port;
        HttpServer server = null;
        try {
            server = ShopServer.start(port);
            if (task.equals("products")) products();
            else if (task.equals("orders-create")) createOrders();
            else listOrders();
        } catch (Throwable error) {
            RESULTS.add(check(task.toUpperCase() + "-RUN", "檢查需能完成", false, "伺服器需能啟動並回應",
                    "檢查中斷：" + error.getClass().getSimpleName() + " " + error.getMessage()));
        } finally {
            if (server != null) server.stop(0);
        }
        System.out.println("[" + String.join(",", RESULTS) + "]");
        if (args.length > 1) {
            java.nio.file.Files.writeString(java.nio.file.Path.of(args[1]), "[" + String.join(",", RESULTS) + "]",
                    java.nio.charset.StandardCharsets.UTF_8);
        }
        // 學生程式可能建立非守護執行緒；輸出完成後強制結束，避免檢查一直掛住。
        System.out.flush();
        System.exit(0);
    }

    private static void products() throws Exception {
        Response all = get("/api/products?keyword=");
        int count = occurrences(all.body, "\"priceCents\":");
        RESULTS.add(check("P-LIST", "列出全部商品與必要欄位", all.status == 200 && count == 4
                        && all.body.contains("\"p-keyboard\"") && all.body.contains("\"stock\":"),
                "200 且回 4 項種子商品", "HTTP " + all.status + "，商品數 " + count));
        Response keyword = get("/api/products?keyword=" + java.net.URLEncoder.encode("鍵盤", java.nio.charset.StandardCharsets.UTF_8));
        RESULTS.add(check("P-KEYWORD", "關鍵字篩選符合的商品", keyword.status == 200
                        && keyword.body.contains("p-keyboard") && !keyword.body.contains("p-mouse"),
                "只回符合關鍵字的商品", "HTTP " + keyword.status + "，回應 " + shorten(keyword.body)));
        Response mixedCase = get("/api/products?keyword=type-c");
        RESULTS.add(check("P-CASE", "關鍵字不分大小寫", mixedCase.status == 200 && mixedCase.body.contains("p-cable"),
                "type-c 應找到 p-cable", "HTTP " + mixedCase.status + "，回應 " + shorten(mixedCase.body)));
        Response empty = get("/api/products?keyword=no-such-product");
        RESULTS.add(check("P-EMPTY", "無符合商品回空陣列", empty.status == 200 && occurrences(empty.body, "\"priceCents\":") == 0,
                "200 且 products 為空", "HTTP " + empty.status + "，回應 " + shorten(empty.body)));
    }

    private static void createOrders() throws Exception {
        Response invalid = post("/api/orders?customerId=s01", "{\"productId\":\"p-mouse\",\"quantity\":0}");
        RESULTS.add(check("O-INVALID", "數量必須為正整數", invalid.status == 400, "400 INVALID_QUANTITY",
                "HTTP " + invalid.status + "，回應 " + shorten(invalid.body)));
        Response missing = post("/api/orders?customerId=s01", "{\"productId\":\"no-such\",\"quantity\":1}");
        RESULTS.add(check("O-NOTFOUND", "商品不存在回 404", missing.status == 404, "404 PRODUCT_NOT_FOUND",
                "HTTP " + missing.status + "，回應 " + shorten(missing.body)));
        Response soldOut = post("/api/orders?customerId=s01", "{\"productId\":\"p-mouse\",\"quantity\":99}");
        Response afterSoldOut = get("/api/products?keyword=");
        RESULTS.add(check("O-OUTOFSTOCK", "庫存不足回 409 且不扣庫存", soldOut.status == 409
                        && afterSoldOut.body.contains("\"id\":\"p-mouse\",\"name\":\"無線滑鼠\",\"priceCents\":49900,\"stock\":2"),
                "409 且 p-mouse 庫存仍為 2", "HTTP " + soldOut.status + "，之後商品回應 " + shorten(afterSoldOut.body)));
        Response created = post("/api/orders?customerId=s01", "{\"productId\":\"p-mouse\",\"quantity\":2}");
        Response afterCreate = get("/api/products?keyword=");
        RESULTS.add(check("O-CREATE", "成功建立訂單並扣庫存、算總價", created.status == 201
                        && created.body.contains("\"totalCents\":99800") && created.body.contains("\"status\":\"CREATED\"")
                        && afterCreate.body.contains("\"id\":\"p-mouse\",\"name\":\"無線滑鼠\",\"priceCents\":49900,\"stock\":0"),
                "201、總價 99800、庫存歸 0", "HTTP " + created.status + "，回應 " + shorten(created.body)
                        + "；之後庫存 " + shorten(afterCreate.body)));
        List<Response> concurrent = new ArrayList<>();
        List<Thread> threads = new ArrayList<>();
        for (int i = 0; i < 6; i++) {
            Thread thread = new Thread(() -> {
                try {
                    Response response = post("/api/orders?customerId=s02", "{\"productId\":\"p-cable\",\"quantity\":2}");
                    synchronized (concurrent) {
                        concurrent.add(response);
                    }
                } catch (Exception ignored) { }
            });
            threads.add(thread);
        }
        // 同時送出六個各買 2 件的請求，庫存 10，只能五個成功。
        for (Thread thread : threads) thread.start();
        for (Thread thread : threads) thread.join();
        long success = concurrent.stream().filter(r -> r.status == 201).count();
        Response afterConcurrent = get("/api/products?keyword=");
        RESULTS.add(check("O-CONCURRENCY", "同時下單不能超賣", success == 5 && concurrent.size() == 6
                        && afterConcurrent.body.contains("\"id\":\"p-cable\",\"name\":\"Type-C 傳輸線\",\"priceCents\":9900,\"stock\":0"),
                "六個請求僅五個成功且庫存不為負", "成功數 " + success + "，回應數 " + concurrent.size()
                        + "；之後庫存 " + shorten(afterConcurrent.body)));
    }

    private static void listOrders() throws Exception {
        post("/api/orders?customerId=s01", "{\"productId\":\"p-mouse\",\"quantity\":1}");
        Response second = post("/api/orders?customerId=s01", "{\"productId\":\"p-cable\",\"quantity\":1}");
        post("/api/orders?customerId=s02", "{\"productId\":\"p-monitor\",\"quantity\":1}");
        String ownOrderId = field(second.body, "id");
        Response own = get("/api/orders?customerId=s01");
        RESULTS.add(check("L-OWN", "只回自己的訂單", own.status == 200 && occurrences(own.body, "\"sequence\":") == 2
                        && !own.body.contains("p-monitor"), "兩筆 s01 訂單，不含他人訂單",
                "HTTP " + own.status + "，回應 " + shorten(own.body)));
        Matcher matcher = Pattern.compile("\"sequence\":(\\d+)").matcher(own.body);
        List<Integer> sequences = new ArrayList<>();
        while (matcher.find()) sequences.add(Integer.parseInt(matcher.group(1)));
        boolean descending = sequences.size() == 2 && sequences.get(0) > sequences.get(1);
        RESULTS.add(check("L-ORDER", "訂單由新到舊", descending, "第一筆 sequence 大於第二筆", "實際順序 " + sequences));
        Response detail = get("/api/orders/" + ownOrderId + "?customerId=s01");
        RESULTS.add(check("L-DETAIL", "可查看自己的訂單明細", detail.status == 200 && detail.body.contains(ownOrderId),
                "200 且包含訂單編號", "HTTP " + detail.status + "，回應 " + shorten(detail.body)));
        Response other = get("/api/orders/" + ownOrderId + "?customerId=s02");
        Response unknown = get("/api/orders/o-not-exist?customerId=s01");
        RESULTS.add(check("L-FORBIDDEN", "他人或不存在的訂單回 404", other.status == 404 && unknown.status == 404,
                "他人訂單與未知訂單都回 404", "他人 HTTP " + other.status + "，未知 HTTP " + unknown.status));
    }

    private record Response(int status, String body) { }

    private static Response get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(URI.create(base + path)).timeout(Duration.ofSeconds(8)).GET().build();
        HttpResponse<String> response = CLIENT.send(request, HttpResponse.BodyHandlers.ofString());
        return new Response(response.statusCode(), response.body());
    }

    private static Response post(String path, String body) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(URI.create(base + path)).timeout(Duration.ofSeconds(8))
                .header("Content-Type", "application/json").POST(HttpRequest.BodyPublishers.ofString(body)).build();
        HttpResponse<String> response = CLIENT.send(request, HttpResponse.BodyHandlers.ofString());
        return new Response(response.statusCode(), response.body());
    }

    private static String check(String key, String label, boolean passed, String expected, String actual) {
        return "{\"key\":\"" + key + "\",\"label\":\"" + Json.escape(label) + "\",\"dimension\":\"task\",\"weight\":1,"
                + "\"passed\":" + passed + ",\"expected\":\"" + Json.escape(expected) + "\",\"actual\":\"" + Json.escape(actual) + "\"}";
    }

    private static int occurrences(String text, String token) {
        return text == null ? 0 : text.split(Pattern.quote(token), -1).length - 1;
    }

    private static String field(String body, String name) {
        Matcher matcher = Pattern.compile("\"" + name + "\":\"([^\"]+)\"").matcher(body == null ? "" : body);
        return matcher.find() ? matcher.group(1) : "";
    }

    private static String shorten(String body) {
        if (body == null) return "";
        return body.length() > 240 ? body.substring(0, 240) + "…" : body;
    }
}
