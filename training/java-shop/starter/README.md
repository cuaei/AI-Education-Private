# 模擬實習：網上商店 Java 後端

歡迎來到模擬公司。你接手一個**已有部分程式**的網上商店，以 Java 後端工程師身份依序完成三項工作：
**查詢商品 → 建立訂單 → 查看訂單**。這是網站內的模擬實習，不是真實公司的職缺或實習安排。

HTTP 伺服器、路由與操作頁面都已提供，你**不需要寫前端**，只要完成 `src/shop/ShopService.java`。
整個專案只用 JDK 17 內建功能，沒有 Maven、Gradle 或外部套件。

## 在本機跑起來

```powershell
javac -encoding UTF-8 -d out (Get-ChildItem -Recurse -Filter *.java src | ForEach-Object FullName)
java -cp out shop.ShopServer
```

然後用瀏覽器開啟 http://127.0.0.1:8080 。
macOS / Linux：

```bash
javac -encoding UTF-8 -d out $(find src -name '*.java')
java -cp out shop.ShopServer
```

尚未完成的功能會回 HTTP 501；完成後重新編譯並重啟即可看到實際效果。
商品與訂單是模擬資料，每次重啟都會還原，可以放心測試。

## 工作一：查詢商品 `GET /api/products?keyword=`

- 回 `200`，格式 `{"products":[{"id","name","priceCents","stock"}]}`。
- `keyword` 留空回全部商品；有值時回名稱包含關鍵字的商品，**不分大小寫**。
- 沒有符合的商品時回空陣列，不要回錯誤。

## 工作二：建立訂單 `POST /api/orders?customerId=s01`

請求本文：`{"productId":"p-mouse","quantity":2}`。

| 情況 | 回應 |
| --- | --- |
| 成功 | `201`，`{"order":{...}}`，總價＝單價×數量，庫存減少相同數量 |
| 數量不是正整數 | `400`，`INVALID_QUANTITY` |
| 商品不存在 | `404`，`PRODUCT_NOT_FOUND` |
| 庫存不足 | `409`，`OUT_OF_STOCK`，庫存不可被扣成負數 |

「檢查庫存 → 扣庫存 → 建立訂單」必須在 `repository.orderLock()` 的同步區塊內完成，
否則多人同時下單會超賣。同一顧客連續下兩張單是兩筆獨立訂單，不需要做冪等合併。

## 工作三：查看訂單

- `GET /api/orders?customerId=s01`：只回這位顧客的訂單，**由新到舊**（依 `sequence` 遞減）。
- `GET /api/orders/{orderId}?customerId=s01`：只回自己的訂單；不存在或屬於別人時回 `404`、`ORDER_NOT_FOUND`。

## 檢查與次數

- 三項工作各自最多 **3 次有效檢查**，前一項通過才會開放下一項；每次上傳沿用整個專案，進度會接續。
- 只有真正跑完的檢查才計次；平台環境故障或檢查超時**不扣次**。
- 三次未通過會暫停該項檢查，請先複習，再請教師或管理員重設；重設保留歷史紀錄。
- 檢查結果由程式實際發出 HTTP 請求得來，AI 只能解釋結果，不能替你判定通過。

## 上傳格式

把 `src`、`web`、`README.md` 壓成 ZIP 上傳（可多一層資料夾）。
不要包含 `out`、`.git`、IDE 設定或環境設定檔；原始碼使用 UTF-8。
