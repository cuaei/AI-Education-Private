# Java 檢查執行環境：只有 JDK，沒有網路與外部套件需求。
# 學生程式在此容器編譯與執行，主服務不直接執行上傳內容。
FROM eclipse-temurin:17-jdk
RUN useradd --uid 10001 --create-home student || true
WORKDIR /tmp
USER 10001:10001
CMD ["sh", "/course/checks/run.sh"]
