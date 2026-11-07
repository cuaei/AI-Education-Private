package competition;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

/** 本機示範：編譯後執行可看到目前尚待完成的提示。 */
public final class Main {
    public static void main(String[] args) {
        CompetitionRepository repository = new CompetitionRepository();
        repository.addCompetition(new Competition("java-cup", "Java 程式設計賽", 2,
                LocalDateTime.of(2099, 10, 1, 18, 0)));
        Clock clock = Clock.fixed(Instant.parse("2099-09-01T00:00:00Z"), ZoneId.of("UTC"));
        RegistrationService service = new RegistrationService(repository, clock);
        System.out.println("比賽報名系統已啟動（模擬資料）。");
        try {
            service.register("java-cup", "s01", "陳同學");
            System.out.println("報名成功，剩餘名額：" + service.remainingSeats("java-cup"));
        } catch (UnsupportedOperationException e) {
            System.out.println("尚待完成：" + e.getMessage());
            System.out.println("下一步：閱讀 README.md，完成 RegistrationService 並補上自己的測試。");
        }
    }
}
