import competition.Competition;
import competition.CompetitionRepository;
import competition.Registration;
import competition.RegistrationException;
import competition.RegistrationService;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/** 可信核心功能檢查：與學生原始碼一起編譯後執行，輸出 JSON。不讀取學生測試的輸出文字。 */
public final class CoreChecks {
    private static final String OPEN = "2099-09-01T00:00:00Z";
    private static final String CLOSED = "2099-11-01T00:00:00Z";
    private static final List<String> RESULTS = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        run("CORE-NAME", "空白姓名必須拒絕並回 INVALID_NAME", CoreChecks::blankName);
        run("CORE-UNKNOWN", "比賽不存在回 UNKNOWN_COMPETITION", CoreChecks::unknownCompetition);
        run("CORE-DUPLICATE", "重複報名原樣回傳且不占名額", CoreChecks::duplicate);
        run("CORE-CAPACITY", "額滿回 FULL 且名額不為負", CoreChecks::capacity);
        run("CORE-DEADLINE", "截止後報名回 CLOSED", CoreChecks::deadline);
        run("CORE-CANCEL", "取消釋放名額且不再出現在有效名單", CoreChecks::cancel);
        run("CORE-CANCEL-UNKNOWN", "沒有有效報名時取消回 NOT_FOUND", CoreChecks::cancelUnknown);
        run("CORE-CANCEL-DEADLINE", "截止後取消回 CLOSED", CoreChecks::cancelDeadline);
        run("CORE-CONCURRENCY", "八人同時搶三個名額只能三人成功", CoreChecks::concurrency);
        String json = "[" + String.join(",", RESULTS) + "]";
        if (args.length > 0) {
            java.nio.file.Files.writeString(java.nio.file.Path.of(args[0]), json, java.nio.charset.StandardCharsets.UTF_8);
        } else {
            System.out.println(json);
        }
        System.out.flush();
        System.exit(0);
    }

    private interface Case { String run() throws Exception; }

    private static void run(String key, String label, Case test) {
        String actual;
        boolean passed;
        try {
            actual = test.run();
            passed = actual == null;
            if (passed) actual = "符合預期";
        } catch (Throwable error) {
            passed = false;
            actual = "執行異常：" + error.getClass().getSimpleName() + " " + String.valueOf(error.getMessage());
        }
        RESULTS.add("{\"key\":\"" + key + "\",\"label\":\"" + label + "\",\"dimension\":\"core\",\"weight\":5,"
                + "\"passed\":" + passed + ",\"expected\":\"" + label + "\",\"actual\":\"" + Json.escape(actual) + "\"}");
    }

    private static RegistrationService service(String instant, int capacity) {
        CompetitionRepository repository = new CompetitionRepository();
        repository.addCompetition(new Competition("cup", "Java 程式設計賽", capacity, LocalDateTime.of(2099, 10, 1, 18, 0)));
        return new RegistrationService(repository, Clock.fixed(Instant.parse(instant), ZoneId.of("UTC")));
    }

    private static String expectReason(Runnable action, RegistrationException.Reason reason, String successMessage) {
        try {
            action.run();
            return successMessage;
        } catch (RegistrationException e) {
            return e.reason() == reason ? null : "原因應為 " + reason + "，實際為 " + e.reason();
        }
    }

    private static String blankName() {
        RegistrationService service = service(OPEN, 2);
        String message = expectReason(() -> service.register("cup", "s01", "   "), RegistrationException.Reason.INVALID_NAME, "全空白姓名未被拒絕");
        if (message != null) return message;
        return expectReason(() -> service.register("cup", "s01", null), RegistrationException.Reason.INVALID_NAME, "null 姓名未被拒絕");
    }

    private static String unknownCompetition() {
        return expectReason(() -> service(OPEN, 2).register("no-such-cup", "s01", "陳同學"),
                RegistrationException.Reason.UNKNOWN_COMPETITION, "不存在的比賽未被拒絕");
    }

    private static String duplicate() {
        RegistrationService service = service(OPEN, 2);
        Registration first = service.register("cup", "s01", "陳同學");
        Registration second = service.register("cup", "s01", "陳同學");
        if (first.sequence() != second.sequence()) return "重複報名產生了新的紀錄";
        if (service.listActive("cup").size() != 1) return "重複報名後有效報名數應為 1，實際 " + service.listActive("cup").size();
        if (service.remainingSeats("cup") != 1) return "重複報名後剩餘名額應為 1，實際 " + service.remainingSeats("cup");
        return null;
    }

    private static String capacity() {
        RegistrationService service = service(OPEN, 1);
        service.register("cup", "s01", "陳同學");
        String message = expectReason(() -> service.register("cup", "s02", "林同學"), RegistrationException.Reason.FULL, "額滿仍可讓第二位學生報名");
        if (message != null) return message;
        if (service.remainingSeats("cup") < 0) return "剩餘名額出現負數";
        if (service.listActive("cup").size() != 1) return "額滿後有效報名數應為 1，實際 " + service.listActive("cup").size();
        return null;
    }

    private static String deadline() {
        return expectReason(() -> service(CLOSED, 2).register("cup", "s01", "陳同學"),
                RegistrationException.Reason.CLOSED, "截止後仍可報名");
    }

    private static String cancel() {
        RegistrationService service = service(OPEN, 1);
        service.register("cup", "s01", "陳同學");
        service.cancel("cup", "s01");
        if (service.remainingSeats("cup") != 1) return "取消後剩餘名額應為 1，實際 " + service.remainingSeats("cup");
        if (!service.listActive("cup").isEmpty()) return "已取消的報名仍出現在有效名單";
        try {
            service.register("cup", "s02", "林同學");
        } catch (RegistrationException e) {
            return "取消後應可讓他人報名，實際回 " + e.reason();
        }
        return null;
    }

    private static String cancelUnknown() {
        return expectReason(() -> service(OPEN, 2).cancel("cup", "nobody"), RegistrationException.Reason.NOT_FOUND, "沒有報名卻能取消");
    }

    private static String cancelDeadline() {
        RegistrationService service = service(OPEN, 1);
        service.register("cup", "s01", "陳同學");
        RegistrationService closed = service(CLOSED, 1);
        return expectReason(() -> closed.cancel("cup", "s01"), RegistrationException.Reason.CLOSED, "截止後仍可取消");
    }

    private static String concurrency() throws Exception {
        RegistrationService service = service(OPEN, 3);
        ExecutorService pool = Executors.newFixedThreadPool(8);
        try {
            List<Callable<String>> tasks = new ArrayList<>();
            for (int i = 0; i < 8; i++) {
                String student = "s" + i;
                tasks.add(() -> {
                    try {
                        service.register("cup", student, "學生" + student);
                        return "ok";
                    } catch (RegistrationException e) {
                        return e.reason().name();
                    }
                });
            }
            int success = 0;
            for (Future<String> future : pool.invokeAll(tasks)) {
                if ("ok".equals(future.get())) success++;
            }
            if (success != 3) return "容量 3 時應恰好 3 人成功，實際 " + success + " 人";
            if (service.listActive("cup").size() != 3) return "最終有效報名數應為 3，實際 " + service.listActive("cup").size();
            return null;
        } finally {
            pool.shutdownNow();
        }
    }
}
