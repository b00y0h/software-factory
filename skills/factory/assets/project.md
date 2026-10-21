# Factory profile — <name>

Written by the factory's surveyor on <date>. **Edit it freely.** Every factory agent reads
this file before working, and it wins over their generic briefs wherever they differ.

## Settings

| Setting | Value | Evidence |
|---|---|---|
| Name | <product name used in docs> | |
| Base branch | `main` on `origin` | |
| Host | `github` + `gh` / `gitlab` + `glab` / `none` | |
| Merge mode | `auto-merge` / `open-only` / `local` | <what proves the host gates merges on green checks> |
| Branch names | <the rule, e.g. `<type>/<kebab-summary>`, and when a functional prefix applies>. Never `factory/`. | <merged branch names, CI rules> |
| Previews | <what triggers a preview environment and where its URL appears, or `none`> | |
| ADR runs | Branch `<prefix>/<adr file name>`; PR opens as a draft: yes / no | |

## Stack

Languages, frameworks, package manager and pinned versions, plus one line per app or package
that matters.

## Set up a fresh worktree

```bash
# the exact commands the builder runs once in a new worktree
```

## Tests and gates

- Test one package or module: `<command>`
- Run a single test file: `<command>`
- Typecheck and lint: `<command>`
- What CI runs: <job names>
- Never run locally: <command> (why)

## Git and PR rules

- Commit messages: <format>
- PR title: <format, and the linter that enforces it>
- Push notes: <anything unusual about pushing from this machine or repo>

## Generated files

Committed files a command produces. They're never merged by hand: after a merge the builder
regenerates them, and overlap warnings ignore them. One per line, as a glob pattern with the
command that regenerates it.

- `<glob>`: `<command>`

## Rules that bite

The repo's conventions a change most often breaks. The builder follows them and the code
reviewer checks them. Cite the file each one comes from.

## Security hot spots

Where authentication, permissions, tenancy, secrets and user input live in this repo.

## Users and UI

Who uses each surface, the component library and design tokens, and anything a user must
never be able to do.

## Always escalate

Paths or kinds of change that need a human here, on top of the approver's generic list.
