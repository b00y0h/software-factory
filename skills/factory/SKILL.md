---
name: factory
description: Run the software factory in any repository. Takes one feature, or every unit of an ADR in build order, through spec (built on spec-author), build, four parallel reviews and approval, with every step done by a subagent and tracked on a live dashboard. Several sessions can run jobs or ADRs at once, one per session. Use only when the user types /factory.
argument-hint: "init | adr <ADR> | continue [run] [answer] | <feature> | next | approve <job-id> | rework <job-id> <note>"
disable-model-invocation: true
---

# /factory: you are the orchestrator

The session running this skill is an orchestrator. You run the loop below for **one** job or
**one** ADR run, and spawn every agent it needs. You are the only writer of your own board
file, and the only one who creates branches or pushes for your job or run. You never write a
spec, code, review or decision yourself. Agents do that, one file each. If an agent fails,
retry it once, then move the job to `needs-human`. Never do its work for it.

Other sessions may be running other jobs or runs on the same repo at the same time. Each has
its own floor (its own worktree) and its own board file, and the dashboard shows all of them.
You never write another session's files.

This skill ships in the `software-factory` plugin, and the same machinery runs in every
repository. What differs per repo lives in that repo's `factory/project.md`: its stack, its
test commands, its rules, its branch names, and how it merges. Every agent reads that file
first.

The factory works in two ways:

- **A job** (`/factory <feature>`): one feature, one branch, one PR, merged per the merge mode.
- **An ADR run** (`/factory adr <ADR>`): every unit of an ADR that isn't done yet, in build
  order, each one a job on the **same** branch. Work that already exists (merged, on an open
  branch, or partly built) is found and kept. A completion check confirms the whole ADR is
  done, then the branch is pushed once and a PR opens (or is updated) for preview and human
  review. A run never auto-merges.

## The loop (edit this to change the factory)

```
                   ┌──────────────────┐
                   │ feature, or the  │
                   │ next ADR unit    │
                   └─────────┬────────┘
                             ▼
                   ┌─────────────────────────────────────┐
                   │   spec-writer (uses spec-author)    │
                   │       opus                          │
                   └─────────┬───────────────────────────┘
                             ▼
                   ┌──────────────────┐
                   │     builder      │◄────────────────────┐
                   │       opus       │                     │
                   └─────────┬────────┘                     │
        ┌─────────────┬──────┴──────┬─────────────┐         │
        ▼             ▼             ▼             ▼         │
  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐   │
  │  security │ │     ux    │ │ ui design │ │    code   │   │
  │    opus   │ │   sonnet  │ │   sonnet  │ │   sonnet  │   │
  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘   │
        └─────────────┴──────┬──────┴─────────────┘         │
                             ▼                              │
                   ┌──────────────────┐   any CHANGES:      │
                   │   WAIT FOR ALL   ├─────────────────────┘
                   │   4 reviews in   │   resume builder
                   └─────────┬────────┘   (max 2 rounds)
                             ▼ all PASS
                   ┌──────────────────┐
                   │     approver     │
                   │       opus       │
                   └─┬───────────────┬┘
             APPROVE │               │ ESCALATE
                     ▼               ▼
   ┌──────────────────────────┐ ┌─────────────┐
   │ job: merge per project.md│ │ needs-human │ ◄── /factory approve
   │ run: next unit; after the│ └─────────────┘
   │ last, push + preview PR  │
   └──────────────────────────┘
```

## Roles

Every role is a subagent in this plugin's `agents/` folder. Its file sets its model and the
tools it may use, so reviewers and the approver cannot edit code: they have no Edit tool.

| Role | `subagent_type` | Model | Writes |
|---|---|---|---|
| surveyor | `software-factory:surveyor` | opus | the repo's `factory/project.md` (only at init) |
| spec-writer | `software-factory:spec-writer` | opus | `spec.md`, or a run's `plan.md` |
| builder | `software-factory:builder` | opus | commits on the branch, plus `build.md` |
| review-security | `software-factory:review-security` | opus | `round-N/review-security.md` |
| review-ux | `software-factory:review-ux` | sonnet | `round-N/review-ux.md` |
| review-ui | `software-factory:review-ui` | sonnet | `round-N/review-ui.md` |
| review-code | `software-factory:review-code` | sonnet | `round-N/review-code.md` |
| approver | `software-factory:approver` | opus | `decision.md` |

The spec-writer is the spec-author skill folded in. Its templates are in this skill's
`spec-author/` folder. When a feature or unit already has a written spec, it adopts that
spec's file table and acceptance criteria word for word.

Spawn every agent the same way. The prompt is only names and paths:

```
Agent(subagent_type: "software-factory:<role>", description: "<role> <JOB>",
      [name: "builder-<JOB>"  ← the builder only],
      prompt: "MODE=<job | unit | plan | adr>
               SKILL_DIR=<abs>
               WORKTREE=<abs>     ← your floor
               FACTORY=<abs>      ← the shared state folder
               JOB=<JOB>          JOB_DIR=<abs>
               RUN=<RUN>          RUN_DIR=<abs>     ← runs only
               ADR=<abs>                            ← spec-writer, MODE=plan only
               BRANCH=<branch>                      ← once it exists
               DIFF_BASE=<sha>                      ← builder, reviewers, approver
               ROUND_DIR=<abs>                      ← reviewers, and the builder on resume
               SYNC=<n>                             ← only while bringing the base branch in")
```

`MODE` is `job` for a feature, `unit` for the spec-writer on an ADR unit, `plan` for the
spec-writer planning a run, and `adr` for the builder, reviewers and approver inside a run.
Agents get their context from those files, never from this conversation.

## Knobs

| Knob | Value | Meaning |
|---|---|---|
| `MAX_ROUNDS` | 2 | Review rounds a job gets before it goes to `needs-human` |
| `REVIEWERS` | security, ux, ui, code | Role `review-<name>` writes `review-<name>.md` |

## The floor, the state folder, and your board file

**Your floor** (`WORKTREE`) is the one checkout where your job or run is built: this
session's own checkout, provided it is a **linked worktree**. Claude Code lets a worktree
session edit files only in its own worktree, so a builder in any other checkout would be
refused. A floor holds one job or one run at a time, switching its branch as it goes. Another
session has another floor.

- `git rev-parse --git-dir` differs from `git rev-parse --git-common-dir`: this session is in
  a linked worktree, so it is your floor. Refuse to start if another board file already holds
  an unfinished job or run on this floor (see **Board files**). Finish or continue that one
  first.
- They're the same: this session is on the repo's **main checkout**, and the factory never
  switches that checkout's branch. Claim your job or run id first (below), then create
  `<ROOT>/.claude/worktrees/factory-<id>` (`git -C <ROOT> worktree add --detach <path>
  <BASE_REF>`), load `EnterWorktree` with ToolSearch, and enter it **before spawning any
  agent**. That is your floor. If `EnterWorktree` isn't available, stop and tell the user to
  open a session in that folder.

Before work starts on your floor, it must have no changes outside `factory/`
(`git status --porcelain -- . ':!factory'` prints nothing). Otherwise stop, and say what's
uncommitted.

**The state folder** (`FACTORY`) is `~/.factory/<repo>/`, outside every checkout and shared
by every session:

| Path | Written by |
|---|---|
| `project.json` | Setup only: `{ "name", "host", "merge" }` from the profile's Settings |
| `board/<id>.json` | **one file per job or run, written only by the session that owns it** |
| `backlog.md` | the user; `/factory next` ticks items |
| `jobs/<JOB>/`, `runs/<RUN>/` | the agents of the owning session |
| `tests.lock` | the lock builders take turns on to run heavy commands |
| `dashboard.html` | copied from this skill on every command |

The repo keeps only `factory/project.md` and `factory/README.md`.

| Name | Value |
|---|---|
| `SKILL_DIR` | this skill's base directory, shown when the skill loads (inside the plugin's install folder) |
| `ROOT` | the repo's main checkout: `dirname "$(git rev-parse --path-format=absolute --git-common-dir)"` |
| `<repo>` | `basename <ROOT>` |
| `WORKTREE` | your floor (above) |
| `FACTORY` | `~/.factory/<repo>` (absolute) |
| `PROFILE` | `<WORKTREE>/factory/project.md` |
| `BASE` | the base branch from `PROFILE` Settings, normally `main`. `BASE_REF` is `origin/<BASE>`, or `<BASE>` when Host is `none` |
| `RUN` | the ADR's file or folder name, for example `0062-childrens-code-opt-in-tenant` |
| `RUN_DIR` | `FACTORY/runs/<RUN>` |
| `JOB` | a run unit: `<adr number>-<unit id>-<2 words>`, for example `0062-u0-tenant-policy`. A standalone job: `NNN-<slug>`, the next number after the highest in `FACTORY/jobs/` (starting at `001`). |
| `JOB_DIR` | `FACTORY/jobs/<JOB>` |
| `BOARD` | your board file: `FACTORY/board/<RUN>.json` for a run, `FACTORY/board/<JOB>.json` for a standalone job |
| `BRANCH` | named by the spec-writer, following `PROFILE`'s Branch names rule. **Never** a `factory/` prefix. |
| `DIFF_BASE` | the commit the job or unit started from. Reviewers diff `DIFF_BASE..HEAD`, so in a run they see only this unit's work. |
| `ROUND_DIR` | `JOB_DIR/round-<N>` |

**Claiming an id.** Two sessions must never take the same id. Claim it by creating its
folder with a plain `mkdir` (no `-p`), which fails if the folder exists:
- A run: `mkdir FACTORY/runs/<RUN>`. If it exists and that run isn't `merged`, it is already
  someone's: refuse, and point at `/factory continue <RUN>` from the session that owns it.
- A standalone job: `mkdir FACTORY/jobs/<NNN-slug>`. If it exists, take the next number and
  try again.
- A run unit: its id carries the ADR number, so it is unique once the run is claimed.

## Commands

Parse `$ARGUMENTS`:

| Input | Do |
|---|---|
| `init` | Run **Setup**, even if `PROFILE` already exists (it is replaced). |
| `adr <ADR>` | Run an **ADR** to completion. `<ADR>` is a path to the ADR file or its folder, or just its number (find `docs/**/<number>*`). Work already done on the ADR is found and kept, and an existing run of it is picked up. |
| `continue [run] [answer]` | Resume a run (see **Continuing a run**). If the first word is the id of an open run, it picks the run; the rest is the answer. |
| `next` | Claim the first `- [ ]` line in `FACTORY/backlog.md` that no other session has claimed (`mkdir FACTORY/claims/<first 12 hex of the line's sha1>` succeeds), tick it (`- [x] <text> → <JOB>`), and run it as a new job. If none is left, say so and stop. |
| `approve <job-id>` | The job must be in `needs-human` on **your** floor (enter its floor first if this session isn't on it; see **Continuing a run**). For a job, go to **Merge**. For a run unit, accept it (step 6 of the run) and continue the run. |
| `rework <job-id> <note>` | Same floor rule. Go to **Rework**. |
| anything else | The text is a feature. Run a new **job**. |

Before any command:
1. If `FACTORY/board.json` exists, this state folder predates per-session board files.
   Migrate it once: write its `project` block to `project.json`, write each run (with its
   unit jobs) to `board/<RUN>.json` and each other job to `board/<JOB>.json`, then delete
   `board.json`.
2. Settle your floor (above).
3. If `PROFILE` doesn't exist, run **Setup** and stop there.
4. Copy `SKILL_DIR/assets/dashboard.html` to `FACTORY/dashboard.html` if that file is missing, or
   if its `factory-dashboard-version` meta tag is lower than this skill's (a session on an
   older plugin must never replace a newer dashboard).
5. **Start the dashboard.** Run `bash "<SKILL_DIR>/scripts/dashboard.sh" "<FACTORY>" --open`.
   It reuses a server that any session already started for this repo, or starts one on
   localhost (from port 8765 up) that keeps running after this session. It prints
   `running <url>` or `started <url>`, and opens the browser only when it started one. Give
   the user the link the first time in a session, and whenever it says `started`. Every
   session's work shows on that one page. If the script fails, say why in one line and carry
   on: the dashboard is a view, never a blocker.
6. Tidy up your own board file only: if your job is `merging` or your run `pushed`, check its
   PR or MR (`gh pr view <url> --json state`, or `glab mr view <url> -F json`). If it is
   merged, set `merged`. Never poll.
7. Keep `FACTORY/project.json` in step with `PROFILE`: its `name`, `host` and `merge` from the
   Settings table, and `generated` from the *Generated files* list. Rewrite it (write a `.tmp`
   file, then `mv`) only if something differs.

## Setup

1. Create `FACTORY` with `board/`, `jobs/`, `runs/` and `claims/`. Copy `dashboard.html`
   from `SKILL_DIR/assets/`, and `backlog.md` if there isn't one. Start the dashboard (step 5
   above), so the user can watch the setup too.
2. Copy `SKILL_DIR/assets/README.md` to `WORKTREE/factory/README.md`. Spawn the `surveyor`. It
   inspects the repo and writes `PROFILE`.
3. Write `FACTORY/project.json` from `PROFILE`: the name, host and merge mode from Settings,
   and the *Generated files* patterns as `generated`.
4. Show the user the Settings table, and say in a line what the merge mode and the branch
   rules mean for them. Then stop and ask them to read `factory/project.md` (and commit it,
   so teammates and other sessions share it) before the first job. It governs what gets
   run, what gets pushed, and what gets merged.

## Overlap with other sessions

Two jobs or runs that change the same files may conflict when the second one merges. The
factory handles that itself: every job and run brings the base branch in before it pushes
(see **Bringing the base branch in**), and its builder resolves any conflict, with the
resolution reviewed like any other change. Overlap warnings tell the user what is coming,
and that nothing needs doing unless the two pieces of work disagree about the same code.

- Every board file lists the repo paths its work touches in `files`: the planned paths
  (from the plan's *Files this run touches*, or a job spec's *Files to touch*) as soon as
  they're known, plus the actually changed paths
  (`git -C <WORKTREE> diff --name-only <BASE_REF>...HEAD`) after each accepted unit or job.
  Strip line ranges (`Foo.ts:620-700` → `Foo.ts`).
- **Generated files never count.** A generated file is regenerated after a merge, never
  merged by hand, so overlapping on one means nothing. Leave out every path that matches
  `PROFILE`'s *Generated files* or the built-in list: `**/pnpm-lock.yaml`,
  `**/package-lock.json`, `**/yarn.lock`, `**/bun.lockb`, `**/payload-types.ts`,
  `**/importMap.js`, `**/*.generated.*`, `**/__generated__/**` and `**/dist/**`.
- Two paths overlap when they're equal, or one is a folder containing the other.
- **Check overlaps** by reading every other file in `FACTORY/board/` whose job or run isn't
  `merged`, and intersecting its `files` with yours. Record the result in your run's or
  job's `overlaps` as `[{ "with": "<id>", "title": "<title>", "files": [...] }]`.
- Check after the plan (or a job's spec), and again after each accepted unit. When a new
  overlap appears, tell the user in one line what will happen, not just that it exists: which
  will likely merge first (a pushed run or an auto-merging job, else a one-off job, which is
  usually quicker than a run), and that the other will bring that change in before it
  pushes. Then **continue**. Ask the user only if the two pieces of work clearly want
  opposite things from the same code. That is a product decision, not a merge.
- The dashboard computes the same overlaps across every board file, without generated files,
  and words each warning the same way.
- The final PR body lists any overlaps, and how the sync resolved them.

## Bringing the base branch in

Before anything is pushed, the branch must contain the latest base branch, so the PR merges
cleanly and its preview shows what will really ship. Overlapping work that merged first is
picked up here, by the factory, rather than left as a conflict for whoever merges the PR.

1. `git -C <WORKTREE> fetch origin <BASE>`. If
   `git -C <WORKTREE> merge-base --is-ancestor <BASE_REF> HEAD` succeeds, the branch is
   already current. Skip the rest.
2. Record `DIFF_BASE = git -C <WORKTREE> rev-parse HEAD`, then have the builder bring it in
   (prompt `SYNC=<n>`):
   - **A job:** resume `builder-<JOB>` with `SendMessage`: *"Bring <BASE_REF> into this branch
     (sync <n>). Write JOB_DIR/sync-<n>.md."*
   - **A run:** add a unit `SYNC` (title "Bring <BASE> in") after the last accepted unit, and
     run it as a job (`JOB` = `<adr>-sync-<n>`), spawning `builder` with `SYNC=<n>`.
3. Read the first line of `JOB_DIR/sync-<n>.md`:
   - `CLEAN`: the merge had no conflicts, and the builder re-ran the gates and regenerated the
     generated files. Accept it and record `HEAD` as the reviewed commit.
   - `RESOLVED <n>`: the builder resolved conflicts by hand. Run a review round with
     `SYNC=<n>` (reviewers judge the resolution, not the whole of the base branch), then
     the approver. Accept on `APPROVE`; otherwise `needs-human`.
   - `BLOCKED: <reason>`: a conflict needs a product decision. Set `needs-human` (and pause a
     run) with that reason.

Never rebase and never force-push. The builder does the merge and every resolution; you only
check that the branch is current and read the result.

## The job loop (shared by jobs and run units)

**Spec.** Spawn `spec-writer` (`MODE=job`, or `MODE=unit` in a run). When it finishes,
`spec.md` must exist. Copy its `# … — <feature>` title into the job's `title`, and set stage
`build`.

**Build.** Spawn `builder` with `name: builder-<JOB>`, and record that name in the job's
`builder` field. If your Agent tool has no `name` input, record the agent ID it returns and
address the builder by that ID. When it finishes, `build.md` must exist and start with no
`BLOCKED:` line. Go to round 1.

**Review round N: WAIT FOR ALL.**
1. `mkdir ROUND_DIR`. Set `stage: review`, `round: N`, and all four reviews to `pending`.
2. Spawn all four reviewers **in a single message**, so they run in parallel.
3. Each time one finishes, read the first line of its file and update its chip in `BOARD`
   right away. The dashboard fills in as verdicts land.
4. The round is done only when **all four files exist in ROUND_DIR**. Never resume the
   builder mid-round. If a reviewer finished without writing its file, spawn it again
   once. If there is still no file, move the job to `needs-human`.

A verdict is `PASS` only if the file's first line is exactly `VERDICT: PASS`. Anything else
counts as `CHANGES`. The factory fails closed.

| Outcome | Next |
|---|---|
| All four PASS | Approve |
| Any CHANGES, and `N < maxRound` | Move this round into `history` and set stage `build`. Then `SendMessage` to `builder-<JOB>`: *"Round N reviews are in ROUND_DIR. Address every CHANGES item, commit, and rewrite build.md."* When it finishes, run round N+1. |
| Any CHANGES, and `N = maxRound` | Set `needs-human` with `reason: "Review rounds used up: <reviewers still asking for CHANGES>"`. |

`SendMessage` may be a deferred tool; load it with ToolSearch (`select:SendMessage`) before
the first resume. If it cannot reach the builder (for example, this is a new session), spawn a
fresh `builder` with the same name. It rebuilds its context from the job folder, which is
why everything lives in files.

**Approve.** Set stage `approval` and spawn `approver`. Read the first line of `decision.md`:
- `APPROVE`: a job goes to **Merge**; a run unit is accepted (step 6 of the run).
- `ESCALATE`, or anything else: set `needs-human`, and copy its `Reason:` line into `reason`.
  In a run, the run is `paused` until you're told `approve` or `rework` for that job.

## Running a job

1. **Start.** Claim `JOB` (`mkdir FACTORY/jobs/<JOB>`) and settle your floor. Put the floor on
   a fresh base, with **no branch yet**, so nothing is named before the spec names it:
   ```bash
   git -C <WORKTREE> fetch origin <BASE>          # skip when Host is none
   git -C <WORKTREE> switch --detach <BASE_REF>
   ```
   Record `git -C <WORKTREE> rev-parse HEAD` as the job's `startSha` (its `DIFF_BASE`). Write
   the feature text, verbatim, to `JOB_DIR/feature.md`. Write `BOARD` with this job at stage
   `spec`.
2. **Spec** (`MODE=job`). Set the job's `files` from the spec's *Files to touch*, then check
   overlaps.
3. **Name the branch.** Read `**Branch:**` from `spec.md`. Refuse it, and set `needs-human`,
   if it breaks `PROFILE`'s Branch names rule, starts with `factory/`, or already exists
   (`git -C <WORKTREE> show-ref --verify refs/heads/<name>`, or
   `git -C <WORKTREE> ls-remote --exit-code --heads origin <name>`). Otherwise run
   `git -C <WORKTREE> switch -c <name>` and record it as the job's `branch`.
4. **Build, review and approve** (`MODE=job`) as in the job loop.

## Running an ADR

`/factory adr <ADR>` works through every unit of the ADR that isn't finished yet, in order, on
one branch, and finishes with the whole ADR complete. An ADR is often partly built already
(by hand, in per-unit MRs, or by an earlier run), so the run starts by finding out what is
done, and builds only the rest.

If `FACTORY/runs/<RUN>` already exists, this ADR has a run. Don't start another one: pick
that run up (see **Continuing a run**), which refreshes its plan first.

1. **Start the run.** Resolve the ADR path and `RUN`, and claim it (`mkdir FACTORY/runs/<RUN>`).
   Settle your floor and put it on a fresh base with no branch, as in step 1 of a job. Write
   `BOARD` with the run at stage `planning`, no units yet, and `floor` set to `WORKTREE`.
2. **Plan, starting with what's already done.** Spawn `spec-writer` with `MODE=plan`, `ADR`
   and `RUN_DIR`. It surveys the base branch, open branches and MRs, the code, the ADR's own
   status table and earlier runs, then writes `RUN_DIR/plan.md`: every unit in build order,
   each marked `done:` (with evidence), `adopt:` (with a branch), `build`, `skip:` or `ask:`,
   plus a **Continue from** line and the *Files this run touches*. Set the run's `files` from
   that list, then check overlaps. Tell the user in one line what was already done.
3. **Name or continue the branch.** Read `**Branch:**` and `**Continue from:**` from
   `plan.md`.
   - **Continue from `none`**: check the name as in step 3 of a job (it must follow
     `PROFILE`'s rule for ADR runs), then `git -C <WORKTREE> switch -c <name>`.
   - **Continue from an existing branch** (it must be the same name): build on it. Fetch it
     and `git -C <WORKTREE> switch <name>` (or `switch -c <name> origin/<name>`). If it is
     behind `BASE_REF`, bring it up to date with `git -C <WORKTREE> merge --no-ff <BASE_REF>`.
     Never rebase. On a conflict, `git merge --abort`, set the run `paused` with the reason,
     and stop. Record its open PR or MR, if any, as the run's `url`, so the end of the run
     updates it instead of opening another.

   Fill in the run's `branch`, `continuedFrom`, and its units in plan order (see
   **Board files**), and set stage `running`.
4. **For each unit in plan order:**
   - `done:` units are marked `done` with `prior` set to the evidence. They get no job.
   - `skip:` units are marked `skipped` and never built.
   - `ask:` units stop the run: set the run `paused`, its `reason` to the question, and tell
     the user to answer with `/factory continue <RUN> <answer>`.
   - `adopt: <branch>` units: first bring that work in with
     `git -C <WORKTREE> fetch origin <branch>` and
     `git -C <WORKTREE> merge --no-ff origin/<branch> -m "Merge <branch> (adopting <unit>)"`.
     A branch that is already in the run's history needs no merge. On a conflict, abort the
     merge, set the run `paused` with the reason, and stop. Then treat the unit like a
     `build` unit, with `DIFF_BASE` set to the commit **before** the merge, so the reviewers
     see the adopted work. Add to `feature.md`: *"Code for this unit came from <branch>
     (<PR/MR>). Verify it, finish it, and prove every criterion."* Set the unit's `adopted`
     to the branch.
   - `build` units become a job. Create `JOB_DIR`, then write `feature.md` as
     *"Unit <id> of <ADR>: <title>. Source: <source>. Adopt it; don't rewrite it."*, plus
     the plan's **Found** note for the unit and any answer the user gave. Set the job's `run`,
     `unit` and `branch`, and record `startSha = git -C <WORKTREE> rev-parse HEAD` as its
     `DIFF_BASE`. Mark the unit `active`.
   - The `WP` unit (update the workplan) waits until after the completion check (step 7).
5. **Run the job loop** for that unit: spec (`MODE=unit`), then build, review and approve
   (`MODE=adr`). Units run one at a time on your floor, each on top of the last.
6. **Accept the unit** on `APPROVE` (or `/factory approve`). `git -C <WORKTREE> rev-parse
   HEAD` must equal `decision.md`'s `Reviewed-SHA:` (or, after a human approve, be recorded
   as the reviewed commit). Set the job's stage `done` and the unit `done`. Add the unit's
   changed paths to the run's `files`, check overlaps again, and go on to the next unit.
   Never start a unit on top of an unreviewed commit.
7. **Bring the base branch in, then check that the ADR is complete.** When every other unit is
   `done` or `skipped`, first bring the base branch in (see **Bringing the base branch in**),
   so the completion check runs on what will really ship. Then set the run's `completion` to
   `checking` and spawn `approver` with `MODE=complete` and `RUN_DIR`.
   It checks every acceptance criterion of every unit, including the ones that were done
   before the run, on the current `HEAD`, and writes `RUN_DIR/completion.md`.
   - `COMPLETE`: set `completion: complete` and go on.
   - `GAPS`, the first time: for each gap line, run a fix job for that unit
     (`JOB` = `<adr>-<unit>-fix-<n>`, `feature.md` = the gap line), through the job loop.
     Then check again.
   - `GAPS` again: set `completion: gaps`, pause the run with the gaps as the `reason`, and
     tell the user. `/factory continue <RUN> push anyway` pushes with the gaps listed in the
     PR body. `/factory rework <job-id> <note>` fixes a unit, and then the check runs again.
8. **Update the workplan.** If the plan has a `WP` unit, run it now as a job. Its
   `feature.md` lists every unit's outcome from this run: done before the run (with
   evidence), adopted (with branch and PR/MR), built (with job id), fixed after the
   completion check, or skipped (with the reason).
9. **Push, and open or update the preview PR:**
   - Bring the base branch in once more if it moved while the workplan unit ran (usually a
     no-op).
   - `git -C <WORKTREE> log --oneline <BASE_REF>..HEAD` must contain only this ADR's work:
     the run's units, plus any adopted or continued branch, plus the sync merges.
   - Push exactly HEAD, and no tags:
     `git -C <WORKTREE> push --no-follow-tags -u origin HEAD:refs/heads/<BRANCH>`.
     If the output shows `[new tag]`, stop and tell the user. Pushing a continued branch
     must be a fast-forward. If it isn't, someone pushed to it meanwhile: pause the run and
     say so. Never force-push.
   - If the run already has an open PR or MR (`url`), update its description
     (`glab mr update <url> --description "<body>"`, or `gh pr edit <url> --body "<body>"`).
     Otherwise open one **without auto-merge**, as a draft if `PROFILE` says so for ADR runs:
     `glab mr create --source-branch <BRANCH> --target-branch <BASE> --title "<title>"
     --description "<body>" [--draft] --yes`, or `gh pr create --base <BASE> --head <BRANCH>
     --title "<title>" --body "<body>" [--draft]`.
   - The title is `plan.md`'s `**PR title:**`. The body contains:
     - a link to the ADR;
     - a table of every unit with its outcome (done before this run, with its evidence;
       adopted, with the branch; built, with its job id; or skipped, with the reason);
     - the completion check's result, including any gaps you were told to push anyway;
     - every approver's **Flags for the PR reviewer**;
     - the plan's **Rollout gates**;
     - any overlaps with other open runs or jobs, and their files;
     - one line on how to reach the preview, if `PROFILE` describes one.

     Add no AI attribution lines.
   - Set the run `pushed` with its `url`, and tell the user the PR link and where the preview
     will appear. Any MR an adopted unit came from will show as merged once this one merges,
     because its commits are included. Say so, so nobody merges it separately.

**After the push**, `/factory rework <job-id> <note>` still works on a run unit: the builder
commits on top of the branch, the unit is reviewed again from that commit, and when it is
accepted you bring the base branch in and push again (fast-forward only, with the same
command). The PR and its preview update themselves.

## Continuing a run

`/factory continue [run] [answer]` picks a run back up, whether it paused on a question, or
its session ended or was compacted mid-run.

- **Which run.** If a run id was given, use it. Otherwise use the open run whose `floor` is
  this session's checkout. If there is none, list the open runs (their id, stage and floor)
  and ask which one.
- **Which floor.** A run continues on the floor recorded in its board file. If this session
  isn't on it, enter it with `EnterWorktree`, but only after the user confirms that the
  session that started the run has ended. Two sessions must never drive one run. You now own
  that board file. If that floor no longer exists, use this session's floor, and continue on
  the run's branch as in step 3 of the run.
- **Refresh the plan first.** Work may have landed since the run last moved: units merged by
  hand, MRs opened. Spawn `spec-writer` with `MODE=plan` again. It keeps the unit ids and
  order and updates their statuses. Mark any unit that is now `done:` as done (with `prior`),
  and pick up any new `adopt:` when you reach that unit. Units this run already accepted
  stay `done`.
- Paused on an `ask:` unit: append the answer to that unit's job `feature.md` (create the job
  as in step 4 if it doesn't exist yet) and build it.
- Paused on a `needs-human` job: say so, and point at `/factory approve` or
  `/factory rework` for that job. Do nothing else.
- Interrupted: read your board file and the job folders, and resume the unit at its recorded
  stage. If a stage's file is missing, re-run that stage's agent. A builder resumes as a fresh
  `builder-<JOB>`, rebuilding its context from the files.

## Merge (jobs only)

Used both after `APPROVE` and for `/factory approve <job-id>` on a job. Follow `PROFILE`
wherever it says something more specific than this section.

1. Bring the base branch in (see **Bringing the base branch in**). It's usually a no-op for
   a quick job, but it's how a job picks up overlapping work that merged first.
2. Set `SHA` to `git -C <WORKTREE> rev-parse HEAD`. `SHA` must be the last commit that was
   accepted: the approver's `Reviewed-SHA:` in `decision.md`, or the sync's result. If it
   isn't, stop and set `needs-human` with the reason "branch moved after approval".
3. `git -C <WORKTREE> log --oneline <BASE_REF>..<SHA>` must list only this job's commits
   (and its sync merges). Add its changed paths to the job's `files` and check overlaps once
   more.
4. Ship it according to the merge mode in `PROFILE` Settings. The title is the `PR title:`
   line from `spec.md`. The body is the one-paragraph summary from `spec.md`, its acceptance
   criteria, each round's verdicts, any overlaps, and the decision (or "approved by a human
   with /factory approve"). Add no AI attribution lines.

| Mode | Host | Do |
|---|---|---|
| `auto-merge` | gitlab | Push (below), then `glab mr create --source-branch <BRANCH> --target-branch <BASE> --title "<title>" --description "<body>" --auto-merge --remove-source-branch --yes` |
| `auto-merge` | github | Push, then `gh pr create --base <BASE> --head <BRANCH> --title "<title>" --body "<body>"`, then `gh pr merge <url> --auto --match-head-commit <SHA>` plus the strategy flag from `PROFILE` (default `--merge`) |
| `open-only` | either | Push, then the same create command without auto-merge. A human merges. |
| `local` | none | Only if `ROOT` has `BASE` checked out and is clean: `git -C <ROOT> merge --no-ff <SHA> -m "<title>"`. Otherwise set `needs-human` with the reason. |

**Push** exactly the reviewed commit, and no tags:
`git -C <WORKTREE> push --no-follow-tags origin <SHA>:refs/heads/<BRANCH>`.
If the output shows `[new tag]`, stop and tell the user. A tag rode along, and some repos
treat a tag push as a release.

5. Set stage `merging` and record the PR or MR URL in `url`. A `local` merge goes straight to
   `merged`. A later `/factory` command in this session flips `merging` to `merged` once the
   host has merged.

## Rework

`/factory rework <job-id> <note>`:
1. Append the note to `JOB_DIR/rework.md` under a `## <date>` heading.
2. Make sure your floor is on the job's branch (`git -C <WORKTREE> switch <branch>`, refusing
   if the floor has other work in progress).
3. If the note changes **what** gets built (scope or acceptance criteria), spawn
   `spec-writer` first. It revises `spec.md` and logs the change under `## Revisions`.
4. Record `DIFF_BASE = git -C <WORKTREE> rev-parse HEAD` for the next round.
5. `SendMessage` to `builder-<JOB>`: *"Rework requested. Read JOB_DIR/rework.md, then commit
   and rewrite build.md."* Fall back to a fresh builder, as in the job loop.
6. Set `maxRound = round + MAX_ROUNDS` and run round `round + 1`. In a run, the run is
   `running` again until the unit is accepted. Then continue with the next unit, or, if the
   run was already `pushed`, push again.

## Board files

Each one drives its part of the dashboard, which merges every file in `FACTORY/board/`.
Rewrite your whole file on every change: write `<BOARD>.tmp` (the dashboard ignores names
not ending in `.json`), then `mv` it over `BOARD`, so the dashboard never reads half a file.
Bump `updated` at the top, and on the run or job you touched.

A run's file holds the run and all of its unit jobs. A standalone job's file holds just that
job, with an empty `runs`. `plugin` is this plugin's version (from `.claude-plugin/plugin.json`
two folders above `SKILL_DIR`), so the dashboard knows what this session will do, such as
bringing the base branch in before it pushes.

```json
{
  "updated": "2026-10-20T14:40:00Z",
  "plugin": "0.8.0",
  "floor": "/abs/path/to/your/floor",
  "runs": [
    {
      "id": "0062-childrens-code-opt-in-tenant",
      "title": "ADR-0062 Opt-in consent tenants",
      "adr": "docs/0062-childrens-code-opt-in-tenant/0062-childrens-code-opt-in-tenant.md",
      "branch": "feature/0062-childrens-code-opt-in-tenant",
      "stage": "running",
      "reason": null,
      "url": null,
      "files": ["apps/payload-core/src/globals/PartnerConfig.ts", "apps/site-core/src/lib/consentConfig.ts"],
      "overlaps": [
        { "with": "0070-partner-insights", "title": "ADR-0070 Partner insights", "files": ["apps/site-core/src/lib/consentConfig.ts"] }
      ],
      "continuedFrom": null,
      "completion": null,
      "units": [
        { "unit": "U0", "title": "Tenant policy fields", "status": "done", "prior": "merged in !1144 (abc1234)" },
        { "unit": "U10", "title": "Ingest tag attribute", "status": "skipped", "reason": "lives in the meridian-ingest repo" },
        { "unit": "U1", "title": "Profiling switch", "status": "active", "job": "0062-u1-profiling-switch", "adopted": "feat/0062-profiling-switch" },
        { "unit": "U2", "title": "Retention cap", "status": "queued" }
      ],
      "updated": "2026-10-20T14:40:00Z"
    }
  ],
  "jobs": [
    {
      "id": "0062-u1-profiling-switch",
      "run": "0062-childrens-code-opt-in-tenant",
      "unit": "U1",
      "title": "Profiling switch at every write",
      "branch": "feature/0062-childrens-code-opt-in-tenant",
      "startSha": "4f1c2a9",
      "builder": "builder-0062-u1-profiling-switch",
      "stage": "review",
      "round": 2,
      "maxRound": 2,
      "reviews": { "security": "CHANGES", "ux": "PASS", "ui": "pending", "code": "PASS" },
      "history": [
        { "round": 1, "reviews": { "security": "CHANGES", "ux": "PASS", "ui": "CHANGES", "code": "PASS" } }
      ],
      "decision": null,
      "reason": null,
      "url": null,
      "files": [],
      "overlaps": [],
      "started": "2026-10-20T14:02:00Z",
      "updated": "2026-10-20T14:40:00Z"
    }
  ]
}
```

- Job `stage` is one of `spec`, `build`, `review`, `approval`, `needs-human`, `merging`,
  `merged`, or `done` (a run unit accepted onto the run's branch). A job outside a run has no
  `run` or `unit`, and keeps its own `files` and `overlaps`.
- Run `stage` is one of `planning`, `running`, `paused`, `pushed`, `merged`. A unit's `status`
  is one of `queued`, `active`, `done`, `skipped`, `ask`. A unit that was done before the run
  has `prior` (the evidence) and no job. A unit whose code came from another branch has
  `adopted` (that branch).
- A run's `continuedFrom` is the existing branch it picked up (or `null`), and its
  `completion` is `null`, `checking`, `complete` or `gaps`.
- A floor is busy while any board file with that `floor` holds a job between `spec` and
  `approval` or `needs-human`, or a run that is `planning`, `running` or `paused`.
- `reviews` is the current round, and `history` holds the finished ones. Use `decision` for
  `APPROVE`, `ESCALATE` or `HUMAN-APPROVED`.

## Rules

- Agents get their context from files, not from this conversation, and each one writes only
  its own file. You write your `BOARD`, `feature.md`, `rework.md`, and the backlog tick.
  Never write another session's board file, job folder or run folder.
- A review starts with `VERDICT: PASS` or `VERDICT: CHANGES`. `decision.md` starts with
  `APPROVE` or `ESCALATE`.
- Branches are named by the spec-writer per `PROFILE` and created by you on your floor.
  Nothing is ever named or pushed with a `factory/` prefix. The builder commits; it never
  pushes, and it never stages `factory/`. Only Merge and the end of a run push.
- WAIT FOR ALL: a round is done only when every reviewer's file exists in the round folder.
- The builder is one named agent per job (`builder-<JOB>`), resumed with `SendMessage` and
  pointed at the round folder each time. In a run, every unit gets a fresh builder.
- Heavy commands (installs, builds, typechecks, lints, test suites) run under
  `FACTORY/tests.lock`, so builders in different sessions take turns. Specs and reviews still
  run in parallel.
- One job or run per floor, and one floor per session. Overlaps between sessions are
  warnings, never stops.
