#!/usr/bin/env python3
"""Mark pushed factory work as merged (or closed) once its PR or MR is, so the dashboard is
right even when the session that pushed it has ended.

    python3 sweep.py <FACTORY> [--once] [--every <seconds>]

Reads every `board/*.json` in the state folder. For each run that is `pushed`, and each job
that is `merging` (a one-off job, or a unit that ships on its own PR), it asks the host
(`gh` or `glab`, by `project.json`'s `host`) whether the PR or MR at its `url` has merged or
been closed. Then:

- a job whose PR merged becomes `merged`; one closed without merging becomes `closed`;
- a run becomes `merged` once its own PR (if it has one) and every unit that ships on its own
  PR have merged, and `closed` if its PR was closed without merging.

It only ever moves work forward to `merged` or `closed`, the two stages nothing leaves, so it
can't fight the session that owns a board file: owners never move work back out of them. It
writes a board file only when something changed, atomically (a `.tmp` file, then a rename),
and only after re-reading it to check the owner didn't change it meanwhile. It never
comments, merges, pushes or deletes anything.

--once checks once and exits. Otherwise it checks every --every seconds (default 300) for as
long as it runs; dashboard.sh starts one per state folder, next to the dashboard server.
"""
import datetime
import glob
import json
import os
import subprocess
import sys
import time


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def pr_state(host, url):
    """'merged', 'closed', 'open', or None when the host can't say."""
    if not url or not str(url).startswith(('http://', 'https://')):
        return None
    if host == 'gitlab':
        cmd = ['glab', 'mr', 'view', url, '-F', 'json']
    else:
        cmd = ['gh', 'pr', 'view', url, '--json', 'state']
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        return None
    try:
        state = str(json.loads(p.stdout).get('state', '')).lower()
    except ValueError:
        return None
    if state == 'merged':
        return 'merged'
    if state in ('closed', 'locked'):
        return 'closed'
    return 'open'


def sweep_board(board, host, cache):
    """Apply what the host says to one board's runs and jobs. Returns True if anything changed."""
    def state(url):
        if url not in cache:
            cache[url] = pr_state(host, url)
        return cache[url]

    changed = False
    stamp = now()
    jobs = board.get('jobs') or []
    for job in jobs:
        if job.get('stage') != 'merging' or not job.get('url'):
            continue
        s = state(job['url'])
        if s in ('merged', 'closed'):
            job['stage'] = s
            job['updated'] = stamp
            job['sweptAt'] = stamp
            changed = True
    for run in board.get('runs') or []:
        if run.get('stage') != 'pushed':
            continue
        own = [j for j in jobs if j.get('run') == run.get('id') and j.get('ships') == 'own']
        own_states = [j.get('stage') for j in own]
        own_merged = all(s in ('merged', 'closed') for s in own_states)
        if run.get('url'):
            s = state(run['url'])
            if s == 'closed':
                run['stage'] = 'closed'
            elif s == 'merged' and own_merged:
                run['stage'] = 'merged'
            else:
                continue
        elif own and own_merged:
            # every unit shipped on its own PR, and they are all in
            run['stage'] = 'merged'
        else:
            continue
        run['updated'] = stamp
        run['sweptAt'] = stamp
        changed = True
    if changed:
        board['updated'] = stamp
    return changed


def sweep(factory):
    try:
        with open(os.path.join(factory, 'project.json')) as f:
            host = json.load(f).get('host') or 'github'
    except (OSError, ValueError):
        host = 'github'
    if host not in ('github', 'gitlab'):
        return []   # no remote: `local` merges are recorded by the session itself
    cache, swept = {}, []
    for path in sorted(glob.glob(os.path.join(factory, 'board', '*.json'))):
        try:
            mtime = os.stat(path).st_mtime_ns
            with open(path) as f:
                board = json.load(f)
        except (OSError, ValueError):
            continue
        if not sweep_board(board, host, cache):
            continue
        try:
            # the owning session may have rewritten its file while the host was asked: if so,
            # leave it alone this time, and the next sweep starts from what the owner wrote
            if os.stat(path).st_mtime_ns != mtime:
                continue
            tmp = path[:-len('.json')] + '.sweep.tmp'
            with open(tmp, 'w') as f:
                json.dump(board, f, indent=2)
                f.write('\n')
            os.replace(tmp, path)
            swept.append(os.path.basename(path))
        except OSError:
            continue
    return swept


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith('-'):
        sys.stderr.write(__doc__)
        sys.exit(2)
    factory = os.path.abspath(os.path.expanduser(args[0]))
    every = 300.0
    if '--every' in args:
        try:
            every = max(30.0, float(args[args.index('--every') + 1]))
        except (IndexError, ValueError):
            sys.stderr.write(__doc__)
            sys.exit(2)
    while True:
        swept = sweep(factory)
        if swept:
            print(f"{now()} marked merged or closed in: {', '.join(swept)}", flush=True)
        if '--once' in args:
            break
        time.sleep(every)


if __name__ == '__main__':
    main()
