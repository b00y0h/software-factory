#!/usr/bin/env bash
# Make sure the factory hub is serving every repo's dashboard, and print this repo's link.
#
#   dashboard.sh <state folder> [--open]
#
# One hub (hub.py) serves every repo's state folder under the factory home (the state
# folder's parent, normally ~/.factory) from one localhost port, so one page shows every
# project and switches between them. Prints "running <url>" when a hub is already up (started
# by any session, in any repo), or "started <url>" when it starts one. The link opens this
# repo's board; the page's project menu reaches every other repo. --open opens the link in the
# default browser, but only when it had to start the hub. The hub listens on 127.0.0.1 only,
# on the first port from 8765 that is free or already serving this home, and keeps running
# after this script exits. A hub from an older plugin is replaced by this one's. The script
# also makes sure sweep.py (and sentry.py, when set up) are running for this state folder.
set -euo pipefail

state="${1:?usage: dashboard.sh <state folder> [--open]}"
open_after_start="${2:-}"
state="$(cd "$state" && pwd)"
home="$(dirname "$state")"
repo="$(basename "$state")"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The page itself lives once, at the home, and a newer copy is never replaced by an older one.
version_of() { grep -o 'factory-dashboard-version" content="[0-9]*' "$1" 2>/dev/null | grep -o '[0-9]*$' || echo 0; }
asset="$here/../assets/dashboard.html"
if [ ! -f "$home/dashboard.html" ] || [ "$(version_of "$home/dashboard.html")" -lt "$(version_of "$asset")" ]; then
  cp "$asset" "$home/dashboard.html.tmp" && mv "$home/dashboard.html.tmp" "$home/dashboard.html"
fi

# One sweeper per state folder: it marks pushed work merged (or closed) once its PR or MR is,
# so the board stays right after the session that pushed it has ended. It only reads the host.
# Its log is sweep.log in the state folder.
ensure_sweep() {
  local pidfile="$state/.sweep.pid"
  if [ -s "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then return 0; fi
  command -v gh >/dev/null 2>&1 || command -v glab >/dev/null 2>&1 || return 0
  nohup python3 "$here/sweep.py" "$state" >>"$state/sweep.log" 2>&1 &
  echo $! > "$pidfile"
}
ensure_sweep || true

# And one Sentry poller, when the profile watches Sentry and a token is available (see
# sentry.py). It records new errors for triage, and verifies and resolves fixed ones.
ensure_sentry() {
  local pidfile="$state/.sentry.pid"
  if [ -s "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then return 0; fi
  python3 -c 'import json,sys; s=(json.load(open(sys.argv[1])).get("sentry") or {}); sys.exit(0 if s.get("url") and s.get("autonomy","triage")!="off" else 1)' \
    "$state/project.json" 2>/dev/null || return 0
  [ -n "${SENTRY_AUTH_TOKEN:-}" ] || [ -s "$HOME/.factory/sentry.token" ] || return 0
  nohup python3 "$here/sentry.py" poll "$state" >>"$state/sentry.log" 2>&1 &
  echo $! > "$pidfile"
}
ensure_sentry || true

# The hub answers /.factory-id with "factory-hub <home>", so another home's hub, or a
# per-repo server from a plugin before 0.14, is never mistaken for ours.
want="factory-hub $home"
serves_us() { [ "$(curl -s --max-time 2 "$1/.factory-id" 2>/dev/null || true)" = "$want" ]; }
hub_version() { curl -s --max-time 2 "$1/api/hub" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("hub", 0))' 2>/dev/null || echo 0; }
mine="$(grep -m1 '^HUB_VERSION' "$here/hub.py" | grep -o '[0-9]*$')"

port_free() {
  if command -v lsof >/dev/null 2>&1; then
    ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
  else
    python3 -c 'import socket,sys; s=socket.socket(); s.bind(("127.0.0.1", int(sys.argv[1])))' "$1" 2>/dev/null
  fi
}

link() { echo "$1/dashboard.html#/p/$repo"; }

start_hub() {   # start_hub <port>: start one and wait until it answers
  local url="http://localhost:$1"
  nohup python3 "$here/hub.py" "$home" --port "$1" >>"$home/hub.log" 2>&1 &
  echo $! > "$home/.hub.pid"
  for _ in $(seq 1 25); do serves_us "$url" && break; sleep 0.2; done
  serves_us "$url" || { echo "the factory hub on port $1 did not answer (see $home/hub.log)" >&2; exit 1; }
  printf '%s\n' "$url" > "$home/hub.url"
}

open_link() {
  [ "$open_after_start" = "--open" ] || return 0
  { command -v open >/dev/null 2>&1 && open "$1"; } || { command -v xdg-open >/dev/null 2>&1 && xdg-open "$1"; } || true
}

use() {   # use <url>: report a running hub, replacing it first if it is older than ours
  local url="$1" port="${1##*:}"
  local pid; pid="$(cat "$home/.hub.pid" 2>/dev/null || true)"
  # only a pid that is still a hub: a stale pid file may name some other process by now
  if [ "$(hub_version "$url")" -lt "${mine:-0}" ] && [ -n "$pid" ] && ps -p "$pid" -o args= 2>/dev/null | grep -q 'hub\.py'; then
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 25); do port_free "$port" && break; sleep 0.2; done
    if port_free "$port"; then start_hub "$port"; echo "running $(link "$url")"; exit 0; fi
  fi
  printf '%s\n' "$url" > "$home/hub.url"
  echo "running $(link "$url")"; exit 0
}

# The link a session recorded, if that hub is still up.
if [ -s "$home/hub.url" ] && serves_us "$(cat "$home/hub.url")"; then use "$(cat "$home/hub.url")"; fi

for port in $(seq 8765 8784); do
  url="http://localhost:$port"
  if serves_us "$url"; then use "$url"; fi
  port_free "$port" || continue
  start_hub "$port"
  echo "started $(link "$url")"
  open_link "$(link "$url")"
  exit 0
done

echo "no free port between 8765 and 8784" >&2
exit 1
