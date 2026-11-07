# 綜合實作：比賽報名系統（Java 後端）

這是平台「綜合實作」的正式起始項目，屬於**網站內的模擬實作**，不是真實公司的專案。
題目場景由開發者本次選定為「比賽報名」，與之後的網上商店實習是不同場景。
你需要在自己電腦完成剩餘功能、寫自己的測試，然後把整個專案壓縮成 ZIP 上傳檢查。

## 環境

- JDK 17 或以上（只需要 JDK，不需要 Maven、Gradle 或任何外部套件）。
- 終端機切換到本專案目錄後執行：

```powershell
javac -encoding UTF-8 -d out (Get-ChildItem -Recurse -Filter *.java src,test | ForEach-Object FullName)
java -cp out competition.Main
java -cp out competition.RegistrationServiceTest
```

macOS / Linux：

```bash
javac -encoding UTF-8 -d out $(find src test -name '*.java')
java -cp out competition.Main
java -cp out competition.RegistrationServiceTest
```

## 你要交付什麼

1. 完成 `src/competition/RegistrationService.java` 的 `register`、`cancel`、`remainingSeats`。
2. 在 `test/competition/RegistrationServiceTest.java` 寫自己的測試，覆蓋下方規則。
3. 上傳時填寫「設計解釋」（200–2000 字）：說明你怎麼處理重複報名、名額與截止時間，以及目前的限制。
4. 不要修改 `Competition`、`Registration`、`CompetitionRepository`、`RegistrationException` 的對外介面；
   平台會用課程內建版本配合你的 Service 與測試執行。

## 固定業務規則

1. 姓名為 null、空白或全形／半形空格時，拋出 `RegistrationException`，原因 `INVALID_NAME`。
2. 比賽不存在時，原因 `UNKNOWN_COMPETITION`。
3. 同一學生對同一比賽已有有效報名時，**原樣回傳原本那一筆**，不新增、不再占名額。
4. 目前時間**晚於**截止時間時，報名與取消都回 `CLOSED`；恰好等於截止時間仍可操作。
5. 有效報名數達到容量時，新學生報名回 `FULL`。
6. `remainingSeats` ＝ 容量減有效報名數，永遠不為負數。
7. 取消只影響**該學生自己**的有效報名；沒有有效報名時回 `NOT_FOUND`。
8. 取消後釋放一個名額，可以再次報名；已取消的紀錄保留，但不出現在 `listActive`。
9. 多人同時搶最後名額時只能一人成功：「檢查名額＋建立」必須在
   `repository.competitionLock(competitionId)` 的同步區塊內完成。
10. 時間一律使用建構子注入的 `Clock`，不要直接使用系統時間，否則測試無法重現。

## 評分與通過（滿分 100，至少 70）

| 部分 | 分數 | 由誰評定 |
| --- | --- | --- |
| 核心功能（9 項業務檢查） | 45 | 程式實際執行 |
| 你自己的測試（正確版誤報＋三個內建故障） | 20 | 程式實際執行 |
| 程式結構（時間注入、方法長度、錯誤處理、狀態保存方式） | 20 | 程式靜態檢查 |
| 設計解釋 | 15 | 你主動請 AI 評分，或由教師人工評分；未評時顯示待評 |

**必要條件**：核心功能 9 項全過，且你的測試對正確版全過、對三個故障版都能抓出問題。
兩項必要條件任一未達成，即使總分超過 70 也不算通過。
設計解釋未評分時仍可通過，但會標示「設計解釋待評」。

## 檢查次數

- 綜合實作最多 **3 次有效檢查**。上傳本身不扣次，只有真正跑完檢查才計次。
- 平台環境故障、Docker 不可用或檢查超時屬於未完成檢查，**不扣次**，可稍後重試。
- 三次仍未通過會暫停檢查，請先複習，再請教師或管理員重設次數；重設不會刪除你的歷史紀錄。

## 上傳格式

- 把 `src`、`test`、`README.md` 一起壓成 ZIP（可以多一層資料夾）。
- 不要包含 `out`、`.git`、IDE 設定或任何環境設定檔。
- 原始碼必須是 UTF-8，ZIP 不可加密。
