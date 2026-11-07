package competition;

/** 一筆報名紀錄。同一學生對同一比賽最多一筆 ACTIVE。 */
public final class Registration {
    public enum Status { ACTIVE, CANCELLED }

    private final long sequence;
    private final String competitionId;
    private final String studentId;
    private final String studentName;
    private Status status;

    public Registration(long sequence, String competitionId, String studentId, String studentName) {
        this.sequence = sequence;
        this.competitionId = competitionId;
        this.studentId = studentId;
        this.studentName = studentName;
        this.status = Status.ACTIVE;
    }

    public long sequence() { return sequence; }
    public String competitionId() { return competitionId; }
    public String studentId() { return studentId; }
    public String studentName() { return studentName; }
    public Status status() { return status; }
    public void cancel() { this.status = Status.CANCELLED; }

    @Override public String toString() {
        return "#" + sequence + " " + competitionId + " " + studentId + " " + status;
    }
}
