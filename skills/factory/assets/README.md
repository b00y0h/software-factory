# The software factory

This repo is set up for the [`software-factory`](https://github.com/b00y0h/software-factory)
Claude Code plugin. Give `/factory` a feature, or a whole ADR, and it writes specs, builds
them, has four reviewers check each one in parallel, and then ships the work or stops and
asks you.

```
feature or ADR unit → spec-writer → builder ⇄ 4 reviewers (security · ux · ui · code) → approver
                                                (max 2 rounds)          job: merge  ┘   └→ needs-human
                                                                        run: next unit, then one preview PR
```

## What lives where

| Where | What |
|---|---|
| `factory/project.md` (this folder, committed) | This repo's profile: stack, test commands, rules, branch names, previews, and how it merges. Every agent reads it first. **Yours to edit.** |
| `~/.factory/<repo>/` (on your machine) | The factory's state, shared by every session: one `board/<id>.json` per job or run (written only by the session that owns it), `project.json`, `backlog.md`, `runs/<adr>/plan.md`, one `jobs/<id>/` folder per job, and `dashboard.html`. It sits outside every checkout, so any session can pick a run back up. |
| the floor | The checkout where a session's builder works: that session's own worktree, holding one job or run at a time. If you start `/factory` from the main checkout, it moves into `.claude/worktrees/factory-<id>` first, so the main checkout never changes branch. |

Several sessions can run ADRs or jobs at once, one each. They share one dashboard, take turns
on heavy commands such as test suites, and warn when two of them touch the same files.

## Run it

```text
/factory init                    survey this repo and (re)write factory/project.md
/factory adr <ADR>               build every buildable unit of an ADR, in order, then open one preview PR
/factory continue [run] [answer] resume a run, or answer the question it paused on
/factory <feature>               run a new job through the loop
/factory next                    run the first unchecked item in the backlog
/factory approve <job-id>        accept a job that is waiting on a human
/factory rework <job-id> <note>  send a job back to the builder with feedback
```

Watch it: `/factory` starts the dashboard on its first command, opens it in your browser, and
gives you the link (normally <http://localhost:8765/dashboard.html>). Every session's work
shows there. Add `?demo` to see it running on sample data. To serve it by hand:

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory ~/.factory/<repo>
```

## Branches and merging

Nothing is ever named `factory/`. The spec-writer names each branch by `project.md`'s rule.
The builder commits on the floor, but it never pushes.

- **A job**: after `APPROVE`, the orchestrator pushes exactly the reviewed commit and follows
  the merge mode in `project.md`. `auto-merge` opens a PR that the host merges once the
  required checks pass, `open-only` opens a PR for you to merge, and `local` merges into the
  local base branch (for repos with no remote).
- **An ADR run**: every unit is accepted onto one branch, named by the ADR-run rule (for
  example `feature/0062-…`, where `feature/` triggers a preview). When the last unit is
  accepted, the branch is pushed once and a PR opens, never with auto-merge, so you can
  review the whole ADR on its preview.
