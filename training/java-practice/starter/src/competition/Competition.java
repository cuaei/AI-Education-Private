package competition;

import java.time.LocalDateTime;

/** 一場可比賽報名的活動。欄位由課程固定，學生不需要修改。 */
public final class Competition {
    private final String id;
    private final String name;
    private final int capacity;
    private final LocalDateTime deadline;

    public Competition(String id, String name, int capacity, LocalDateTime deadline) {
        if (id == null || id.isBlank()) throw new IllegalArgumentException("id 不可空白");
        if (capacity <= 0) throw new IllegalArgumentException("名額必須為正整數");
        this.id = id;
        this.name = name;
        this.capacity = capacity;
        this.deadline = deadline;
    }

    public String id() { return id; }
    public String name() { return name; }
    public int capacity() { return capacity; }
    public LocalDateTime deadline() { return deadline; }
}
