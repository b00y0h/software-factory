# Software Factory

A Claude Code plugin that turns one command into a small software team. `/factory <feature>`
writes a spec, builds it on its own branch, has four reviewers check it in parallel, and then
merges it or stops and asks you. Every step is a subagent, and each one reads files and writes
exactly one. A live dashboard shows every job moving through the loop.

```
feature → spec-writer → builder ⇄ 4 reviewers → approver → merge
           opus         opus      security opus  opus        └→ needs-human ◄── /factory approve
                                  ux · ui · code sonnet
                                  (max 2 rounds; all four must report before the builder resumes)
```

## Install

```text
/plugin marketplace add b00y0h/software-factory
/plugin install software-factory@software-factory
```

Start a new session afterwards so the skill and agents load.

## Use

```text
/factory init                    survey this repo and write factory/project.md
/factory <feature>               run a new job through the loop
/factory next                    run the first unchecked item in factory/backlog.md
/factory approve <job-id>        merge a job that is waiting on a human
/factory rework <job-id> <note>  send a job back to the builder with feedback
```

The first `/factory` in a repository runs `init` and stops. The **surveyor** reads the repo
(its agent instructions, manifests, CI config and git history) and writes
`factory/project.md`: the stack, the setup and test commands, the rules a change most often
breaks, the security hot spots, the users, and how this repo merges. Every other agent reads
it first. Read it, fix anything wrong, then run `/factory` again.

Watch the board:

```bash
cd factory && python3 -m http.server 8765
```

Then open <http://localhost:8765/dashboard.html>, or add `?demo` to see it run on sample data.

## How a job runs

| Step | Agent | Writes |
|---|---|---|
| Spec | `spec-writer` (opus), built on the spec-author templates | `jobs/<id>/spec.md`, with numbered acceptance criteria |
| Build | `builder` (opus), in its own git worktree on `factory/<id>` | commits, plus `build.md` with the evidence for each criterion |
| Review | `review-security` (opus), `review-ux`, `review-ui`, `review-code` (sonnet), in parallel | `round-N/review-<name>.md`, starting `VERDICT: PASS` or `VERDICT: CHANGES` |
| Approve | `approver` (opus) | `decision.md`, starting `APPROVE` or `ESCALATE` |

Any `CHANGES` sends the round back to the same builder. After two rounds, or on `ESCALATE`,
the job waits for you. Reviewers and the approver have no Edit tool, and only the
orchestrator pushes.

## What "merge" means

After `APPROVE`, the orchestrator pushes exactly the reviewed commit and follows the merge
mode in `project.md`:

- `auto-merge`: open a PR or MR with auto-merge on. The host merges once required checks
  pass. The surveyor only chooses this when it can show the host refuses to merge without
  them.
- `open-only`: open the PR or MR, and you merge it. This is the default whenever the gate
  can't be verified.
- `local`: merge into the local base branch, for repos with no remote.

It works with GitHub (`gh`), GitLab (`glab`, including self-hosted), and repos with no remote.

## Change it

- **The loop:** `skills/factory/SKILL.md`. Its Knobs table holds `MAX_ROUNDS`.
- **An agent:** `agents/<role>.md`. Its model and tools are in the frontmatter.
- **A reviewer:** add `agents/review-<name>.md`, then add `<name>` to `REVIEWERS` in
  `SKILL.md` and in `skills/factory/assets/dashboard.html`.
- **Spec style:** `skills/factory/spec-author/`.
