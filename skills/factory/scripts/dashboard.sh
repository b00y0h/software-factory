#!/usr/bin/env bash
# Make sure a repo's factory dashboard is being served, and print its link.
#
#   dashboard.sh <state folder> [--open]
#
# Prints "running <url>" when a server for this state folder is already up (started by any
# session), or "started <url>" when it starts one. --open opens the link in the default
# browser, but only when it had to start the server. The server listens on 127.0.0.1 only,
# on the first port from 8765 that is free or already serving this folder, and keeps running
# after this script exits. It also makes sure sweep.py is running for this folder (see below).
set -euo pipefail

state="${1:?usage: dashboard.sh <state folder> [--open]}"
open_after_start="${2:-}"
state="$(cd "$state" && pwd)"
[ -f "$state/dashboard.html" ] || { echo "no dashboard.html in $state" >&2; exit 1; }

# A marker unique to this state folder, so another repo's dashboard is never mistaken for ours.
marker="$state/.factory-id"
[ -s "$marker" ] || printf '%s\n' "$state" > "$marker"
want="$(cat "$marker")"

serves_us() { [ "$(curl -s --max-time 2 "$1/.factory-id" 2>/dev/null || true)" = "$want" ]; }

port_free() {
  if command -v lsof >/dev/null 2>&1; then
    ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
  else
    python3 -c 'import socket,sys; s=socket.socket(); s.bind(("127.0.0.1", int(sys.argv[1])))' "$1" 2>/dev/null
  fi
}

report() { printf '%s\n' "$2" > "$state/dashboard.url"; echo "$1 $2/dashboard.html"; }

# One sweeper per state folder, beside the server: it marks pushed work merged (or closed) once
# its PR or MR is, so the board stays right after the session that pushed it has ended. It only
# reads the host. Its log is sweep.log in the state folder.
ensure_sweep() {
  local pidfile="$state/.sweep.pid" here
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [ -s "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then return 0; fi
  command -v gh >/dev/null 2>&1 || command -v glab >/dev/null 2>&1 || return 0
  nohup python3 "$here/sweep.py" "$state" >>"$state/sweep.log" 2>&1 &
  echo $! > "$pidfile"
}
ensure_sweep || true

# And one Sentry poller, when the profile watches Sentry and a token is available (see
# sentry.py). It records new errors for triage, and verifies and resolves fixed ones.
ensure_sentry() {
  local pidfile="$state/.sentry.pid" here
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [ -s "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then return 0; fi
  python3 -c 'import json,sys; s=(json.load(open(sys.argv[1])).get("sentry") or {}); sys.exit(0 if s.get("url") and s.get("autonomy","triage")!="off" else 1)' \
    "$state/project.json" 2>/dev/null || return 0
  [ -n "${SENTRY_AUTH_TOKEN:-}" ] || [ -s "$HOME/.factory/sentry.token" ] || return 0
  nohup python3 "$here/sentry.py" poll "$state" >>"$state/sentry.log" 2>&1 &
  echo $! > "$pidfile"
}
ensure_sentry || true

# The link another session recorded, if that server is still up.
if [ -s "$state/dashboard.url" ] && serves_us "$(cat "$state/dashboard.url")"; then
  report running "$(cat "$state/dashboard.url")"; exit 0
fi

for port in $(seq 8765 8784); do
  url="http://localhost:$port"
  if serves_us "$url"; then report running "$url"; exit 0; fi
  port_free "$port" || continue
  nohup python3 -m http.server "$port" --bind 127.0.0.1 --directory "$state" >/dev/null 2>&1 &
  for _ in $(seq 1 25); do serves_us "$url" && break; sleep 0.2; done
  serves_us "$url" || { echo "the dashboard server on port $port did not answer" >&2; exit 1; }
  report started "$url"
  if [ "$open_after_start" = "--open" ]; then
    { command -v open >/dev/null 2>&1 && open "$url/dashboard.html"; } ||
      { command -v xdg-open >/dev/null 2>&1 && xdg-open "$url/dashboard.html"; } || true
  fi
  exit 0
done

echo "no free port between 8765 and 8784" >&2
exit 1
