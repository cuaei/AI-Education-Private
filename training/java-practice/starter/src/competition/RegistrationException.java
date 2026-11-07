package competition;

/** 報名失敗時使用的業務原因。檢查會核對原因，不要自行更換名稱。 */
public class RegistrationException extends RuntimeException {
    public enum Reason { INVALID_NAME, UNKNOWN_COMPETITION, FULL, CLOSED, NOT_FOUND }

    private final Reason reason;

    public RegistrationException(Reason reason, String message) {
        super(message);
        this.reason = reason;
    }

    public Reason reason() { return reason; }
}
