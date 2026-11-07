/** JSON 字串跳脫，避免學生原始碼中的引號破壞檢查結果格式。 */
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
                    // 非 ASCII 以 Unicode 跳脫輸出，避免容器或管道字元編碼差異破壞 JSON。
                    if (c < 0x20) out.append(' ');
                    else if (c > 0x7e) out.append(String.format("\\u%04x", (int) c));
                    else out.append(c);
                }
            }
        }
        return out.toString();
    }
}
