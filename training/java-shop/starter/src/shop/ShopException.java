package shop;

/** 業務錯誤：status 會成為 HTTP 狀態碼，code 為穩定的錯誤代號。 */
public class ShopException extends RuntimeException {
    private final int status;
    private final String code;

    public ShopException(int status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }

    public int status() { return status; }
    public String code() { return code; }
}
