package competition;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

/**
 * 你自己的測試。不使用任何外部套件：用 main 方法搭配自訂 check 即可。
 * 平台會做三件事：
 * 1. 對「正確實作」執行你的測試，必須全部通過，不能誤報。
 * 2. 對三個「內建故障實作」執行你的測試，每個都必須被你的測試抓出來。
 * 3. 只讀取程式的實際執行結果，不看輸出文字，所以沒有斷言的測試不算數。
 * 建議至少涵蓋：重複報名不占名額、額滿拒絕、只能取消自己的報名。
 */
public final class RegistrationServiceTest {
    private static int checks = 0;

    private static void check(boolean condition, String message) {
        checks++;
        if (!condition) throw new AssertionError(message);
    }

    private static RegistrationService serviceAt(String isoInstant, int capacity) {
        CompetitionRepository repository = new CompetitionRepository();
        repository.addCompetition(new Competition("java-cup", "Java 程式設計賽", capacity,
                LocalDateTime.of(2099, 10, 1, 18, 0)));
        Clock clock = Clock.fixed(Instant.parse(isoInstant), ZoneId.of("UTC"));
        return new RegistrationService(repository, clock);
    }

    public static void main(String[] args) {
        RegistrationService service = serviceAt("2099-09-01T00:00:00Z", 2);
        // 範例斷言：正常報名後剩餘名額減一。請換成你自己的完整案例。
        service.register("java-cup", "s01", "陳同學");
        check(service.remainingSeats("java-cup") == 1, "報名一人後應剩一個名額");

        // TODO：補上重複報名、額滿、取消他人報名等案例。
        System.out.println("學生測試完成，斷言數：" + checks);
    }
}
