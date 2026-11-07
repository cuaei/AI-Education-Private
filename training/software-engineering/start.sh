#!/bin/sh
set -eu
mkdir -p /tmp/work
cp -R /submission/. /tmp/work/
cd /tmp/work/frontend
ln -s /opt/student-deps/node_modules node_modules
# Fixed commands: submitted package scripts are not executed.
/opt/student-deps/node_modules/.bin/tsc --noEmit
/opt/student-deps/node_modules/.bin/vite build --config /opt/empty-vite.config.mjs --configLoader native
cd /tmp/work
exec python -m uvicorn backend.app:app --host 0.0.0.0 --port 8080
