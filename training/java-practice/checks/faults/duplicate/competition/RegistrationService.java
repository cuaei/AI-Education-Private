package competition;

import java.time.Clock;
import java.time.LocalDateTime;
import java.util.List;

/** 內建故障一：重複報名會再占一個名額。只用於驗證學生測試是否有效，不進入學生下載包。 */
public final class RegistrationService {
    private final CompetitionRepository repository;
    private final Clock clock;

    public RegistrationService(CompetitionRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public Registration register(String competitionId, String studentId, String studentName) {
        if (studentName == null || studentName.isBlank()) {
            throw new RegistrationException(RegistrationException.Reason.INVALID_NAME, "姓名不可空白");
        }
        Competition competition = requireCompetition(competitionId);
        synchronized (repository.competitionLock(competitionId)) {
            requireOpen(competition);
            if (repository.findActive(competitionId).size() >= competition.capacity()) {
                throw new RegistrationException(RegistrationException.Reason.FULL, "名額已滿");
            }
            return repository.create(competitionId, studentId, studentName);
        }
    }

    public Registration cancel(String competitionId, String studentId) {
        Competition competition = requireCompetition(competitionId);
        synchronized (repository.competitionLock(competitionId)) {
            requireOpen(competition);
            for (Registration item : repository.findActive(competitionId)) {
                if (item.studentId().equals(studentId)) {
                    item.cancel();
                    return item;
                }
            }
            throw new RegistrationException(RegistrationException.Reason.NOT_FOUND, "沒有可取消的報名");
        }
    }

    public int remainingSeats(String competitionId) {
        Competition competition = requireCompetition(competitionId);
        return Math.max(0, competition.capacity() - repository.findActive(competitionId).size());
    }

    public List<Registration> listActive(String competitionId) {
        return repository.findActive(competitionId);
    }

    private Competition requireCompetition(String competitionId) {
        return repository.findCompetition(competitionId).orElseThrow(() ->
                new RegistrationException(RegistrationException.Reason.UNKNOWN_COMPETITION, "比賽不存在"));
    }

    private void requireOpen(Competition competition) {
        if (LocalDateTime.now(clock).isAfter(competition.deadline())) {
            throw new RegistrationException(RegistrationException.Reason.CLOSED, "已截止");
        }
    }
}
