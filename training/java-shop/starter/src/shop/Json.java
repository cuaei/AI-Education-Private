package shop;

import java.util.List;

/** 極簡 JSON 工具：只處理本專案固定欄位，不是通用解析器。 */
public final class Json {
    private Json() { }

    public static String escape(String value) {
        if (value == null) return "";
        StringBuilder out = new StringBuilder();
        for (char c : value.toCharArray()) {
            switch (c) {
                case '\\' -> out.append("\\\\");
                case '"' -> out.append("\\\"");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) out.append(' ');
                    else out.append(c);
                }
            }
        }
        return out.toString();
    }

    /** 從請求本文取出字串欄位；缺欄位回 null。 */
    public static String stringField(String body, String field) {
        java.util.regex.Matcher matcher = java.util.regex.Pattern
                .compile("\"" + field + "\"\\s*:\\s*\"((?:\\\\.|[^\"\\\\])*)\"").matcher(body);
        return matcher.find() ? matcher.group(1).replace("\\\"", "\"") : null;
    }

    /** 從請求本文取出整數欄位；缺欄位或非整數回 null。 */
    public static Integer intField(String body, String field) {
        java.util.regex.Matcher matcher = java.util.regex.Pattern
                .compile("\"" + field + "\"\\s*:\\s*(-?\\d+)").matcher(body);
        if (!matcher.find()) return null;
        try {
            return Integer.valueOf(matcher.group(1));
        } catch (NumberFormatException e) {
            return null;
        }
    }

    public static String product(Product product) {
        return "{\"id\":\"" + escape(product.id()) + "\",\"name\":\"" + escape(product.name())
                + "\",\"priceCents\":" + product.priceCents() + ",\"stock\":" + product.stock() + "}";
    }

    public static String order(Order order) {
        return "{\"id\":\"" + escape(order.id()) + "\",\"sequence\":" + order.sequence()
                + ",\"customerId\":\"" + escape(order.customerId()) + "\",\"productId\":\"" + escape(order.productId())
                + "\",\"quantity\":" + order.quantity() + ",\"totalCents\":" + order.totalCents()
                + ",\"status\":\"" + escape(order.status()) + "\"}";
    }

    public static String array(String field, List<String> items) {
        return "{\"" + field + "\":[" + String.join(",", items) + "]}";
    }

    public static String error(String code, String message) {
        return "{\"error\":\"" + escape(code) + "\",\"message\":\"" + escape(message) + "\"}";
    }
}
