#!/bin/sh
set -eu
mkdir -p /tmp/classes
find /submission/src -type f -name '*.java' -print > /tmp/sources.txt
printf '%s\n' /adapter/CoreNameRunner.java >> /tmp/sources.txt
javac -encoding UTF-8 -proc:none -d /tmp/classes @/tmp/sources.txt
JOB_ID="${JOB_ID:-}" JOB_NONCE="${JOB_NONCE:-}" \
  java -Dfile.encoding=UTF-8 -cp /tmp/classes CoreNameRunner
