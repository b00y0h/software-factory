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
| ADR runs | Branch `<prefix>/<adr file name>`; PR opens as a draft: yes / no; units ship: `one PR` (default) / `one PR per unit` / `as the plan says` | <how earlier ADRs here were merged> |
| Spec approval | `off` / `risky` / `always`: when a human approves a spec (or a run's plan) before it is built | |
| CI shepherd | `on` / `off`; wait up to <minutes, default 30> for checks after a push | <the CI that runs on PRs> |

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

## Test quality

How the test-quality reviewer proves that tests would catch a bug. It works in a scratch
checkout (a `git worktree` outside the floor), never in the floor itself.

- Mutation tool: <Stryker / mutmut / PIT / cargo-mutants / Infection / none>, and the command
  that runs it **scoped to some files**: `<command with a <files> placeholder>`
- Scratch checkout setup: <the fastest way to make a fresh `git worktree` able to run one test
  file, e.g. `ln -s <floor>/node_modules node_modules`, or "same as *Set up a fresh worktree*">
- Test files: <globs for this repo's tests, so source and tests can be told apart>

## UI paths

Files that are user interface here. A change touching any of them gets the accessibility
reviewer (WCAG 2.2 AA). Tests, stories and generated files never count.

- `<glob>`

## Accessibility checks

- Existing checks: <axe in unit tests / Playwright + axe / lint rules / Lighthouse, with commands, or none>
- Browser scan: <Playwright and axe-core in node_modules? yes or no>
- Rendering UI locally for a scan: <how: dev server and page, or component + stylesheet>

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
