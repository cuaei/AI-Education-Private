import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;

/**
 * 綜合實作檢查協調器：在隔離容器內以 `java /checks/harness/PracticeHarness.java` 單檔啟動。
 * 只用 JDK 內建功能：編譯學生程式、執行可信核心檢查、對正確版與三個故障版執行學生測試，
 * 最後輸出單行 JSON 給平台。不讀取學生測試印出的文字作為通過依據。
 */
public final class PracticeHarness {
    private static Path submission;
    private static Path checksRoot;

    public static void main(String[] args) {
        submission = Path.of(args.length > 0 ? args[0] : "/submission");
        checksRoot = Path.of(args.length > 1 ? args[1] : "/checks");
        try {
            System.out.println(run());
            System.out.flush();
        } catch (Exception e) {
            System.out.println("{\"environment_error\":\"" + Json.escape(e.getClass().getSimpleName() + " " + e.getMessage()) + "\"}");
        }
        System.exit(0);
    }

    private static String run() throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) return "{\"environment_error\":\"容器內沒有可用的 JDK 編譯器\"}";
        Path work = Files.createTempDirectory("practice");
        List<Path> studentSources = javaFiles(submission.resolve("src"));
        List<Path> studentTests = javaFiles(submission.resolve("test"));
        StringBuilder out = new StringBuilder("{\"status\":\"completed\",\"checks\":[");

        Path studentClasses = Files.createDirectories(work.resolve("student"));
        List<Path> coreSources = new ArrayList<>(studentSources);
        coreSources.add(checksRoot.resolve("checks/harness/CoreChecks.java"));
        coreSources.add(checksRoot.resolve("checks/harness/Json.java"));
        String compileError = compile(compiler, coreSources, studentClasses);
        if (compileError != null) {
            for (String key : List.of("CORE-NAME", "CORE-UNKNOWN", "CORE-DUPLICATE", "CORE-CAPACITY", "CORE-DEADLINE",
                    "CORE-CANCEL", "CORE-CANCEL-UNKNOWN", "CORE-CANCEL-DEADLINE", "CORE-CONCURRENCY")) {
                out.append(check(key, "核心功能須能編譯並通過", "core", 5, false, "你的程式需能編譯", "編譯失敗：" + compileError)).append(',');
            }
        } else {
            Path coreResult = work.resolve("core-result.json");
            ProcessResult core = process(work, 90, "java", "-cp", studentClasses.toString(), "CoreChecks", coreResult.toString());
            String body = Files.exists(coreResult) ? Files.readString(coreResult, StandardCharsets.UTF_8).strip() : "";
            if (!body.startsWith("[")) {
                out.append(check("CORE-RUN", "核心檢查執行", "core", 45, false, "核心檢查需完成",
                        "核心檢查未能完成：" + core.output)).append(',');
            } else {
                out.append(body, 1, body.length() - 1).append(',');
            }
        }

        String[][] variants = {{"correct", "TEST-CORRECT", "你的測試對正確實作全部通過", "你的測試在正確實作上應全過"},
                {"duplicate", "TEST-FAULT-DUPLICATE", "你的測試能發現重複報名故障", "對重複報名故障版應出現斷言失敗"},
                {"capacity", "TEST-FAULT-CAPACITY", "你的測試能發現額滿故障", "對額滿故障版應出現斷言失敗"},
                {"ownership", "TEST-FAULT-OWNERSHIP", "你的測試能發現取消他人報名故障", "對越權取消故障版應出現斷言失敗"}};
        for (String[] variant : variants) {
            out.append(studentTest(compiler, work, studentTests, variant)).append(',');
        }
        for (String structure : structureChecks(studentSources)) {
            out.append(structure).append(',');
        }
        out.setLength(out.length() - 1);
        return out.append("]}").toString();
    }

    private static String studentTest(JavaCompiler compiler, Path work, List<Path> studentTests, String[] variant) throws Exception {
        String name = variant[0], key = variant[1], label = variant[2], expected = variant[3];
        boolean shouldPass = name.equals("correct");
        if (studentTests.isEmpty()) {
            return check(key, label, "student_tests", 5, false, expected, "缺少 test 目錄下的測試程式");
        }
        Path classes = Files.createDirectories(work.resolve("tests-" + name));
        // 固定類別永遠使用課程版本，不採用學生可能改過的副本；正確版 Service 只存在於 checks/base。
        List<Path> sources = new ArrayList<>(javaFiles(checksRoot.resolve("starter/src")).stream()
                .filter(p -> !p.getFileName().toString().equals("RegistrationService.java")).toList());
        if (!shouldPass) sources.addAll(javaFiles(checksRoot.resolve("checks/faults/" + name)));
        else sources.add(checksRoot.resolve("checks/base/competition/RegistrationService.java"));
        sources.addAll(studentTests);
        String compileError = compile(compiler, sources, classes);
        if (compileError != null) {
            return check(key, label, "student_tests", 5, false, expected, "你的測試無法編譯：" + compileError);
        }
        ProcessResult result = process(work, 40, "java", "-cp", classes.toString(), "competition.RegistrationServiceTest");
        if (result.timedOut) return check(key, label, "student_tests", 5, false, expected, "測試執行超時，不能算通過或發現故障");
        boolean passed = shouldPass ? result.exitCode == 0 : result.exitCode != 0;
        String actual = "測試實際結束碼 " + result.exitCode + "；" + (shouldPass ? "正確實作應回 0" : "故障實作應以非 0 結束");
        return check(key, label, "student_tests", 5, passed, expected, actual);
    }

    private static List<String> structureChecks(List<Path> studentSources) throws IOException {
        StringBuilder all = new StringBuilder();
        int longest = 0;
        String longestName = "";
        for (Path source : studentSources) {
            String text = Files.readString(source, StandardCharsets.UTF_8);
            all.append(text).append('\n');
            List<String> lines = text.lines().toList();
            if (lines.size() > longest) { longest = lines.size(); longestName = source.getFileName().toString(); }
        }
        String code = all.toString();
        boolean usesSystemTime = code.contains("LocalDateTime.now()") || code.contains("Instant.now()")
                || code.contains("System.currentTimeMillis") || code.contains("new Date(");
        boolean emptyCatch = code.replaceAll("(?s)/\\*.*?\\*/", "").replaceAll("//[^\\n]*", "")
                .matches("(?s).*catch\\s*\\([^)]*\\)\\s*\\{\\s*\\}.*") || code.contains("printStackTrace");
        boolean staticState = code.matches("(?s).*static\\s+(?!final)[\\w<>?, ]*(List|Map|Set)[\\w<>?, ]+\\w+\\s*[=;].*");
        return List.of(
                check("STRUCT-CLOCK", "時間使用注入的 Clock", "structure", 5, !usesSystemTime,
                        "不可直接使用系統時間", usesSystemTime ? "偵測到直接使用系統時間的呼叫" : "未發現直接使用系統時間"),
                check("STRUCT-SIZE", "單一類別不超過 400 行", "structure", 5, longest <= 400,
                        "單一類別不超過 400 行", "最長檔案 " + longestName + " 共 " + longest + " 行"),
                check("STRUCT-ERRORS", "不以空 catch 或印出堆疊代替錯誤處理", "structure", 5, !emptyCatch,
                        "不可有空 catch 或 printStackTrace", emptyCatch ? "偵測到空 catch 或 printStackTrace" : "未發現空 catch 或 printStackTrace"),
                check("STRUCT-STATE", "業務狀態不放在可變 static 集合", "structure", 5, !staticState,
                        "不可使用可變 static 集合保存業務狀態", staticState ? "偵測到可變 static 集合" : "未發現可變 static 集合"));
    }

    private static String check(String key, String label, String dimension, int weight, boolean passed, String expected, String actual) {
        return "{\"key\":\"" + key + "\",\"label\":\"" + Json.escape(label) + "\",\"dimension\":\"" + dimension
                + "\",\"weight\":" + weight + ",\"passed\":" + passed + ",\"expected\":\"" + Json.escape(expected)
                + "\",\"actual\":\"" + Json.escape(actual) + "\"}";
    }

    private static List<Path> javaFiles(Path root) throws IOException {
        if (!Files.isDirectory(root)) return List.of();
        try (Stream<Path> stream = Files.walk(root)) {
            return stream.filter(p -> p.toString().endsWith(".java")).sorted().toList();
        }
    }

    private static String compile(JavaCompiler compiler, List<Path> sources, Path dest) throws IOException {
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        try (StandardJavaFileManager manager = compiler.getStandardFileManager(diagnostics, null, StandardCharsets.UTF_8)) {
            Iterable<? extends JavaFileObject> units = manager.getJavaFileObjectsFromPaths(sources);
            List<String> options = List.of("-encoding", "UTF-8", "-d", dest.toString(), "-proc:none");
            boolean ok = compiler.getTask(null, manager, diagnostics, options, null, units).call();
            if (ok) return null;
        }
        StringBuilder message = new StringBuilder();
        for (Diagnostic<? extends JavaFileObject> diagnostic : diagnostics.getDiagnostics()) {
            if (message.length() > 700) break;
            String name = diagnostic.getSource() == null ? "" : Path.of(diagnostic.getSource().toUri()).getFileName().toString();
            message.append(name).append(':').append(diagnostic.getLineNumber()).append(' ')
                    .append(diagnostic.getMessage(null)).append("；");
        }
        return message.toString();
    }

    private record ProcessResult(int exitCode, String output, boolean timedOut) { }

    private static ProcessResult process(Path work, int seconds, String... command) {
        try {
            Process process = new ProcessBuilder(command).directory(work.toFile()).redirectErrorStream(true).start();
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            Thread reader = new Thread(() -> {
                try { process.getInputStream().transferTo(buffer); } catch (IOException ignored) { }
            });
            reader.setDaemon(true);
            reader.start();
            if (!process.waitFor(seconds, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                return new ProcessResult(-1, "執行超時", true);
            }
            reader.join(2000);
            String output = buffer.toString(StandardCharsets.UTF_8);
            return new ProcessResult(process.exitValue(), output.length() > 2000 ? output.substring(output.length() - 2000) : output, false);
        } catch (Exception e) {
            return new ProcessResult(-1, e.getClass().getSimpleName() + " " + e.getMessage(), false);
        }
    }
}
