# The software factory

This folder is the factory's floor for this repository. The machinery itself is the
[`software-factory`](https://github.com/b00y0h/software-factory) Claude Code plugin: the
`/factory` orchestrator, eight agents, the spec-author templates, and this dashboard. Give it a
feature, and it writes a spec, builds it on its own branch, has four reviewers check it in
parallel, and then either ships it or stops and asks you.

```
feature → spec-writer → builder ⇄ 4 reviewers (security · ux · ui · code) → approver → merge
                                     (max 2 rounds)                              └→ needs-human
```

| File | What it is |
|---|---|
| `project.md` | This repo's profile: stack, test commands, rules, and how it merges. Every agent reads it first. **Yours to edit.** |
| `board.json` | Durable state, written only by the orchestrator. It drives the dashboard. |
| `backlog.md` | The queue for `/factory next`. |
| `jobs/NNN-slug/` | One folder per job: `feature.md`, `spec.md`, `build.md`, `round-N/review-*.md`, `decision.md`. |
| `dashboard.html` | The live board. Refreshed from the skill on every run, so don't edit it here. |

## Run it

```text
/factory init                    survey this repo and (re)write project.md
/factory <feature>               run a new job through the loop
/factory next                    run the first unchecked item in backlog.md
/factory approve <job-id>        merge a needs-human job
/factory rework <job-id> <note>  send a job back to the builder with feedback
```

Watch it:

```bash
cd factory && python3 -m http.server 8765
```

Then open <http://localhost:8765/dashboard.html>. Add `?demo` to see it running on sample
data.

## What "merge" means

The builder commits on `factory/<job-id>`, in its own worktree, and never pushes. After
`APPROVE`, the orchestrator pushes exactly the reviewed commit and follows the merge mode
in `project.md`:

- `auto-merge`: open a PR with auto-merge on. The host merges once the required checks pass.
- `open-only`: open the PR, and you merge it.
- `local`: merge into the local base branch (only for repos with no remote).
