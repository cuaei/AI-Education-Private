package shop;

/** 商店商品。價格以「分」保存，避免浮點誤差。 */
public final class Product {
    private final String id;
    private final String name;
    private final int priceCents;
    private int stock;

    public Product(String id, String name, int priceCents, int stock) {
        this.id = id;
        this.name = name;
        this.priceCents = priceCents;
        this.stock = stock;
    }

    public String id() { return id; }
    public String name() { return name; }
    public int priceCents() { return priceCents; }
    public int stock() { return stock; }
    public void decreaseStock(int quantity) { this.stock -= quantity; }
}
