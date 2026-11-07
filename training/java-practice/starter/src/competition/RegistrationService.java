package competition;

import java.time.Clock;
import java.util.List;

/**
 * 你要完成的主要類別：比賽報名的業務規則。
 * 已提供建構子與 listActive；register、cancel、remainingSeats 由你實作。
 * 完整規則見 README.md。時間一律使用注入的 clock，不要直接呼叫系統時間。
 */
public final class RegistrationService {
    private final CompetitionRepository repository;
    private final Clock clock;

    public RegistrationService(CompetitionRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    /**
     * 報名。規則順序：姓名檢查 → 比賽存在 → 已有有效報名則原樣回傳 → 截止判斷 → 名額判斷 → 建立。
     * 同一場比賽的「檢查名額＋建立」必須同步，不能先查再各自新增。
     */
    public Registration register(String competitionId, String studentId, String studentName) {
        throw new UnsupportedOperationException("TODO：請依 README 規則完成報名");
    }

    /** 取消自己的有效報名並釋放名額。 */
    public Registration cancel(String competitionId, String studentId) {
        throw new UnsupportedOperationException("TODO：請依 README 規則完成取消");
    }

    /** 剩餘名額＝容量減有效報名數，不可為負數。 */
    public int remainingSeats(String competitionId) {
        throw new UnsupportedOperationException("TODO：請依 README 規則完成剩餘名額");
    }

    /** 已提供：只列出有效報名，依報名先後排序。 */
    public List<Registration> listActive(String competitionId) {
        return repository.findActive(competitionId);
    }
}
