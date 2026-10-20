---
name: factory
description: Run the software factory in any repository. Takes one feature, or every unit of an ADR in build order, through spec (built on spec-author), build, four parallel reviews and approval, with every step done by a subagent and tracked on a live dashboard. Use only when the user types /factory.
argument-hint: "init | adr <ADR> | continue [answer] | <feature> | next | approve <job-id> | rework <job-id> <note>"
disable-model-invocation: true
---

# /factory: you are the orchestrator

The session running this skill is the factory's orchestrator. You run the loop below and
spawn every agent. You are the **only** writer of `board.json` and `backlog.md`, and the
only one who creates branches or pushes. You never write a spec, code, review or decision
yourself. Agents do that, one file each. If an agent fails, retry it once, then move the job
to `needs-human`. Never do its work for it.

This skill ships in the `software-factory` plugin, and the same machinery runs in every
repository. What differs per repo lives in that repo's `factory/project.md`: its stack, its
test commands, its rules, its branch names, and how it merges. Every agent reads that file
first.

The factory works in two ways:

- **A job** (`/factory <feature>`): one feature, one branch, one PR, merged per the merge mode.
- **An ADR run** (`/factory adr <ADR>`): every buildable unit of an ADR, in build order, each
  one a job on the **same** branch. When the last unit is accepted, the branch is pushed
  once and a PR opens for preview and human review. A run never auto-merges.

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
               WORKTREE=<abs>     ← the floor
               FACTORY=<abs>      ← the state folder
               JOB=<JOB>          JOB_DIR=<abs>
               RUN=<RUN>          RUN_DIR=<abs>     ← runs only
               ADR=<abs>                            ← spec-writer, MODE=plan only
               BRANCH=<branch>                      ← once it exists
               DIFF_BASE=<sha>                      ← builder, reviewers, approver
               ROUND_DIR=<abs>                      ← reviewers, and the builder on resume")
```

`MODE` is `job` for a feature, `unit` for the spec-writer on an ADR unit, `plan` for the
spec-writer planning a run, and `adr` for the builder, reviewers and approver inside a run.
Agents get their context from those files, never from this conversation.

## Knobs

| Knob | Value | Meaning |
|---|---|---|
| `MAX_ROUNDS` | 2 | Review rounds a job gets before it goes to `needs-human` |
| `REVIEWERS` | security, ux, ui, code | Role `review-<name>` writes `review-<name>.md` |

## The floor and the state folder

**The floor** (`WORKTREE`) is the one checkout where all building happens: this session's
own checkout, provided it is a **linked worktree**. Claude Code lets a worktree session edit
files only in its own worktree, so a builder in any other checkout would be refused. One job
or one run uses the floor at a time, switching its branch as it goes.

- `git rev-parse --git-dir` differs from `git rev-parse --git-common-dir`: this session is
  in a linked worktree, so it is the floor.
- They're the same: this session is on the repo's **main checkout**, and the factory never
  switches that checkout's branch. Create `<ROOT>/.claude/worktrees/factory` if it doesn't
  exist (`git -C <ROOT> worktree add --detach <path> <BASE_REF>`), load `EnterWorktree` with
  ToolSearch, and enter it **before spawning any agent**. That is the floor from now on. If
  `EnterWorktree` isn't available, stop and tell the user to open a session in that folder.

Before work starts on the floor, it must have no changes outside `factory/`
(`git status --porcelain -- . ':!factory'` prints nothing). Otherwise stop, and say what's
uncommitted.

**The state folder** (`FACTORY`) is `~/.factory/<repo>/`, outside every checkout, so any
session can read it and any agent can write its file there. It holds `board.json`,
`backlog.md`, `dashboard.html`, `jobs/` and `runs/`. The repo keeps only `factory/project.md`
and `factory/README.md`.

| Name | Value |
|---|---|
| `SKILL_DIR` | this skill's base directory, shown when the skill loads (inside the plugin's install folder) |
| `ROOT` | the repo's main checkout: `dirname "$(git rev-parse --path-format=absolute --git-common-dir)"` |
| `<repo>` | `basename <ROOT>` |
| `WORKTREE` | the floor (above) |
| `FACTORY` | `~/.factory/<repo>` (absolute) |
| `PROFILE` | `<WORKTREE>/factory/project.md` |
| `BASE` | the base branch from `PROFILE` Settings, normally `main`. `BASE_REF` is `origin/<BASE>`, or `<BASE>` when Host is `none` |
| `JOB` | `NNN-slug`: the next number after the highest one in `FACTORY/jobs/` (starting at `001`). For a run unit, the slug is `<adr number>-<unit id>-<2 words>`, for example `007-0062-u0-tenant-policy` |
| `JOB_DIR` | `FACTORY/jobs/<JOB>` |
| `RUN` | the ADR's file or folder name, for example `0062-childrens-code-opt-in-tenant` |
| `RUN_DIR` | `FACTORY/runs/<RUN>` |
| `BRANCH` | named by the spec-writer, following `PROFILE`'s Branch names rule. **Never** a `factory/` prefix. |
| `DIFF_BASE` | the commit the job or unit started from. Reviewers diff `DIFF_BASE..HEAD`, so in a run they see only this unit's work. |
| `ROUND_DIR` | `JOB_DIR/round-<N>` |

## Commands

Parse `$ARGUMENTS`:

| Input | Do |
|---|---|
| `init` | Run **Setup**, even if `PROFILE` already exists (it is replaced). |
| `adr <ADR>` | Start an **ADR run**. `<ADR>` is a path to the ADR file or its folder, or just its number (find `docs/**/<number>*`). |
| `continue [answer]` | Resume the active run (see **Continuing a run**). |
| `next` | Take the first `- [ ]` line in `FACTORY/backlog.md`, tick it (`- [x] <text> → <JOB>`), and run it as a new job. If none is left, say so and stop. |
| `approve <job-id>` | The job must be in `needs-human`. For a job, go to **Merge**. For a run unit, accept it (step 6 of the run) and continue the run. |
| `rework <job-id> <note>` | Go to **Rework**. |
| anything else | The text is a feature. Run a new **job**. |

Before any command:
1. Settle the floor (above).
2. If `PROFILE` doesn't exist, run **Setup** and stop there.
3. Copy `SKILL_DIR/assets/dashboard.html` over `FACTORY/dashboard.html` if they differ.
4. Tidy up once: for each job in `merging` or run in `pushed`, check its PR or MR
   (`gh pr view <url> --json state` or `glab mr view <url> -F json`). If it is merged, set
   `merged`. Do this once per run. Never poll.
5. The floor holds one thing at a time. Refuse to start a job or a run while a run is
   `running` or `paused`, or a job is still between `spec` and `approval`. Finish or continue
   that first.

The first time in a session, tell the user where to watch:
`cd ~/.factory/<repo> && python3 -m http.server 8765`, then open
<http://localhost:8765/dashboard.html>.

## Setup

1. Create `FACTORY` from `SKILL_DIR/assets/`: copy `dashboard.html`, `backlog.md` and
   `board.json` (skip any that already exist, except `dashboard.html`), and create `jobs/` and
   `runs/`. Set `board.json`'s `floor` to `WORKTREE`.
2. Copy `SKILL_DIR/assets/README.md` to `WORKTREE/factory/README.md`. Spawn the `surveyor`. It
   inspects the repo and writes `PROFILE`.
3. Copy the project's name, host and merge mode from `PROFILE` Settings into `board.json`'s
   `project` block.
4. Show the user the Settings table, and say in a line what the merge mode and the branch
   rules mean for them. Then stop and ask them to read `factory/project.md` (and commit it,
   so teammates share it) before the first job. It governs what gets run, what gets pushed,
   and what gets merged.

## The job loop (shared by jobs and run units)

**Spec.** Spawn `spec-writer` (`MODE=job`, or `MODE=unit` in a run). When it finishes,
`spec.md` must exist. Copy its `# … — <feature>` title into the board's `title`, and set stage
`build`.

**Build.** Spawn `builder` with `name: builder-<JOB>`, and record that name in the board's
`builder` field. If your Agent tool has no `name` input, record the agent ID it returns and
address the builder by that ID. When it finishes, `build.md` must exist and start with no
`BLOCKED:` line. Go to round 1.

**Review round N: WAIT FOR ALL.**
1. `mkdir ROUND_DIR`. Set `stage: review`, `round: N`, and all four reviews to `pending`.
2. Spawn all four reviewers **in a single message**, so they run in parallel.
3. Each time one finishes, read the first line of its file and update its chip on the
   board right away. The dashboard fills in as verdicts land.
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

1. **Start.** Put the floor on a fresh base, with **no branch yet**, so nothing is named
   before the spec names it:
   ```bash
   git -C <WORKTREE> fetch origin <BASE>          # skip when Host is none
   git -C <WORKTREE> switch --detach <BASE_REF>
   mkdir -p "<JOB_DIR>"
   ```
   Record `git -C <WORKTREE> rev-parse HEAD` on the job as `startSha` (its `DIFF_BASE`).
   Write the feature text, verbatim, to `JOB_DIR/feature.md`. Add the job to the board at
   stage `spec`.
2. **Spec** (`MODE=job`).
3. **Name the branch.** Read `**Branch:**` from `spec.md`. Refuse it, and set `needs-human`,
   if it breaks `PROFILE`'s Branch names rule, starts with `factory/`, or already exists
   (`git -C <WORKTREE> show-ref --verify refs/heads/<name>`, or
   `git -C <WORKTREE> ls-remote --exit-code --heads origin <name>`). Otherwise run
   `git -C <WORKTREE> switch -c <name>` and record it as the job's `branch`.
4. **Build, review and approve** (`MODE=job`) as in the job loop.

## Running an ADR

`/factory adr <ADR>` works through every buildable unit of the ADR, in order, on one branch.

1. **Start the run.** Resolve the ADR path and `RUN`. Put the floor on a fresh base with no
   branch, as in step 1 of a job. `mkdir -p <RUN_DIR>`. Add the run to the board at stage
   `planning`, with no units yet.
2. **Plan.** Spawn `spec-writer` with `MODE=plan`, `ADR` and `RUN_DIR`. It writes
   `RUN_DIR/plan.md`: every unit in build order, each one marked `build`, `skip:` or `ask:`.
3. **Name the branch.** Read `**Branch:**` from `plan.md`, check it as in step 3 of a job
   (it must follow `PROFILE`'s rule for ADR runs), then `git -C <WORKTREE> switch -c <name>`.
   Fill in the run's `branch` and its units in plan order (see **board.json**), and set
   stage `running`.
4. **For each unit in plan order:**
   - `skip:` units are marked `skipped` and never built.
   - `ask:` units stop the run: set the run `paused`, its `reason` to the question, and tell
     the user to answer with `/factory continue <answer>`.
   - `build` units become a job. Create `JOB` and `JOB_DIR`, then write `feature.md` as
     *"Unit <id> of <ADR>: <title>. Source: <source>. Adopt it; don't rewrite it."*, plus
     any answer the user gave. Set the job's `run`, `unit` and `branch`, and record
     `startSha = git -C <WORKTREE> rev-parse HEAD` as its `DIFF_BASE`. Mark the unit
     `active`.
5. **Run the job loop** for that unit: spec (`MODE=unit`), then build, review and approve
   (`MODE=adr`). Units run one at a time on the floor, each on top of the last.
6. **Accept the unit** on `APPROVE` (or `/factory approve`). `git -C <WORKTREE> rev-parse
   HEAD` must equal `decision.md`'s `Reviewed-SHA:` (or, after a human approve, be recorded
   as the reviewed commit). Set the job's stage `done`, the unit `done`, and go on to the next
   unit. Never start a unit on top of an unreviewed commit.
7. **When every `build` unit is done, push and open the preview PR:**
   - `git -C <WORKTREE> log --oneline <BASE_REF>..HEAD` must contain only the run's units.
   - Push exactly HEAD, and no tags:
     `git -C <WORKTREE> push --no-follow-tags -u origin HEAD:refs/heads/<BRANCH>`.
     If the output shows `[new tag]`, stop and tell the user.
   - Open the PR or MR **without auto-merge**, as a draft if `PROFILE` says so for ADR runs:
     `glab mr create --source-branch <BRANCH> --target-branch <BASE> --title "<title>"
     --description "<body>" [--draft] --yes`, or `gh pr create --base <BASE> --head <BRANCH>
     --title "<title>" --body "<body>" [--draft]`.
   - The title is `plan.md`'s `**PR title:**`. The body contains:
     - a link to the ADR;
     - a table of every unit with its outcome (done, with its job id; or skipped, with the
       reason);
     - every approver's **Flags for the PR reviewer**;
     - the plan's **Rollout gates**;
     - one line on how to reach the preview, if `PROFILE` describes one.

     Add no AI attribution lines.
   - Set the run `pushed` with its `url`, and tell the user the PR link and where the preview
     will appear.

**After the push**, `/factory rework <job-id> <note>` still works on a run unit: the builder
commits on top of the branch, the unit is reviewed again from that commit, and when it is
accepted you push again (fast-forward only, with the same command). The PR and its preview
update themselves.

## Continuing a run

`/factory continue [answer]` picks the active run back up, whether it paused on a question,
or the session ended or was compacted mid-run. The run must continue on the floor recorded
in `board.json`. If this session's checkout isn't that floor, enter it with `EnterWorktree`
before anything else (or ask the user to open a session there).

- Paused on an `ask:` unit: append the answer to that unit's job `feature.md` (create the job
  as in step 4 if it doesn't exist yet) and build it.
- Paused on a `needs-human` job: say so, and point at `/factory approve` or
  `/factory rework` for that job. Do nothing else.
- Interrupted: read `board.json` and the job folders, and resume the unit at its recorded
  stage. If a stage's file is missing, re-run that stage's agent. A builder resumes as a fresh
  `builder-<JOB>`, rebuilding its context from the files.

## Merge (jobs only)

Used both after `APPROVE` and for `/factory approve <job-id>` on a job. Follow `PROFILE`
wherever it says something more specific than this section.

1. Set `SHA` to `git -C <WORKTREE> rev-parse HEAD`. If the approver approved, `SHA` must
   equal the `Reviewed-SHA:` line in `decision.md`. If it doesn't, stop and set
   `needs-human` with the reason "branch moved after approval".
2. `git -C <WORKTREE> log --oneline <BASE_REF>..<SHA>` must list only this job's commits.
3. Ship it according to the merge mode in `PROFILE` Settings. The title is the `PR title:`
   line from `spec.md`. The body is the one-paragraph summary from `spec.md`, its acceptance
   criteria, each round's verdicts, and the decision (or "approved by a human with
   /factory approve"). Add no AI attribution lines.

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

4. Set stage `merging` and record the PR or MR URL in `url`. A `local` merge goes straight to
   `merged`. The next `/factory` run flips `merging` to `merged` once the host has merged.

## Rework

`/factory rework <job-id> <note>`:
1. Append the note to `JOB_DIR/rework.md` under a `## <date>` heading.
2. Make sure the floor is on the job's branch (`git -C <WORKTREE> switch <branch>`, refusing
   if the floor has other work in progress).
3. If the note changes **what** gets built (scope or acceptance criteria), spawn
   `spec-writer` first. It revises `spec.md` and logs the change under `## Revisions`.
4. Record `DIFF_BASE = git -C <WORKTREE> rev-parse HEAD` for the next round.
5. `SendMessage` to `builder-<JOB>`: *"Rework requested. Read JOB_DIR/rework.md, then commit
   and rewrite build.md."* Fall back to a fresh builder, as in the job loop.
6. Set `maxRound = round + MAX_ROUNDS` and run round `round + 1`. In a run, the run is
   `running` again until the unit is accepted. Then continue with the next unit, or, if the
   run was already `pushed`, push again.

## board.json

It drives the dashboard. Rewrite the whole file on every change: write
`board.json.tmp`, then `mv` it over `board.json`, so the dashboard never reads half a file.
Bump `updated` at the top, and on every job or run you touch.

```json
{
  "updated": "2026-10-20T14:40:00Z",
  "floor": "/abs/path/to/the/floor",
  "project": { "name": "Acme", "host": "gitlab", "merge": "auto-merge" },
  "runs": [
    {
      "id": "0062-childrens-code-opt-in-tenant",
      "title": "ADR-0062 Opt-in consent tenants",
      "adr": "docs/0062-childrens-code-opt-in-tenant/0062-childrens-code-opt-in-tenant.md",
      "branch": "feature/0062-childrens-code-opt-in-tenant",
      "stage": "running",
      "reason": null,
      "url": null,
      "units": [
        { "unit": "U0", "title": "Tenant policy fields", "status": "done", "job": "007-0062-u0-tenant-policy" },
        { "unit": "U10", "title": "Ingest tag attribute", "status": "skipped", "reason": "lives in the meridian-ingest repo" },
        { "unit": "U1", "title": "Profiling switch", "status": "active", "job": "008-0062-u1-profiling-switch" },
        { "unit": "U2", "title": "Retention cap", "status": "queued" }
      ],
      "updated": "2026-10-20T14:40:00Z"
    }
  ],
  "jobs": [
    {
      "id": "008-0062-u1-profiling-switch",
      "run": "0062-childrens-code-opt-in-tenant",
      "unit": "U1",
      "title": "Profiling switch at every write",
      "branch": "feature/0062-childrens-code-opt-in-tenant",
      "startSha": "4f1c2a9",
      "builder": "builder-008-0062-u1-profiling-switch",
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
      "started": "2026-10-20T14:02:00Z",
      "updated": "2026-10-20T14:40:00Z"
    }
  ]
}
```

- Job `stage` is one of `spec`, `build`, `review`, `approval`, `needs-human`, `merging`,
  `merged`, or `done` (a run unit accepted onto the run's branch). A job outside a run has no
  `run` or `unit`.
- Run `stage` is one of `planning`, `running`, `paused`, `pushed`, `merged`. A unit's `status`
  is one of `queued`, `active`, `done`, `skipped`, `ask`.
- `reviews` is the current round, and `history` holds the finished ones. Use `decision` for
  `APPROVE`, `ESCALATE` or `HUMAN-APPROVED`.

## Rules

- Agents get their context from files, not from this conversation, and each one writes only
  its own file. You write `board.json`, `backlog.md`, `feature.md` and `rework.md`.
- A review starts with `VERDICT: PASS` or `VERDICT: CHANGES`. `decision.md` starts with
  `APPROVE` or `ESCALATE`.
- Branches are named by the spec-writer per `PROFILE` and created by you on the floor. Nothing
  is ever named or pushed with a `factory/` prefix. The builder commits; it never pushes, and
  it never stages `factory/`. Only Merge and the end of a run push.
- WAIT FOR ALL: a round is done only when every reviewer's file exists in the round folder.
- The builder is one named agent per job (`builder-<JOB>`), resumed with `SendMessage` and
  pointed at the round folder each time. In a run, every unit gets a fresh builder.
- Only one heavy process runs at a time. The builder runs tests, and reviewers read the
  diff. The floor holds one job or one run at a time.
