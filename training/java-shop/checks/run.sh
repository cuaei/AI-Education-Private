#!/bin/sh
# 在隔離容器內執行：$1 為工作代號 products / orders-create / orders-list。
set -e
mkdir -p /tmp/harness-classes
javac -encoding UTF-8 -proc:none -d /tmp/harness-classes /course/checks/harness/ShopHarness.java /course/checks/harness/Json.java
java -Dfile.encoding=UTF-8 -Dstdout.encoding=UTF-8 -Dsun.stdout.encoding=UTF-8 \
  -cp /tmp/harness-classes ShopHarness /submission /course "$1"
