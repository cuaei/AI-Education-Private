import competition.CompetitionRepository;
import competition.Competition;
import competition.Registration;
import competition.RegistrationException;
import competition.RegistrationService;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Base64;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Fixed platform adapter. It emits observations only; it never emits scores. */
public final class CoreNameRunner {
    private static final int MAX_FRAME = 64 * 1024;
    private static final Pattern NAME = Pattern.compile("\\\"student_name\\\"\\s*:\\s*(null|\\\"((?:\\\\.|[^\\\"\\\\])*)\\\")");

    public static void main(String[] args) throws Exception {
        // Student code is untrusted and may write System.out. Preserve the
        // protocol stream, redirect student output to stderr, and let the
        // coordinator capture it as untrusted diagnostics.
        java.io.PrintStream protocolOut = System.out;
        System.setOut(System.err);
        BufferedInputStream input = new BufferedInputStream(System.in);
        BufferedOutputStream output = new BufferedOutputStream(protocolOut);
        while (true) {
            byte[] frame;
            try { frame = readFrame(input); }
            catch (EOFException end) { return; }
            String request = new String(frame, StandardCharsets.UTF_8);
            String requestId = field(request, "request_id");
            try {
                String name = parseName(request);
                RegistrationService service = service();
                try {
                    Registration registration = service.register("cup", "s01", name);
                    write(output, response(requestId, "return", "{}"));
                } catch (RegistrationException error) {
                    String payload = "{\"exception_type\":\"RegistrationException\",\"reason\":\""
                            + error.reason().name() + "\"}";
                    write(output, response(requestId, "exception", payload));
                }
            } catch (Throwable error) {
                String payload = "{\"error\":\"" + escape(error.getClass().getSimpleName()) + "\"}";
                write(output, response(requestId, "process_error", payload));
            }
        }
    }

    private static RegistrationService service() {
        CompetitionRepository repository = new CompetitionRepository();
        repository.addCompetition(new Competition("cup", "Java 程式設計賽", 2,
                LocalDateTime.of(2099, 10, 1, 18, 0)));
        return new RegistrationService(repository,
                Clock.fixed(Instant.parse("2099-09-01T00:00:00Z"), ZoneId.of("UTC")));
    }

    private static String parseName(String request) {
        Matcher matcher = NAME.matcher(request);
        if (!matcher.find()) throw new IllegalArgumentException("missing student_name");
        if ("null".equals(matcher.group(1))) return null;
        return unescape(matcher.group(2));
    }

    private static String response(String requestId, String kind, String payload) {
        return "{\"protocol\":1,\"job_id\":\"" + fieldFromEnv("JOB_ID")
                + "\",\"nonce\":\"" + fieldFromEnv("JOB_NONCE") + "\",\"request_id\":\""
                + escape(requestId) + "\",\"case\":\"CORE-NAME\",\"command\":\"observation\",\"kind\":\""
                + kind + "\",\"payload\":" + payload + "}";
    }

    private static String field(String json, String key) {
        Pattern pattern = Pattern.compile("\\\"" + Pattern.quote(key) + "\\\"\\s*:\\s*\\\"((?:\\\\.|[^\\\"\\\\])*)\\\"");
        Matcher matcher = pattern.matcher(json);
        return matcher.find() ? unescape(matcher.group(1)) : "";
    }

    private static String fieldFromEnv(String key) { return escape(System.getenv().getOrDefault(key, "")); }

    private static String unescape(String value) {
        return value.replace("\\\\", "\\").replace("\\\"", "\"").replace("\\n", "\n")
                .replace("\\r", "\r").replace("\\t", "\t");
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
                .replace("\r", "\\r").replace("\t", "\\t");
    }

    private static byte[] readFrame(BufferedInputStream input) throws IOException {
        int a = input.read(), b = input.read(), c = input.read(), d = input.read();
        if (a < 0) throw new EOFException();
        if ((a | b | c | d) < 0) throw new EOFException();
        int length = (a << 24) | (b << 16) | (c << 8) | d;
        if (length <= 0 || length > MAX_FRAME) throw new IOException("invalid frame length");
        byte[] body = input.readNBytes(length);
        if (body.length != length) throw new EOFException();
        return body;
    }

    private static void write(BufferedOutputStream output, String message) throws IOException {
        byte[] body = message.getBytes(StandardCharsets.UTF_8);
        if (body.length > MAX_FRAME) throw new IOException("response too large");
        output.write((body.length >>> 24) & 0xff); output.write((body.length >>> 16) & 0xff);
        output.write((body.length >>> 8) & 0xff); output.write(body.length & 0xff);
        output.write(body); output.flush();
    }
}
