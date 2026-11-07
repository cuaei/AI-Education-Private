package shop;

import java.util.List;

/**
 * 商店後端的三項工作，由你完成：
 * 1. listProducts：查詢商品（含關鍵字篩選）。
 * 2. createOrder：建立訂單（檢查商品、數量與庫存，扣庫存並計算總價）。
 * 3. listOrders / findOrder：查看自己的訂單。
 * HTTP 路由與頁面已提供，不需要修改；規則細節見 README.md。
 */
public final class ShopService {
    private final ShopRepository repository;

    public ShopService(ShopRepository repository) {
        this.repository = repository;
    }

    /** 關鍵字為空白或 null 時回全部商品；否則回名稱包含關鍵字的商品（不分大小寫）。 */
    public List<Product> listProducts(String keyword) {
        throw new UnsupportedOperationException("TODO：完成商品查詢");
    }

    /**
     * 建立訂單。錯誤請拋出 ShopException：
     * 數量不是正整數 → 400 / INVALID_QUANTITY；商品不存在 → 404 / PRODUCT_NOT_FOUND；
     * 庫存不足 → 409 / OUT_OF_STOCK。成功時扣庫存並回傳訂單。
     */
    public Order createOrder(String customerId, String productId, int quantity) {
        throw new UnsupportedOperationException("TODO：完成建立訂單");
    }

    /** 只回這位顧客的訂單，依建立順序由新到舊。 */
    public List<Order> listOrders(String customerId) {
        throw new UnsupportedOperationException("TODO：完成訂單列表");
    }

    /** 只回這位顧客自己的訂單；不存在或屬於別人 → 404 / ORDER_NOT_FOUND。 */
    public Order findOrder(String customerId, String orderId) {
        throw new UnsupportedOperationException("TODO：完成訂單明細");
    }
}
