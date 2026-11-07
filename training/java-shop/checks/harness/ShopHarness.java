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
 * 商店實習檢查協調器：編譯學生程式與可信檢查，啟動檢查並輸出單行 JSON。
 * 參數：submission 目錄、課程目錄、工作代號（products / orders-create / orders-list）。
 */
public final class ShopHarness {
    public static void main(String[] args) {
        try {
            System.out.println(run(args));
            System.out.flush();
        } catch (Exception e) {
            System.out.println("{\"environment_error\":\"" + Json.escape(e.getClass().getSimpleName() + " " + e.getMessage()) + "\"}");
        }
        System.exit(0);
    }

    private static String run(String[] args) throws Exception {
        Path submission = Path.of(args.length > 0 ? args[0] : "/submission");
        Path course = Path.of(args.length > 1 ? args[1] : "/course");
        String task = args.length > 2 ? args[2] : "products";
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) return "{\"environment_error\":\"容器內沒有可用的 JDK 編譯器\"}";
        Path work = Files.createTempDirectory("shop");
        Path classes = Files.createDirectories(work.resolve("classes"));
        List<Path> sources = new ArrayList<>(javaFiles(submission.resolve("src")));
        sources.add(course.resolve("checks/harness/ShopChecks.java"));
        sources.add(course.resolve("checks/harness/Json.java"));
        String compileError = compile(compiler, sources, classes);
        if (compileError != null) {
            return "{\"status\":\"completed\",\"checks\":[{\"key\":\"COMPILE\",\"label\":\"程式需能編譯\","
                    + "\"dimension\":\"task\",\"weight\":1,\"passed\":false,\"expected\":\"javac 編譯成功\","
                    + "\"actual\":\"" + Json.escape("編譯失敗：" + compileError) + "\"}]}";
        }
        Path resultFile = work.resolve("shop-result-" + java.util.UUID.randomUUID() + ".json");
        ProcessResult result = process(work, 120, "java", "-cp", classes.toString(), "ShopChecks", task, resultFile.toString());
        String body = Files.exists(resultFile) ? Files.readString(resultFile, StandardCharsets.UTF_8).strip() : "";
        if (!body.startsWith("[")) {
            return "{\"status\":\"completed\",\"checks\":[{\"key\":\"RUN\",\"label\":\"檢查需能完成\","
                    + "\"dimension\":\"task\",\"weight\":1,\"passed\":false,\"expected\":\"伺服器啟動並回應檢查\","
                    + "\"actual\":\"" + Json.escape("檢查未完成：" + result.output) + "\"}]}";
        }
        return "{\"status\":\"completed\",\"checks\":" + body + "}";
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
            boolean ok = compiler.getTask(null, manager, diagnostics, List.of("-encoding", "UTF-8", "-d", dest.toString(), "-proc:none"), null, units).call();
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
