#!/usr/bin/env python3
"""Where a pushed PR or MR stands: its checks on the pushed commit, and whether it merges.

    python3 ci.py <github|gitlab> <PR or MR url> <sha> [--wait <minutes>]

Prints one line of JSON and exits 0 (2 on a usage error):

    {"status": "green", "sha": "<sha>", "failed": [], "pending": [], "conflict": false}

- status is one of:
  - `green`: every check on <sha> finished, and none failed (skipped checks are fine).
  - `red`: at least one check on <sha> failed or was cancelled. `failed` lists them as
    {"name", "link"}.
  - `pending`: checks are still running when the wait ran out. `pending` lists them.
  - `none`: the host reports no checks at all for <sha>.
  - `stale`: the PR's head is no longer <sha>, so someone pushed after the factory did.
  - `merged` or `closed`: the PR is no longer open.
  - `error`: the CLI failed. `error` says why.
- conflict is true when the host says the PR can't merge cleanly into its base.

--wait polls every 30 seconds until no check is pending, or the minutes run out. Without it,
the script reports once. It only reads; it never re-runs, comments or merges.
"""
import json
import subprocess
import sys
import time

POLL_SECONDS = 30


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr.strip()


def github(url, sha):
    code, out, err = run(['gh', 'pr', 'view', url, '--json', 'headRefOid,state,mergeable'])
    if code != 0:
        return {'status': 'error', 'error': err or 'gh pr view failed'}
    pr = json.loads(out)
    base = {'conflict': pr.get('mergeable') == 'CONFLICTING'}
    if pr.get('state') in ('MERGED', 'CLOSED'):
        return {**base, 'status': pr['state'].lower()}
    if not str(pr.get('headRefOid', '')).startswith(sha) and not sha.startswith(str(pr.get('headRefOid', ''))):
        return {**base, 'status': 'stale', 'head': pr.get('headRefOid')}
    # gh exits non-zero while checks fail (1) or are pending (8), but still prints the JSON
    code, out, err = run(['gh', 'pr', 'checks', url, '--json', 'name,bucket,link'])
    try:
        checks = json.loads(out) if out.strip() else []
    except ValueError:
        return {**base, 'status': 'error', 'error': err or 'unreadable gh pr checks output'}
    if not checks:
        return {**base, 'status': 'none'}
    failed = [{'name': c['name'], 'link': c.get('link', '')} for c in checks if c.get('bucket') in ('fail', 'cancel')]
    pending = [c['name'] for c in checks if c.get('bucket') == 'pending']
    status = 'red' if failed else 'pending' if pending else 'green'
    return {**base, 'status': status, 'failed': failed, 'pending': pending}


def gitlab(url, sha):
    code, out, err = run(['glab', 'mr', 'view', url, '-F', 'json'])
    if code != 0:
        return {'status': 'error', 'error': err or 'glab mr view failed'}
    mr = json.loads(out)
    base = {'conflict': bool(mr.get('has_conflicts'))}
    if mr.get('state') in ('merged', 'closed'):
        return {**base, 'status': mr['state']}
    head = str(mr.get('sha', ''))
    if not head.startswith(sha) and not sha.startswith(head):
        return {**base, 'status': 'stale', 'head': head}
    pipe = mr.get('head_pipeline') or {}
    if not pipe or str(pipe.get('sha', head)) != head:
        return {**base, 'status': 'none'}
    state = pipe.get('status')
    if state in ('success', 'skipped'):
        return {**base, 'status': 'green', 'failed': [], 'pending': []}
    if state in ('failed', 'canceled'):
        code, out, _ = run(['glab', 'api', f"projects/{mr['project_id']}/pipelines/{pipe['id']}/jobs?scope[]=failed&scope[]=canceled"])
        jobs = json.loads(out) if code == 0 and out.strip() else []
        failed = [{'name': j.get('name', ''), 'link': j.get('web_url', '')} for j in jobs if not j.get('allow_failure')]
        return {**base, 'status': 'red', 'failed': failed or [{'name': 'pipeline', 'link': pipe.get('web_url', '')}], 'pending': []}
    return {**base, 'status': 'pending', 'failed': [], 'pending': [f"pipeline {state}"]}


def main():
    args = sys.argv[1:]
    wait = 0.0
    if '--wait' in args:
        i = args.index('--wait')
        try:
            wait = float(args[i + 1])
        except (IndexError, ValueError):
            sys.stderr.write(__doc__)
            sys.exit(2)
        del args[i:i + 2]
    if len(args) != 3 or args[0] not in ('github', 'gitlab'):
        sys.stderr.write(__doc__)
        sys.exit(2)
    host, url, sha = args
    check = github if host == 'github' else gitlab
    deadline = time.time() + wait * 60
    while True:
        result = check(url, sha)
        # a run's checks can take a moment to register after a push, so `none` keeps waiting too
        if result['status'] not in ('pending', 'none') or time.time() + POLL_SECONDS > deadline:
            break
        time.sleep(POLL_SECONDS)
    print(json.dumps({'sha': sha, 'failed': [], 'pending': [], **result}))


if __name__ == '__main__':
    main()
