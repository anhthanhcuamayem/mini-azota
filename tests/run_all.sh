#!/usr/bin/env bash
# Chạy toàn bộ test với mock Supabase + mock AI (không cần project Supabase thật).
#   tests/run_all.sh            -> regression + API + e2e
set -uo pipefail
cd "$(dirname "$0")/.."

SUPA_PORT=54321
AI_PORT=9099
APP_PORT=8011
LOG_DIR=$(mktemp -d)

python3 tests/mock_supabase.py "$SUPA_PORT" > "$LOG_DIR/supabase.log" 2>&1 &
SUPA_PID=$!
python3 tests/mock_ai.py ok "$AI_PORT" > "$LOG_DIR/ai.log" 2>&1 &
AI_PID=$!
APP_PID=""

cleanup() {
  [ -n "$APP_PID" ] && kill "$APP_PID" 2>/dev/null
  kill "$SUPA_PID" "$AI_PID" 2>/dev/null
  wait 2>/dev/null
}
trap cleanup EXIT

export SUPABASE_URL="http://127.0.0.1:$SUPA_PORT"
export SUPABASE_SERVICE_ROLE_KEY="test-service-role-key"
export AI_BASE_URL="http://127.0.0.1:$AI_PORT/v1"
export AI_API_KEY="test-key"
export AI_MODEL="mock-model"

if ! python3 tests/make_fixtures.py > "$LOG_DIR/fixtures.log" 2>&1; then
  echo "make_fixtures FAILED"; cat "$LOG_DIR/fixtures.log"; exit 1
fi

uvicorn main:app --host 127.0.0.1 --port "$APP_PORT" --ws none --log-level warning > "$LOG_DIR/app.log" 2>&1 &
APP_PID=$!

ready=0
for _ in $(seq 1 80); do
  if curl -fsS "http://127.0.0.1:$APP_PORT/admin/status" >/dev/null 2>&1; then ready=1; break; fi
  sleep 0.5
done
if [ "$ready" != "1" ]; then
  echo "server không khởi động được"; cat "$LOG_DIR/app.log"; exit 1
fi

status=0
echo "=================== test_regression.py ==================="
python3 tests/test_regression.py || status=1
echo "=================== test_school_api.py ==================="
python3 tests/test_school_api.py || status=1
echo "=================== e2e_browser.py ======================="
python3 tests/e2e_browser.py || status=1

exit $status
