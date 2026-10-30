#!/usr/bin/env python3
"""The factory's link to Sentry: watch for errors worth fixing, fetch what a triager needs,
check that a fix held in production, and resolve the issue once it has.

    python3 sentry.py poll    <FACTORY> [--once] [--every <seconds>]
    python3 sentry.py list    <FACTORY>
    python3 sentry.py event   <FACTORY> <issue id>
    python3 sentry.py mark    <FACTORY> <issue id> <key>=<value> ...
    python3 sentry.py verify  <FACTORY> <issue id>
    python3 sentry.py resolve <FACTORY> <issue id> [--note <text>]

Settings come from the `sentry` block of `<FACTORY>/project.json`, which the orchestrator
writes from `factory/project.md`'s *Sentry* section:

    { "url": "https://sentry.example.com", "org": "eab", "projects": ["meridian-platform"],
      "environments": ["production"], "levels": ["error", "fatal"], "minEvents": 5,
      "minUsers": 1, "lookbackHours": 24, "ignore": ["ResizeObserver loop", "chrome-extension://"],
      "autonomy": "triage", "dailyCap": 3, "deployLagHours": 2, "verifyHours": 24, "resolve": true }

The token comes from `SENTRY_AUTH_TOKEN`, or from `~/.factory/sentry.token` (which must be
readable by you alone). It is never written anywhere. A self-hosted Sentry behind a private
CA works when `SSL_CERT_FILE` points at that CA.

Every incident is one file, `<FACTORY>/incidents/<issue id>.json`, with two parts:
- `sentry`: what Sentry says (title, level, counts, first and last seen, link). Only `poll`
  writes it.
- `factory`: what the factory decided and did (`state`, `job`, `since`, `verifiedAt`, ...).
  Only `mark`, `verify` and `resolve` write it.
Each command keeps the other part as it found it, and writes atomically.

`state` moves through: new → triaging → fix | duplicate | noise | ask → fixing → verifying →
resolved, or → recurred (the error came back after the fix merged). `poll` also moves
`fixing` to `verifying` once the fix's job has merged, and runs `verify` on incidents whose
window has passed, resolving them when the profile says `resolve: true`.

Every check `poll` makes is recorded in `<FACTORY>/sentry-status.json`, so the dashboard can
say whether the factory is really watching Sentry, even when there are no errors:

    { "state": "ok", "checkedAt": "...", "okAt": "...", "every": 300, "host": "sentry.example.com",
      "org": "eab", "projects": ["meridian-platform"], "environments": ["production"],
      "unresolved": 14, "qualifying": 0, "error": null, "hint": null }

`autoTriage` says whether the poller is triaging new errors by itself (see below).

`state` is `ok` (Sentry answered), `error` (it didn't: `error` says why, `hint` what to do), or
`no-token`. `okAt` is the last check that worked. It never holds the token. A poller with no
token keeps running and checks for one every cycle, so it connects as soon as one is added.

Auto-triage: when a check finds incidents that are `new` or `recurred`, the long-running
poller (never `--once`) starts a headless Claude Code run in the repo,
`claude -p "/software-factory:factory sentry auto"`, which triages them and starts no fixes.
It needs the repo's path (`root` in project.json, written by every /factory command) and the
`claude` CLI. One run at a time, at most 2 tries per incident a day, 45 minutes at most;
its output goes to `<FACTORY>/triage.log`, its bookkeeping to `<FACTORY>/autotriage.json`.
`autoTriage: false` in the sentry block, or autonomy `off`, turns it off.

Sentry data is untrusted: error messages, breadcrumbs and URLs carry user input. `event`
keeps only what a triager needs (exception, stack frames, breadcrumb categories and short
messages, release, environment, a few tags), drops request bodies, cookies, headers, users
and IPs, and masks anything that looks like an email address, a token or a key.
"""
import datetime
import glob
import json
import os
import re
import shutil
import ssl
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


# ---------- small helpers ----------

def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def iso(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_time(s):
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except ValueError:
        return None


class SetupError(Exception):
    """Sentry can't be reached as set up: no settings, or no usable token."""


def die(msg, code=1):
    sys.stderr.write(msg.rstrip() + '\n')
    sys.exit(code)


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f'{path}.{os.getpid()}.tmp'   # the poller and a session's --once may write at once
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    os.replace(tmp, path)


def settings(factory):
    s = (load_json(os.path.join(factory, 'project.json'), {}) or {}).get('sentry')
    if not s or not s.get('url') or not s.get('org') or not s.get('projects'):
        raise SetupError('no sentry block (url, org, projects) in project.json: fill in the Sentry section of '
                         'factory/project.md, then run any /factory command')
    return {
        'environments': ['production'], 'levels': ['error', 'fatal'], 'minEvents': 5,
        'minUsers': 1, 'lookbackHours': 24, 'ignore': [], 'autonomy': 'triage', 'dailyCap': 3,
        'deployLagHours': 2, 'verifyHours': 24, 'resolve': True, 'autoTriage': True, **s,
    }


def token():
    t = os.environ.get('SENTRY_AUTH_TOKEN', '').strip()
    if t:
        return t
    path = os.path.expanduser('~/.factory/sentry.token')
    try:
        st = os.stat(path)
    except OSError:
        raise SetupError('no Sentry token: set SENTRY_AUTH_TOKEN, or put it in ~/.factory/sentry.token (chmod 600)')
    if st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise SetupError('~/.factory/sentry.token is readable by others: chmod 600 it first')
    with open(path) as f:
        t = f.read().strip()
    if not t:
        raise SetupError('~/.factory/sentry.token is empty')
    return t


class Sentry:
    def __init__(self, cfg):
        self.base = cfg['url'].rstrip('/')
        self.org = cfg['org']
        self.tok = token()
        self.ctx = ssl.create_default_context()

    def call(self, method, path, params=None, body=None):
        url = self.base + path
        if params:
            url += '?' + urllib.parse.urlencode(params, doseq=True)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            'Authorization': 'Bearer ' + self.tok, 'Content-Type': 'application/json',
            'Accept': 'application/json'})
        with urllib.request.urlopen(req, context=self.ctx, timeout=60) as res:
            text = res.read().decode() or 'null'
            return json.loads(text)

    def first(self, method, paths, **kw):
        """Try each path in turn (newer org-scoped endpoints first, then the older ones that
        self-hosted versions still serve), and return the first answer that isn't a 404."""
        err = None
        for p in paths:
            try:
                return self.call(method, p, **kw)
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                err = e
        raise err

    def project_ids(self, slugs):
        ids = []
        for slug in slugs:
            if str(slug).isdigit():
                ids.append(str(slug))
            else:
                ids.append(str(self.call('GET', f'/api/0/projects/{self.org}/{slug}/')['id']))
        return ids

    def issues(self, cfg):
        params = {'project': self.project_ids(cfg['projects']), 'query': 'is:unresolved',
                  'statsPeriod': f"{int(cfg['lookbackHours'])}h", 'sort': 'freq', 'limit': 100}
        if cfg['environments']:
            params['environment'] = cfg['environments']
        return self.call('GET', f'/api/0/organizations/{self.org}/issues/', params=params) or []

    def issue(self, iid):
        return self.first('GET', [f'/api/0/organizations/{self.org}/issues/{iid}/', f'/api/0/issues/{iid}/'])

    def latest_event(self, iid):
        return self.first('GET', [f'/api/0/organizations/{self.org}/issues/{iid}/events/latest/',
                                  f'/api/0/issues/{iid}/events/latest/'])

    def events_since(self, iid, since, environments):
        params = {'start': iso(since), 'end': iso(utcnow()), 'limit': 1}
        if environments:
            params['environment'] = environments
        try:
            events = self.first('GET', [f'/api/0/organizations/{self.org}/issues/{iid}/events/',
                                        f'/api/0/issues/{iid}/events/'], params=params)
            return events or []
        except urllib.error.HTTPError:
            # an older Sentry without time filters on events: fall back to the issue's lastSeen
            last = parse_time(self.issue(iid).get('lastSeen'))
            return [{'dateCreated': iso(last)}] if last and last > since else []

    def resolve(self, iid):
        return self.first('PUT', [f'/api/0/organizations/{self.org}/issues/{iid}/', f'/api/0/issues/{iid}/'],
                          body={'status': 'resolved'})

    def comment(self, iid, text):
        return self.first('POST', [f'/api/0/organizations/{self.org}/issues/{iid}/comments/',
                                   f'/api/0/issues/{iid}/comments/'], body={'text': text})


# ---------- incident files ----------

def inc_path(factory, iid):
    return os.path.join(factory, 'incidents', f'{iid}.json')


def read_inc(factory, iid):
    return load_json(inc_path(factory, iid), {}) or {}


def update_inc(factory, iid, sentry=None, factory_part=None):
    """Rewrite one incident file, changing only the part this command owns."""
    path = inc_path(factory, iid)
    cur = load_json(path, {}) or {}
    cur['id'] = str(iid)
    if sentry is not None:
        cur['sentry'] = sentry
    if factory_part is not None:
        cur['factory'] = {**(cur.get('factory') or {}), **factory_part, 'updated': iso(utcnow())}
    cur.setdefault('factory', {'state': 'new', 'updated': iso(utcnow())})
    write_json(path, cur)
    return cur


SECRETISH = [
    (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), '<email>'),
    (re.compile(r'(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+'), 'Bearer <redacted>'),
    (re.compile(r'(?i)\b(token|apikey|api_key|secret|password|passwd|authorization)\b(["\']?\s*[:=]\s*["\']?)[^\s"\'&,;]+'), r'\1\2<redacted>'),
    (re.compile(r'\b(sk|pk|rk|ghp|gho|glpat|xox[abprs])[-_][A-Za-z0-9_-]{8,}'), '<redacted>'),
    (re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}'), '<jwt>'),
    (re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}\b'), '<ip>'),
]


def scrub(value, limit=500):
    s = str(value if value is not None else '')
    for rx, rep in SECRETISH:
        s = rx.sub(rep, s)
    return s if len(s) <= limit else s[:limit] + '…'


def sentry_summary(issue):
    meta = issue.get('metadata') or {}
    return {
        'shortId': issue.get('shortId'), 'title': scrub(issue.get('title'), 200),
        'culprit': scrub(issue.get('culprit'), 200), 'type': scrub(meta.get('type'), 120),
        'level': issue.get('level'), 'status': issue.get('status'), 'substatus': issue.get('substatus'),
        'events': int(issue.get('count') or 0), 'users': int(issue.get('userCount') or 0),
        'firstSeen': issue.get('firstSeen'), 'lastSeen': issue.get('lastSeen'),
        'link': issue.get('permalink'), 'project': (issue.get('project') or {}).get('slug'),
        'unhandled': issue.get('isUnhandled'),
    }


def qualifies(issue, cfg):
    if cfg['levels'] and issue.get('level') not in cfg['levels']:
        return False
    if int(issue.get('count') or 0) < int(cfg['minEvents']) or int(issue.get('userCount') or 0) < int(cfg['minUsers']):
        return False
    text = ' '.join(str(x) for x in (issue.get('title'), issue.get('culprit'), (issue.get('metadata') or {}).get('value')))
    return not any(p and p in text for p in cfg['ignore'])


# ---------- commands ----------

def cmd_poll_once(factory, cfg, api, counts=None):
    found = []
    issues = api.issues(cfg)
    if counts is not None:
        counts['unresolved'] = len(issues)
        counts['qualifying'] = sum(1 for i in issues if qualifies(i, cfg))
    for issue in issues:
        if not qualifies(issue, cfg):
            continue
        iid = str(issue['id'])
        had = os.path.exists(inc_path(factory, iid))
        cur = update_inc(factory, iid, sentry=sentry_summary(issue))
        state = (cur.get('factory') or {}).get('state')
        if not had:
            found.append(iid)
        elif state in ('resolved', 'verified') or (state == 'noise' and issue.get('substatus') == 'escalating'):
            # unresolved again after the factory resolved it, or dismissed noise that is now
            # escalating: triage it again
            update_inc(factory, iid, factory_part={'state': 'new', 'reopened': iso(utcnow())})
            found.append(iid)
    # move incidents along: a merged fix starts its verification window, and a window that has
    # passed gets its verdict
    for path in glob.glob(os.path.join(factory, 'incidents', '*.json')):
        inc = load_json(path, {}) or {}
        f = inc.get('factory') or {}
        iid = inc.get('id')
        if f.get('state') == 'fixing' and f.get('job') and job_merged(factory, f['job']):
            since = utcnow() + datetime.timedelta(hours=float(cfg['deployLagHours']))
            update_inc(factory, iid, factory_part={'state': 'verifying', 'since': iso(since),
                                                    'until': iso(since + datetime.timedelta(hours=float(cfg['verifyHours'])))})
        elif f.get('state') == 'verifying' and parse_time(f.get('until')) and parse_time(f['until']) <= utcnow():
            cmd_verify(factory, cfg, api, iid, quiet=True)
    return found


# ---------- the poller's status, for the dashboard ----------

def explain(e, cfg):
    """(error, hint) for a failed check, in words a person can act on. Never the token."""
    host = urllib.parse.urlsplit(cfg.get('url') or '').netloc or 'Sentry'
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 401:
            return f'{host} rejected the token (401)', 'The token is wrong, revoked or expired: make a new one and replace it.'
        if e.code == 403:
            return f'{host} refused access (403)', 'The token needs read access to issues and events (and write access to issues to resolve them).'
        if e.code == 404:
            return f'{host} has no such org or project (404)', 'Check the org and projects in the Sentry section of factory/project.md.'
        if e.code == 429:
            return f'{host} is rate limiting the factory (429)', 'It retries on the next check.'
        return f'{host} answered {e.code} {e.reason}', 'It retries on the next check.'
    if isinstance(e, urllib.error.URLError):
        reason = e.reason
        if isinstance(reason, ssl.SSLCertVerificationError) or 'CERTIFICATE_VERIFY_FAILED' in str(reason):
            return f"can't verify {host}'s certificate", 'For a self-hosted Sentry behind a private CA, set SSL_CERT_FILE to that CA for the poller.'
        return f"can't reach {host}: {str(reason)[:160]}", 'Check the URL in factory/project.md and this machine\'s network. It retries on the next check.'
    if isinstance(e, ValueError):
        return f'{host} sent something that is not Sentry\'s API', 'Check the URL in the Sentry section of factory/project.md.'
    return f'the check failed: {type(e).__name__}: {str(e)[:160]}', 'It retries on the next check; sentry.log has the details.'


def write_status(factory, cfg, every, **fields):
    path = os.path.join(factory, 'sentry-status.json')
    prev = load_json(path, {}) or {}
    now = iso(utcnow())
    ok = fields.get('state', 'ok') == 'ok'
    status = {
        'state': fields.get('state', 'ok'), 'checkedAt': now, 'okAt': now if ok else prev.get('okAt'),
        'every': int(every), 'host': urllib.parse.urlsplit(cfg.get('url') or '').netloc or None,
        'org': cfg.get('org'), 'projects': cfg.get('projects') or [], 'environments': cfg.get('environments') or [],
        # what the last check that worked saw
        'unresolved': fields.get('unresolved') if ok else prev.get('unresolved'),
        'qualifying': fields.get('qualifying') if ok else prev.get('qualifying'),
        'error': fields.get('error'), 'hint': fields.get('hint'),
        'autoTriage': fields.get('autoTriage', prev.get('autoTriage')),
    }
    write_json(path, status)


# ---------- auto-triage: a headless Claude Code run triages new errors ----------

TRIAGE_TOOLS = ['Agent', 'Read', 'Grep', 'Glob', 'Write', 'Bash(python3:*)', 'Bash(git:*)']
TRIAGE_TIMEOUT = 45 * 60
TRIES_PER_DAY = 2
_triage_proc = None   # the run this poller started, while it runs


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def auto_triage(factory, cfg):
    """Start a headless triage run for new or recurred incidents when one is due, and say what
    auto-triage is doing, for sentry-status.json."""
    global _triage_proc
    if not cfg.get('autoTriage', True) or cfg.get('autonomy') == 'off':
        return {'state': 'off'}
    path = os.path.join(factory, 'autotriage.json')
    book = load_json(path, {}) or {}
    now = utcnow()
    # the run in flight: still going, overdue, or finished
    if book.get('pid') and not book.get('finishedAt'):
        proc = _triage_proc if _triage_proc and _triage_proc.pid == book['pid'] else None
        code = proc.poll() if proc else (None if pid_alive(book['pid']) else 'unknown')
        started = parse_time(book.get('startedAt')) or now
        if code is None and (now - started).total_seconds() > TRIAGE_TIMEOUT:
            try:
                os.killpg(book['pid'], 15)
            except OSError:
                pass
            code = 'timed out'
        if code is None:
            return {'state': 'running', 'startedAt': book.get('startedAt'), 'ids': book.get('ids') or []}
        book.update(finishedAt=iso(now), exit=code)
        _triage_proc = None
        write_json(path, book)
    last = {k: book.get(k) for k in ('startedAt', 'finishedAt', 'exit', 'ids')} if book.get('startedAt') else {}
    pending = []
    for p in glob.glob(os.path.join(factory, 'incidents', '*.json')):
        inc = load_json(p, {}) or {}
        if ((inc.get('factory') or {}).get('state') or 'new') in ('new', 'recurred') and inc.get('id'):
            pending.append(str(inc['id']))
    tries = {i: [t for t in (book.get('tries') or {}).get(i, []) if parse_time(t) and (now - parse_time(t)).total_seconds() < 86400]
             for i in pending}
    due = sorted(i for i in pending if len(tries[i]) < TRIES_PER_DAY)
    if not pending:
        return {'state': 'idle', **last}
    if not due:
        return {'state': 'gave-up', 'reason': f'tried {TRIES_PER_DAY} times today without a verdict; see triage.log',
                'ids': sorted(pending), **last}
    root = (load_json(os.path.join(factory, 'project.json'), {}) or {}).get('root')
    claude = shutil.which('claude')
    if not root or not os.path.isdir(root):
        return {'state': 'unavailable', 'reason': "the poller doesn't know where the repo is yet: run any /factory command in it once", **last}
    if not claude:
        return {'state': 'unavailable', 'reason': "the claude command isn't on the poller's PATH", **last}
    cmd = [claude, '-p', '/software-factory:factory sentry auto', '--permission-mode', 'acceptEdits',
           '--allowedTools', *TRIAGE_TOOLS, '--add-dir', factory]
    log = open(os.path.join(factory, 'triage.log'), 'a')
    log.write(f'\n== {iso(now)} auto-triage of {", ".join(due)}\n')
    log.flush()
    try:
        _triage_proc = subprocess.Popen(cmd, cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    except OSError as e:
        return {'state': 'unavailable', 'reason': f"couldn't start claude: {e}", **last}
    finally:
        log.close()
    for i in due:
        tries[i].append(iso(now))
    write_json(path, {'pid': _triage_proc.pid, 'startedAt': iso(now), 'ids': due, 'tries': {**(book.get('tries') or {}), **tries}})
    print(f'{iso(now)} auto-triage started for {", ".join(due)} (pid {_triage_proc.pid})', flush=True)
    return {'state': 'running', 'startedAt': iso(now), 'ids': due}


def poll_loop(factory, args):
    """Check Sentry now, and (without --once) every --every seconds, recording each check."""
    every = 300.0
    if '--every' in args:
        every = max(60.0, float(args[args.index('--every') + 1]))
    once = '--once' in args
    api, api_key = None, None
    while True:
        failed = False
        try:
            cfg = settings(factory)   # read every cycle, so a fixed profile is picked up
        except SetupError as e:
            die(str(e))               # Sentry isn't set up here (any more): nothing to watch
        try:
            key = (cfg['url'], cfg['org'])
            if api is None or api_key != key:
                api, api_key = Sentry(cfg), key
            counts = {}
            found = cmd_poll_once(factory, cfg, api, counts)
            # only the long-running poller triages; a session's --once leaves it to that session
            extra = {} if once else {'autoTriage': auto_triage(factory, cfg)}
            write_status(factory, cfg, every, state='ok', **counts, **extra)
            if found:
                print(f'{iso(utcnow())} new or regressed: {", ".join(found)}', flush=True)
        except SetupError as e:
            api, failed = None, True
            write_status(factory, cfg, every, state='no-token', error=str(e),
                         hint='The poller checks again every few minutes and connects once a token is there.')
            print(f'{iso(utcnow())} {e}', flush=True)
        except Exception as e:   # the poller outlives any one bad check, and says why it failed
            failed = True
            error, hint = explain(e, cfg)
            write_status(factory, cfg, every, state='error', error=error, hint=hint)
            print(f'{iso(utcnow())} could not check Sentry: {error}: {e!r}', flush=True)
        if once:
            sys.exit(1 if failed else 0)
        time.sleep(every)


def job_merged(factory, job_id):
    for path in glob.glob(os.path.join(factory, 'board', '*.json')):
        for job in (load_json(path, {}) or {}).get('jobs') or []:
            if job.get('id') == job_id:
                return job.get('stage') == 'merged'
    return False


def cmd_verify(factory, cfg, api, iid, quiet=False):
    """Has the error come back since the fix reached production? Prints the verdict as JSON."""
    inc = read_inc(factory, iid)
    f = inc.get('factory') or {}
    since = parse_time(f.get('since'))
    if not since:
        die(f'incident {iid} has no verification window yet (its fix has not merged)')
    now = utcnow()
    # before the window opens (the fix may not be deployed yet), there is nothing to ask Sentry
    events = api.events_since(iid, since, cfg['environments']) if since <= now else []
    if events:
        out = {'id': iid, 'verdict': 'recurred', 'lastEvent': events[0].get('dateCreated')}
        update_inc(factory, iid, factory_part={'state': 'recurred', 'recurredAt': out['lastEvent']})
    elif parse_time(f.get('until')) and parse_time(f['until']) > now:
        out = {'id': iid, 'verdict': 'waiting', 'until': f.get('until')}
    else:
        out = {'id': iid, 'verdict': 'held', 'quietSince': f.get('since')}
        update_inc(factory, iid, factory_part={'state': 'verified', 'verifiedAt': iso(now)})
        if cfg.get('resolve'):
            cmd_resolve(factory, cfg, api, iid, None, quiet=True)
            out['resolved'] = True
    if not quiet:
        print(json.dumps(out))
    return out


def cmd_resolve(factory, cfg, api, iid, note, quiet=False):
    inc = read_inc(factory, iid)
    f = inc.get('factory') or {}
    text = note or ('Resolved by the software factory: no new events in '
                    f"{', '.join(cfg['environments']) or 'any environment'} for {cfg['verifyHours']}h "
                    f"after the fix reached production{(' (' + f['pr'] + ')') if f.get('pr') else ''}"
                    f"{(', job ' + f['job']) if f.get('job') else ''}. "
                    'If it happens again, Sentry marks it regressed and the factory picks it up.')
    api.resolve(iid)
    try:
        api.comment(iid, text)
    except urllib.error.HTTPError:
        pass   # the resolve is what matters; a comment is a courtesy
    update_inc(factory, iid, factory_part={'state': 'resolved', 'resolvedAt': iso(utcnow())})
    if not quiet:
        print(json.dumps({'id': iid, 'resolved': True}))


def cmd_event(factory, api, iid):
    """Save a scrubbed copy of the issue's latest event for the triager, and print its path."""
    ev = api.latest_event(iid)
    keep = {'id': ev.get('eventID') or ev.get('id'), 'dateCreated': ev.get('dateCreated'),
            'release': (ev.get('release') or {}).get('version') if isinstance(ev.get('release'), dict) else ev.get('release'),
            'environment': None, 'platform': ev.get('platform'), 'title': scrub(ev.get('title'), 300),
            'exceptions': [], 'breadcrumbs': [], 'tags': {}}
    for t in ev.get('tags') or []:
        k, v = t.get('key'), t.get('value')
        if k == 'environment':
            keep['environment'] = v
        if k in ('environment', 'release', 'browser', 'browser.name', 'os', 'os.name', 'runtime',
                 'runtime.name', 'transaction', 'handled', 'level', 'mechanism', 'server_name'):
            keep['tags'][k] = scrub(v, 200)
        if k == 'url':
            keep['tags']['url_path'] = scrub(urllib.parse.urlparse(str(v)).path, 200)
    for entry in ev.get('entries') or []:
        if entry.get('type') == 'exception':
            for exc in (entry.get('data') or {}).get('values') or []:
                frames = ((exc.get('stacktrace') or {}).get('frames') or [])[-30:]
                keep['exceptions'].append({
                    'type': scrub(exc.get('type'), 200), 'value': scrub(exc.get('value'), 500),
                    'mechanism': (exc.get('mechanism') or {}).get('type'),
                    'frames': [{'file': fr.get('filename') or fr.get('absPath'), 'function': fr.get('function'),
                                'line': fr.get('lineNo'), 'column': fr.get('colNo'), 'inApp': fr.get('inApp'),
                                'module': fr.get('module'),
                                'context': [[n, scrub(code, 300)] for n, code in (fr.get('context') or [])]}
                               for fr in frames]})
        elif entry.get('type') == 'breadcrumbs':
            for b in ((entry.get('data') or {}).get('values') or [])[-25:]:
                keep['breadcrumbs'].append({'time': b.get('timestamp'), 'category': b.get('category'),
                                            'level': b.get('level'), 'message': scrub(b.get('message'), 300)})
    path = os.path.join(factory, 'incidents', str(iid), 'event.json')
    write_json(path, keep)
    print(path)


def cmd_list(factory):
    """Print every incident and what the factory has done about it, plus today's fix count."""
    rows, today = [], utcnow().date().isoformat()
    for path in sorted(glob.glob(os.path.join(factory, 'incidents', '*.json'))):
        inc = load_json(path, {}) or {}
        s, f = inc.get('sentry') or {}, inc.get('factory') or {}
        rows.append({'id': inc.get('id'), 'shortId': s.get('shortId'), 'state': f.get('state'),
                     'title': s.get('title'), 'level': s.get('level'), 'events': s.get('events'),
                     'users': s.get('users'), 'lastSeen': s.get('lastSeen'), 'job': f.get('job'),
                     'link': s.get('link')})
    started = sum(1 for path in glob.glob(os.path.join(factory, 'incidents', '*.json'))
                  if str(((load_json(path, {}) or {}).get('factory') or {}).get('fixStarted', '')).startswith(today))
    print(json.dumps({'incidents': rows, 'fixesStartedToday': started}, indent=2))


def cmd_mark(factory, iid, pairs):
    part = {}
    for p in pairs:
        if '=' not in p:
            die(f'expected key=value, got {p!r}')
        k, v = p.split('=', 1)
        part[k] = None if v == '' else v
    if part.get('state') == 'fixing' and 'fixStarted' not in part:
        part['fixStarted'] = iso(utcnow())
    print(json.dumps(update_inc(factory, iid, factory_part=part)))


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        die(__doc__, 2)
    cmd, factory = args[0], os.path.abspath(os.path.expanduser(args[1]))
    if cmd == 'list':
        return cmd_list(factory)
    if cmd == 'mark':
        if len(args) < 4:
            die(__doc__, 2)
        return cmd_mark(factory, args[2], args[3:])
    if cmd == 'poll':
        return poll_loop(factory, args)
    try:
        cfg = settings(factory)
        api = Sentry(cfg)
    except SetupError as e:
        die(str(e))
    if len(args) < 3:
        die(__doc__, 2)
    iid = args[2]
    if cmd == 'event':
        return cmd_event(factory, api, iid)
    if cmd == 'verify':
        return cmd_verify(factory, cfg, api, iid)
    if cmd == 'resolve':
        note = args[args.index('--note') + 1] if '--note' in args else None
        return cmd_resolve(factory, cfg, api, iid, note)
    die(__doc__, 2)


if __name__ == '__main__':
    main()
