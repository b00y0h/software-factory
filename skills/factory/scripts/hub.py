#!/usr/bin/env python3
"""The factory hub: one dashboard for every repo on this machine.

    python3 hub.py <factory home> --port <port>

Every repo the factory runs in keeps its state in its own folder, `<home>/<repo>/` (normally
`~/.factory/<repo>/`). The hub serves all of them from one localhost port, so one page shows
every project and switches between them:

    /dashboard.html          the dashboard (<home>/dashboard.html, copied there by dashboard.sh)
    /api/projects            a summary of every project: what is running, what needs a human,
                             CI that is red, Sentry errors that are open, and when it last moved
    /p/<repo>/<path>         one project's state, the same paths the dashboard reads from a
                             state folder (project.json, board/, jobs/<id>/spec.md, ...)
    /.factory-id             "factory-hub <home>", so dashboard.sh can tell this hub apart

It is not a file server. <home> also holds things that must never leave it (sentry.token, pid
files, logs), so only the paths the dashboard reads are served, read-only, by an allowlist:
the project's project.json and backlog.md, the board/ and incidents/ listings and their .json
files, and the markdown under jobs/, runs/ and incidents/<id>/. Anything else, any dotfile,
and anything that resolves outside its project folder (a symlink) is a 404. It listens on
127.0.0.1 only and answers only requests addressed to localhost, so a web page on another
site can't read it through DNS rebinding. Python's standard library only.
"""
import datetime
import glob
import http.server
import json
import os
import re
import socketserver
import sys
import urllib.parse

# dashboard.sh restarts a hub that reports a lower version than the script it has.
HUB_VERSION = 3

SEG = r'[A-Za-z0-9_][A-Za-z0-9._-]*'
# The paths inside a project folder the dashboard may read. Nothing else is served.
ALLOWED = [re.compile('^' + p + '$') for p in (
    r'project\.json',
    r'sentry-status\.json',
    r'backlog\.md',
    r'board/',
    rf'board/{SEG}\.json',
    r'incidents/',
    rf'incidents/{SEG}\.json',
    rf'incidents/{SEG}/triage\.md',
    rf'jobs/{SEG}/{SEG}\.md',
    rf'jobs/{SEG}/round-\d+/{SEG}\.md',
    rf'jobs/{SEG}/ci/{SEG}\.md',
    rf'runs/{SEG}/{SEG}\.md',
    rf'runs/{SEG}/ci/{SEG}\.md',
)]
LISTINGS = {'board/', 'incidents/'}
TYPES = {'.json': 'application/json; charset=utf-8', '.md': 'text/markdown; charset=utf-8',
         '.html': 'text/html; charset=utf-8'}
LOCAL_HOSTS = {'localhost', '127.0.0.1', '[::1]'}

# The same stage names the dashboard and SKILL.md use.
ACTIVE = {'spec', 'build', 'review', 'approval'}
FINAL = {'merged', 'closed'}
CI_ALERT = {'fixing', 'blocked', 'error'}
INC_OPEN = {'new', 'triaging', 'fix', 'ask', 'recurred', 'fixing', 'verifying'}
INC_ALERT = {'new', 'fix', 'ask', 'recurred'}


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None   # missing, or mid-write: the next poll reads it


def is_project(path):
    return os.path.isfile(os.path.join(path, 'project.json')) or os.path.isdir(os.path.join(path, 'board'))


def projects(home):
    out = []
    for name in sorted(os.listdir(home)):
        path = os.path.join(home, name)
        if name.startswith('.') or not re.fullmatch(SEG, name) or not os.path.isdir(path):
            continue
        if is_project(path):
            out.append(name)
    return out


def summarize(home, repo):
    """What one project is doing, in the shape the dashboard's overview draws."""
    folder = os.path.join(home, repo)
    project = read_json(os.path.join(folder, 'project.json')) or {}
    runs, jobs, floors, updated, plugin = [], [], set(), '', ''
    docs = [read_json(p) for p in sorted(glob.glob(os.path.join(folder, 'board', '*.json')))]
    docs.append(read_json(os.path.join(folder, 'board.json')))   # a state folder from before 0.3
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        for r in doc.get('runs') or []:
            runs.append({**r, 'floor': r.get('floor') or doc.get('floor')})
        for j in doc.get('jobs') or []:
            jobs.append({**j, 'floor': j.get('floor') or doc.get('floor')})
        updated = max(updated, str(doc.get('updated') or ''))
        plugin = max(plugin, str(doc.get('plugin') or ''), key=version_key)

    shipped_runs = {r.get('id') for r in runs if r.get('stage') in FINAL}
    open_runs = [r for r in runs if r.get('id') not in shipped_runs]
    open_jobs = [j for j in jobs if (j.get('run') not in shipped_runs if j.get('run') else j.get('stage') not in FINAL)]
    shipped = len(shipped_runs) + sum(1 for j in jobs if not j.get('run') and j.get('stage') in FINAL)

    human = [{'kind': 'job', 'id': j.get('id'), 'title': j.get('title') or j.get('id'), 'gate': j.get('gate'),
              'run': j.get('run'), 'unit': j.get('unit')}
             for j in open_jobs if j.get('stage') == 'needs-human']
    human += [{'kind': 'run', 'id': r.get('id'), 'title': r.get('title') or r.get('id'), 'gate': r.get('gate'),
               'reason': r.get('reason')}
              for r in open_runs if r.get('stage') == 'paused']

    pushed = [x for x in open_runs + open_jobs if isinstance(x.get('ci'), dict) and x.get('stage') in ('pushed', 'merging')]
    ci_red = [{'id': x.get('id'), 'title': x.get('title') or x.get('id'), 'status': x['ci'].get('status')}
              for x in pushed if x['ci'].get('status') in CI_ALERT]
    ci_pending = sum(1 for x in pushed if x['ci'].get('status') == 'pending')

    incidents = [read_json(p) for p in glob.glob(os.path.join(folder, 'incidents', '*.json'))]
    status = read_json(os.path.join(folder, 'sentry-status.json'))
    auto = (status or {}).get('autoTriage') if isinstance(status, dict) else None
    # while the poller's headless run is triaging, new errors (in it, or queued for the next one)
    # don't need a person
    auto_running = (auto or {}).get('state') == 'running'
    inc_state = [('triaging' if auto_running and st in ('new', 'recurred') else st)
                 for i in incidents if isinstance(i, dict)
                 for st in [str((i.get('factory') or {}).get('state') or 'new')]]

    running = [j for j in open_jobs if j.get('stage') in ACTIVE]
    for x in running + [r for r in open_runs if r.get('stage') in ('planning', 'running', 'paused')]:
        if x.get('floor'):
            floors.add(x['floor'])

    backlog = 0
    try:
        with open(os.path.join(folder, 'backlog.md'), encoding='utf-8') as f:
            text = re.sub(r'<!--[\s\S]*?-->', '', f.read())
        backlog = len(re.findall(r'^\s*[-*]\s+\[ \]\s+\S', text, re.M))
    except OSError:
        pass

    sentry = sentry_health(project, status)
    alert = bool(human or ci_red or any(s in INC_ALERT for s in inc_state) or (sentry and sentry['state'] in SENTRY_ALERT))
    busy = bool(running or ci_pending or auto_running or any(r.get('stage') in ('planning', 'running') for r in open_runs))
    return {
        'id': repo,
        'name': project.get('name') or repo,
        'host': project.get('host'),
        'merge': project.get('merge'),
        'status': 'needs-you' if alert else 'running' if busy else 'idle',
        'updated': updated or None,
        'plugin': plugin or None,
        'sessions': len(floors),
        'running': [{'id': j.get('id'), 'title': j.get('title') or j.get('id'), 'stage': j.get('stage'),
                     'run': j.get('run'), 'unit': j.get('unit'), 'bay': bool(j.get('bay'))} for j in running],
        'runs': [{'id': r.get('id'), 'title': r.get('title') or r.get('id'), 'stage': r.get('stage'),
                  'units': len([u for u in r.get('units') or [] if u.get('status') != 'skipped']),
                  'done': len([u for u in r.get('units') or [] if u.get('status') == 'done'])} for r in open_runs],
        'human': human,
        'ci': {'red': ci_red, 'pending': ci_pending},
        'sentry': sentry,
        'incidents': {'open': sum(1 for s in inc_state if s in INC_OPEN), 'alert': sum(1 for s in inc_state if s in INC_ALERT)},
        'backlog': backlog,
        'shipped': shipped,
    }


SENTRY_ALERT = {'error', 'no-token', 'stale'}


def sentry_health(project, status):
    """Whether the factory is really watching Sentry for this repo, from the poller's last check
    (sentry-status.json, written by sentry.py). None when the repo doesn't watch Sentry.

    `waiting` (set up, never checked yet), `ok`, `error`, `no-token`, or `stale`: no check for
    more than two cycles, so the poller has most likely stopped. The dashboard uses the same rule."""
    cfg = project.get('sentry') if isinstance(project, dict) else None
    if not isinstance(cfg, dict) or not cfg.get('url') or cfg.get('autonomy') == 'off':
        return None
    if not isinstance(status, dict) or not status.get('checkedAt'):
        return {'state': 'waiting'}
    keep = ('state', 'checkedAt', 'okAt', 'every', 'error', 'hint', 'unresolved', 'qualifying', 'host', 'autoTriage')
    out = {k: status.get(k) for k in keep}
    try:
        checked = datetime.datetime.fromisoformat(str(status['checkedAt']).replace('Z', '+00:00'))
        age = (datetime.datetime.now(datetime.timezone.utc) - checked).total_seconds()
        if age > 2 * float(status.get('every') or 300) + 120:
            out['state'] = 'stale'
    except (TypeError, ValueError):
        out['state'] = 'stale'
    return out


def version_key(v):
    return [int(p) if p.isdigit() else 0 for p in str(v or '').split('.')]


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'factory-hub'
    sys_version = ''

    def log_message(self, *args):
        pass   # quiet: the dashboard polls every few seconds

    def send(self, code, body=b'', ctype='text/plain; charset=utf-8', extra=None):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy',
                         "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                         "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        host = (self.headers.get('Host') or '').lower()
        host = host.rsplit(':', 1)[0] if not host.endswith(']') else host
        if host not in LOCAL_HOSTS:
            return self.send(403, 'the factory hub only answers on localhost\n')
        home = self.server.home
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if path in ('/', ''):
            return self.send(302, '', extra={'Location': '/dashboard.html'})
        if path == '/.factory-id':
            return self.send(200, f'factory-hub {home}\n')
        if path == '/api/hub':
            return self.send(200, json.dumps({'hub': HUB_VERSION}), TYPES['.json'])
        if path == '/api/projects':
            body = {'updated': now(), 'projects': [summarize(home, p) for p in projects(home)]}
            return self.send(200, json.dumps(body), TYPES['.json'])
        if path == '/dashboard.html':
            return self.file(os.path.join(home, 'dashboard.html'), home)
        m = re.fullmatch(rf'/p/({SEG})/(.+)', path)
        if m and '..' not in path:
            repo, rest = m.groups()
            folder = os.path.join(home, repo)
            if os.path.isdir(folder) and is_project(folder) and any(a.match(rest) for a in ALLOWED):
                if rest in LISTINGS:
                    return self.listing(os.path.join(folder, rest), folder)
                return self.file(os.path.join(folder, rest), folder)
        return self.send(404, 'not found\n')

    def file(self, path, root):
        real, root = os.path.realpath(path), os.path.realpath(root)
        if not real.startswith(root + os.sep) or not os.path.isfile(real):
            return self.send(404, 'not found\n')
        try:
            with open(real, 'rb') as f:
                body = f.read()
        except OSError:
            return self.send(404, 'not found\n')
        return self.send(200, body, TYPES.get(os.path.splitext(real)[1], 'application/octet-stream'))

    def listing(self, path, root):
        """The same shape as http.server's listing, which is what the dashboard parses."""
        real, root = os.path.realpath(path), os.path.realpath(root)
        if not real.startswith(root + os.sep) or not os.path.isdir(real):
            return self.send(404, 'not found\n')
        names = sorted(n for n in os.listdir(real) if n.endswith('.json') and re.fullmatch(SEG, n))
        links = ''.join(f'<li><a href="{urllib.parse.quote(n)}">{n}</a></li>\n' for n in names)
        return self.send(200, f'<!doctype html>\n<ul>\n{links}</ul>\n', TYPES['.html'])


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__.strip())
        return 0 if argv else 2
    home = os.path.abspath(os.path.expanduser(argv[0]))
    port = 8765
    if '--port' in argv:
        port = int(argv[argv.index('--port') + 1])
    if not os.path.isdir(home):
        print(f'no factory home at {home}', file=sys.stderr)
        return 1
    server = Server(('127.0.0.1', port), Handler)
    server.home = home
    server.serve_forever()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
