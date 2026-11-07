package shop;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/**
 * 課程提供的商店資料。商品與訂單都是模擬資料，重新啟動就會還原。
 * 查詢與寫入各自執行緒安全，但「檢查庫存＋扣庫存＋建立訂單」必須在 orderLock() 內同步完成。
 */
public final class ShopRepository {
    private final Map<String, Product> products = new LinkedHashMap<>();
    private final List<Order> orders = new ArrayList<>();
    private final Object orderLock = new Object();

    public ShopRepository() {
        products.put("p-keyboard", new Product("p-keyboard", "機械鍵盤", 129900, 5));
        products.put("p-mouse", new Product("p-mouse", "無線滑鼠", 49900, 2));
        products.put("p-monitor", new Product("p-monitor", "27 吋螢幕", 399900, 3));
        products.put("p-cable", new Product("p-cable", "Type-C 傳輸線", 9900, 10));
    }

    public synchronized List<Product> allProducts() {
        return new ArrayList<>(products.values());
    }

    public synchronized Optional<Product> findProduct(String id) {
        return Optional.ofNullable(products.get(id));
    }

    public Object orderLock() { return orderLock; }

    public synchronized Order createOrder(String customerId, Product product, int quantity) {
        Order order = new Order("o-" + UUID.randomUUID(), orders.size() + 1L, customerId, product.id(), quantity,
                product.priceCents() * quantity);
        orders.add(order);
        return order;
    }

    public synchronized List<Order> allOrders() {
        return new ArrayList<>(orders);
    }

    public synchronized Optional<Order> findOrder(String id) {
        return orders.stream().filter(o -> o.id().equals(id)).findFirst();
    }
}
