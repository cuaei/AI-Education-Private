package competition;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 課程提供的記憶體儲存。只負責保存與查詢，業務規則由 RegistrationService 實作。
 * 注意：這裡的查詢與寫入各自執行緒安全，但「先檢查名額再新增」屬於多步驟操作，
 * 必須在 Service 內以 competitionLock(competitionId) 同步，否則兩個請求可能同時搶到最後一個名額。
 */
public final class CompetitionRepository {
    private final Map<String, Competition> competitions = new ConcurrentHashMap<>();
    private final Map<String, List<Registration>> registrations = new ConcurrentHashMap<>();
    private final Map<String, Object> locks = new ConcurrentHashMap<>();
    private long sequence = 0;

    public void addCompetition(Competition competition) {
        competitions.put(competition.id(), competition);
        registrations.putIfAbsent(competition.id(), new ArrayList<>());
    }

    public Optional<Competition> findCompetition(String id) {
        return Optional.ofNullable(competitions.get(id));
    }

    /** 回傳該比賽的同步鎖；同一場比賽的報名與取消必須使用同一把鎖。 */
    public Object competitionLock(String competitionId) {
        return locks.computeIfAbsent(competitionId, key -> new Object());
    }

    /** 回傳快照，包含已取消的紀錄；修改回傳的清單不會影響儲存內容。 */
    public synchronized List<Registration> findAll(String competitionId) {
        return new ArrayList<>(registrations.getOrDefault(competitionId, List.of()));
    }

    public synchronized List<Registration> findActive(String competitionId) {
        List<Registration> result = new ArrayList<>();
        for (Registration item : registrations.getOrDefault(competitionId, List.of())) {
            if (item.status() == Registration.Status.ACTIVE) result.add(item);
        }
        return result;
    }

    /** 建立並保存一筆 ACTIVE 報名，sequence 遞增代表先後順序。 */
    public synchronized Registration create(String competitionId, String studentId, String studentName) {
        Registration item = new Registration(++sequence, competitionId, studentId, studentName);
        registrations.computeIfAbsent(competitionId, key -> new ArrayList<>()).add(item);
        return item;
    }
}
