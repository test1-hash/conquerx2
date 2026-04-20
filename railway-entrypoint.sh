#!/bin/sh
set -eu

STATE_PATH="${CX2_STATE_PATH:-/data/state.json}"
DOCS_DIR="${CX2_DOCS_DIR:-/data/docs}"
BUNDLED_STATE_PATH="${BUNDLED_STATE_PATH:-/app/data/state.json}"
BUNDLED_DOCS_DIR="${BUNDLED_DOCS_DIR:-/app/docs}"

log() {
  printf '%s %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

seed_data() {
  mkdir -p "$(dirname "$STATE_PATH")" "$DOCS_DIR"

  if [ ! -f "$STATE_PATH" ] && [ -f "$BUNDLED_STATE_PATH" ]; then
    cp "$BUNDLED_STATE_PATH" "$STATE_PATH"
    log "Seeded state file at $STATE_PATH"
  fi

  if [ ! -f "$DOCS_DIR/index.html" ] && [ -d "$BUNDLED_DOCS_DIR" ]; then
    cp -R "$BUNDLED_DOCS_DIR"/. "$DOCS_DIR"/
    log "Seeded docs directory at $DOCS_DIR"
  fi
}

initial_build() {
  log "Building static site into $DOCS_DIR"
  python manage.py build
}

catch_up_update() {
  log "Checking whether a catch-up update is needed"
  python manage.py update-if-needed
}

updater_loop() {
  while true; do
    sleep_seconds="$(python manage.py next-update-check-seconds)"
    log "Sleeping ${sleep_seconds}s until next update window"
    sleep "$sleep_seconds"
    log "Running scheduled update"
    if python manage.py update-if-needed; then
      log "Scheduled update finished"
    else
      log "Scheduled update failed"
    fi
  done
}

main() {
  seed_data
  initial_build
  catch_up_update

  if [ "${CX2_BACKGROUND_UPDATER:-1}" != "0" ]; then
    updater_loop &
    log "Background updater started"
  else
    log "Background updater disabled"
  fi

  exec caddy run --config /app/Caddyfile --adapter caddyfile
}

main "$@"
