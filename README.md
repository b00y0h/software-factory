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
/factory continue [run] [answer] resume a run, or answer the question it paused on
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

Watch the board: `/factory` starts the dashboard for you on its first command, opens it in
your browser, and gives you the link (normally <http://localhost:8765/dashboard.html>).
Sessions share one dashboard per repo, served on localhost only, and it keeps running after
the session ends. Add `?demo` to the link to see it run on sample data. To serve it by hand:

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory ~/.factory/<repo>
```

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

1. **Find what's already done.** The spec-writer reads the ADR and its execution plan or
   workplan, then surveys the work that already exists: the base branch, open branches and
   PRs or MRs, the code itself, the ADR's own status table, and earlier factory runs. It
   writes `~/.factory/<repo>/runs/<adr>/plan.md`, with every unit in build order marked:
   - `done`: already on the base branch, with evidence for each criterion. No work.
   - `adopt: <branch>`: built on an unmerged branch. That branch is merged into the run,
     then the builder verifies it, finishes it and proves it.
   - `build`: not started, or only partly done (the spec lists what's already in place,
     and the builder finishes the rest).
   - `skip: <reason>`: another repo, another team's work, or deferred.
   - `ask: <question>`: needs an input only you have.

   Release and launch conditions go under *Rollout gates*, and they never block a build.
2. **Build every unfinished unit in order on one branch.** If the ADR's branch already
   exists, the run continues on it (merging the base branch in if it has fallen behind)
   and updates its PR. Otherwise it creates one, named by `project.md`'s ADR-run rule (for
   example `feature/0062-…`, when `feature/` is what triggers a preview). Each unit is a full
   job:
   - its spec adopts the plan's unit word for word, with a *Drift from source* note and an
     *Already in place* list;
   - it gets its own builder;
   - its reviewers see only that unit's diff;
   - its approver accepts it onto the branch. Risky changes (schema, permissions, CI) are
     flagged for the PR reviewer instead of stopping the run.
3. **Check the whole ADR is complete.** The approver checks every acceptance criterion of
   every unit on the finished branch, including the units that were done before the run.
   Gaps get one round of fix jobs. If any remain, the run pauses for you
   (`/factory continue <run> push anyway` ships with the gaps listed in the PR).
4. **Update the workplan.** If the ADR has a status table, a last unit records every unit's
   outcome in it.
5. **Push once.** The branch is pushed and a PR opens (or the existing one is updated),
   never with auto-merge, and as a draft if `project.md` says so. You review the whole ADR
   on its preview. The PR lists every unit and how it got done, everything skipped and why,
   the completion check, the approvers' flags, any overlaps, and the rollout gates.

Running `/factory adr` on an ADR that already has a run picks that run up instead of starting
another, after refreshing its plan, so work merged in the meantime is marked done.

If a unit is escalated, or reaches an `ask:`, the run pauses. Use `/factory approve`,
`/factory rework`, or `/factory continue <answer>`. `/factory continue` also resumes a run
after the session ends. A rework after the push commits on top and pushes again, and the
preview updates.

## Where things live

- **`factory/project.md`**, in the repo and committed: the profile every agent reads.
- **`~/.factory/<repo>/`**, on your machine: one board file per job or run (`board/<id>.json`,
  each written only by the session that owns it), the backlog, run plans, one folder per
  job, and the dashboard. It sits outside every checkout, so every session shares it and any
  session can pick a run back up.
- **The floor**: the one checkout where the builder works, which is the factory session's own
  worktree. Claude Code lets a worktree session edit files only in its own worktree, so the
  factory builds there, switching its branch per job or run. Started from a repo's main
  checkout, `/factory` first moves into `.claude/worktrees/factory`, so your main checkout
  never changes branch. The floor holds one job or one run at a time.

## Several sessions at once

Open one Claude Code session per ADR (or job), and run `/factory adr <ADR>` in each. They
run side by side:

- **One floor each.** Every session builds in its own worktree. A session's floor holds one
  job or run at a time, and two sessions can never claim the same run or job id.
- **One dashboard.** Each session writes only its own `board/<id>.json`, and the dashboard
  merges them all, showing which floor each run is on. Every ADR run gets its own color: a
  stripe down its run strip and down each of its cards, whose tag also names the ADR
  (`0062 · U18`). One-off jobs have no strip to match, so they stay uncolored and carry a
  `one-off` tag. Serve it once; every session's work appears there.
  When a run's PR merges (or a job's), its strip and cards leave the board for the **Shipped**
  list at the bottom: a permanent record of everything the factory has finished, with its
  units, branch, PR and plan.
- **One profile.** Every session reads the same `factory/project.md`, and only `/factory init`
  writes it.
- **Taking turns on the heavy work.** Builders run installs, builds, typechecks, lints and test
  suites under a shared lock (`~/.factory/<repo>/tests.lock`), so two sessions never swamp
  the machine with test suites at once. Specs and reviews still run in parallel.
- **Overlap warnings, handled.** Each run lists the files it plans to touch, and later the
  files it did touch. When two open runs or jobs share a file (generated files such as
  lockfiles and generated types don't count), both cards show a warning that says which will
  likely merge first and what happens next. Before anything is pushed, its builder brings the
  latest base branch in, resolves any conflict, regenerates generated files and reruns the
  gates. A hand-resolved conflict is reviewed like any other change, so overlapping work is
  sorted out by the factory, not left for whoever merges the PR.

`/factory continue <run>` picks a specific run back up, for example after its session ended.

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
