#!/usr/bin/env python3
"""Which changed paths are UI, or generated files, by the repo's profile.

    git -C <WORKTREE> diff --name-only <DIFF_BASE>..HEAD | python3 touches.py ui <FACTORY>/project.json
    ... | python3 touches.py generated <FACTORY>/project.json
    ... | python3 touches.py code <FACTORY>/project.json

Prints the paths that match, one per line, and exits 0 if any did, 1 if none did.

- ui: the profile's `ui` patterns (project.json), or the built-in UI list when it has none.
  Tests, stories and generated files never count as UI.
- generated: the built-in generated list plus the profile's `generated` patterns.
- code: everything that can change behavior or its tests, so the test-quality reviewer runs.
  Docs, plain text, images and generated files never count.

Globs match like the dashboard's: `*` stays inside one folder, `**/` is any number of
folders (including none), and `**` is anything.
"""
import json
import re
import sys

BUILT_IN_UI = ['**/*.tsx', '**/*.jsx', '**/*.vue', '**/*.svelte', '**/*.astro', '**/*.html',
               '**/*.css', '**/*.scss', '**/*.sass', '**/*.less']
NEVER_UI = ['**/*.test.*', '**/*.spec.*', '**/__tests__/**', '**/tests/**', '**/test/**',
            '**/e2e/**', '**/*.stories.*']
BUILT_IN_GENERATED = ['**/pnpm-lock.yaml', '**/package-lock.json', '**/yarn.lock', '**/bun.lockb',
                      '**/payload-types.ts', '**/importMap.js', '**/*.generated.*',
                      '**/__generated__/**', '**/dist/**']
NOT_CODE = ['**/*.md', '**/*.mdx', '**/*.txt', '**/*.rst', '**/*.adoc', 'docs/**', '**/LICENSE*',
            '**/CHANGELOG*', '**/*.png', '**/*.jpg', '**/*.jpeg', '**/*.gif', '**/*.svg', '**/*.webp',
            '**/*.ico', '**/.gitignore', 'factory/**']


def glob_to_re(glob):
    # a profile line may carry its regenerate command after ": "
    g = re.split(r':\s', str(glob))[0].strip().strip('`')
    out, i = '', 0
    while i < len(g):
        c = g[i]
        if g.startswith('**/', i):
            out += '(?:.*/)?'
            i += 3
        elif g.startswith('**', i):
            out += '.*'
            i += 2
        elif c == '*':
            out += '[^/]*'
            i += 1
        elif c == '?':
            out += '[^/]'
            i += 1
        else:
            out += re.escape(c)
            i += 1
    return re.compile('^' + out + '$')


def matcher(globs):
    res = [glob_to_re(g) for g in globs]
    return lambda path: any(r.match(path) for r in res)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('ui', 'generated', 'code'):
        sys.exit(__doc__)
    project = {}
    if len(sys.argv) > 2:
        try:
            with open(sys.argv[2]) as f:
                project = json.load(f)
        except (OSError, ValueError):
            project = {}
    generated = matcher(BUILT_IN_GENERATED + list(project.get('generated') or []))
    if sys.argv[1] == 'generated':
        keep = generated
    elif sys.argv[1] == 'code':
        not_code = matcher(NOT_CODE)
        keep = lambda p: not not_code(p) and not generated(p)
    else:
        is_ui = matcher(project.get('ui') or BUILT_IN_UI)
        never = matcher(NEVER_UI)
        keep = lambda p: is_ui(p) and not never(p) and not generated(p)
    hits = [p for p in (line.strip() for line in sys.stdin) if p and keep(p)]
    print('\n'.join(hits))
    sys.exit(0 if hits else 1)


if __name__ == '__main__':
    main()
