# Software Factory

A Claude Code plugin that turns one command into a small software team. Give it a feature, or a
whole ADR, and it writes specs, builds them, has four reviewers check each one in parallel, and
then ships the work or stops and asks you. Every step is a subagent, and each one reads files
and writes exactly one. A live dashboard shows every job moving through the loop.

```
feature or ADR unit → spec-writer → builder ⇄ 4 reviewers → approver → job: merge per project.md
                       opus         opus      security opus  opus      run: next unit, then one preview PR
                                              ux · ui · code sonnet          └→ needs-human ◄── /factory approve
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
/factory adr <ADR>               build every buildable unit of an ADR, in order, then open one preview PR
/factory continue [answer]       resume a run, or answer the question it paused on
/factory <feature>               run a new job through the loop
/factory next                    run the first unchecked item in the backlog
/factory approve <job-id>        accept a job that is waiting on a human
/factory rework <job-id> <note>  send a job back to the builder with feedback
```

The first `/factory` in a repository runs `init` and stops. The **surveyor** reads the repo
(its agent instructions, manifests, CI config and git history) and writes
`factory/project.md`: the stack, the setup and test commands, the rules a change most often
breaks, the security hot spots, the users, the branch names, any preview environments, and
how this repo merges. Every other agent reads it first. Read it, fix anything wrong, then run
`/factory` again.

Watch the board:

```bash
cd ~/.factory/<repo> && python3 -m http.server 8765
```

Then open <http://localhost:8765/dashboard.html>, or add `?demo` to see it run on sample data.

## How a job runs

| Step | Agent | Writes |
|---|---|---|
| Spec | `spec-writer` (opus), built on the spec-author templates | `jobs/<id>/spec.md`, with numbered acceptance criteria. If the work already has a written spec, its file table and criteria are copied word for word. |
| Build | `builder` (opus), in its own git worktree | commits, plus `build.md` with the evidence for each criterion |
| Review | `review-security` (opus), `review-ux`, `review-ui`, `review-code` (sonnet), in parallel | `round-N/review-<name>.md`, starting `VERDICT: PASS` or `VERDICT: CHANGES` |
| Approve | `approver` (opus) | `decision.md`, starting `APPROVE` or `ESCALATE` |

Any `CHANGES` sends the round back to the same builder. After two rounds, or on `ESCALATE`,
the job waits for you. Reviewers and the approver have no Edit tool, and only the
orchestrator creates branches or pushes.

## Running a whole ADR

`/factory adr 0062` (a number, a file, or a folder):

1. **Plan.** The spec-writer reads the ADR and its execution plan or workplan, then writes
   `~/.factory/<repo>/runs/<adr>/plan.md`. It lists every unit in build order, marked `build`,
   `skip: <reason>` (another repo, another team's work, or deferred) or `ask: <question>`
   (needs an input only you have). Release and launch conditions go under *Rollout gates*,
   and they never block a build.
2. **Build every unit in order on one branch**, named by `project.md`'s ADR-run rule (for
   example `feature/0062-…`, when `feature/` is what triggers a preview). Each unit is a full
   job:
   - its spec adopts the plan's unit word for word, plus a *Drift from source* note for
     anything that has moved since the plan was written;
   - it gets its own builder;
   - its reviewers see only that unit's diff;
   - its approver accepts it onto the branch. Risky changes (schema, permissions, CI) are
     flagged for the PR reviewer instead of stopping the run.
3. **Push once.** When the last unit is accepted, the branch is pushed and a PR opens, never
   with auto-merge (and as a draft if `project.md` says so), so you can review the whole ADR
   on its preview. The PR lists every unit, what was skipped and why, the approvers' flags,
   and the rollout gates.

If a unit is escalated, or reaches an `ask:`, the run pauses. Use `/factory approve`,
`/factory rework`, or `/factory continue <answer>`. `/factory continue` also resumes a run
after the session ends. A rework after the push commits on top and pushes again, and the
preview updates.

## Where things live

- **`factory/project.md`**, in the repo and committed: the profile every agent reads.
- **`~/.factory/<repo>/`**, on your machine: the board, the backlog, run plans, one folder per
  job, and the dashboard. It sits outside every checkout, so any session can pick a run
  back up.
- **The floor**: the one checkout where the builder works, which is the factory session's own
  worktree. Claude Code lets a worktree session edit files only in its own worktree, so the
  factory builds there, switching its branch per job or run. Started from a repo's main
  checkout, `/factory` first moves into `.claude/worktrees/factory`, so your main checkout
  never changes branch. The floor holds one job or one run at a time.

## Branches and merging

Nothing is ever named `factory/`. The spec-writer names each branch by `project.md`'s rule.
After a job's `APPROVE`, the orchestrator pushes exactly the reviewed commit and follows the
merge mode:

- `auto-merge`: open a PR or MR with auto-merge on. The host merges once required checks
  pass. The surveyor only chooses this when it can show the host refuses to merge without
  them.
- `open-only`: open the PR or MR, and you merge it. This is the default whenever the gate
  can't be verified.
- `local`: merge into the local base branch, for repos with no remote.

ADR runs never auto-merge. It works with GitHub (`gh`), GitLab (`glab`, including
self-hosted), and repos with no remote.

## Change it

- **The loop:** `skills/factory/SKILL.md`. Its Knobs table holds `MAX_ROUNDS`.
- **An agent:** `agents/<role>.md`. Its model and tools are in the frontmatter.
- **A reviewer:** add `agents/review-<name>.md`, then add `<name>` to `REVIEWERS` in
  `SKILL.md` and in `skills/factory/assets/dashboard.html`.
- **Spec style:** `skills/factory/spec-author/`.
