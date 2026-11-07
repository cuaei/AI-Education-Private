import competition.Competition;
import competition.CompetitionRepository;
import competition.RegistrationException;
import competition.RegistrationService;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

/** Platform regression test for the CORE-NAME contract. */
public final class CoreNameContractTest {
    public static void main(String[] args) {
        RegistrationService service = service();
        expectInvalid(service, null);
        expectInvalid(service, "");
        expectInvalid(service, " ");
        expectInvalid(service, "   ");
        expectInvalid(service, "\t\n");
        expectInvalid(service, "\u2003\u2003");
        service.register("cup", "valid", "陳同學");
        service.register("cup", "literal", "null");
    }

    private static RegistrationService service() {
        CompetitionRepository repository = new CompetitionRepository();
        repository.addCompetition(new Competition("cup", "Java 程式設計賽", 20,
                LocalDateTime.of(2099, 10, 1, 18, 0)));
        return new RegistrationService(repository,
                Clock.fixed(Instant.parse("2099-09-01T00:00:00Z"), ZoneId.of("UTC")));
    }

    private static void expectInvalid(RegistrationService service, String name) {
        try {
            service.register("cup", "student-" + String.valueOf(name), name);
            throw new AssertionError("expected INVALID_NAME");
        } catch (RegistrationException error) {
            if (error.reason() != RegistrationException.Reason.INVALID_NAME) {
                throw new AssertionError("wrong reason: " + error.reason());
            }
        }
    }
}
