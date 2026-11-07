package shop;

/** 訂單。sequence 代表建立先後，列表需依此由新到舊排序。 */
public final class Order {
    private final String id;
    private final long sequence;
    private final String customerId;
    private final String productId;
    private final int quantity;
    private final int totalCents;
    private final String status;

    public Order(String id, long sequence, String customerId, String productId, int quantity, int totalCents) {
        this.id = id;
        this.sequence = sequence;
        this.customerId = customerId;
        this.productId = productId;
        this.quantity = quantity;
        this.totalCents = totalCents;
        this.status = "CREATED";
    }

    public String id() { return id; }
    public long sequence() { return sequence; }
    public String customerId() { return customerId; }
    public String productId() { return productId; }
    public int quantity() { return quantity; }
    public int totalCents() { return totalCents; }
    public String status() { return status; }
}
