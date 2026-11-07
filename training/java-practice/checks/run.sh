#!/bin/sh
# 在隔離容器內執行：先編譯課程檢查器，再對學生上傳內容執行檢查。
set -e
mkdir -p /tmp/harness-classes
javac -encoding UTF-8 -proc:none -d /tmp/harness-classes /course/checks/harness/PracticeHarness.java /course/checks/harness/Json.java
java -Dfile.encoding=UTF-8 -Dstdout.encoding=UTF-8 -Dsun.stdout.encoding=UTF-8 \
  -cp /tmp/harness-classes PracticeHarness /submission /course
