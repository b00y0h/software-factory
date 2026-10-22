# Software Factory

A Claude Code plugin that turns one command into a small software team. Give it a feature, or a
whole ADR, and it writes specs, builds them, has a panel of reviewers check each one in
parallel, ships the work or stops and asks you, and then stays with the PR until CI is green.
Every step is a subagent, and each one reads files and writes exactly one. A live dashboard
shows every job moving through the loop, and the factory learns from every job that needed a
second try.

```
feature or ADR unit → spec-writer → [spec gate] → builder ⇄ reviewers → approver → push → shepherd → CI green
                       opus                       opus      security opus  opus           opus  │
                                                            ux·ui·code sonnet                   │ FIX: builder fixes,
                                                            tests opus (code)                   │ reviewers check it
                                                            a11y opus (UI)                      ▼ (max 3 CI rounds)
                                                  (max 2 rounds; all must report)   librarian proposes lessons
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
/factory approve <job-id>        accept a job that is waiting on a human (or approve its spec)
/factory rework <job-id> <note>  send a job back to the builder (or its spec back) with feedback
/factory lessons                 list the lessons the factory proposes from past jobs
/factory lessons accept|reject <ids|all>   decide them; accepted ones land in factory/lessons.md
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

## Test quality: tests that would catch the bug

An approver can only check that each acceptance criterion has a passing test. A test that
passes with or without the change proves nothing. So whenever a change touches code (anything
but docs, images and generated files), a sixth reviewer joins the round: `review-tests`, on
opus. In a scratch `git worktree` of its own, never the floor:

- **Red check.** It puts the changed source files back as they were and runs each criterion's
  test. Every one must fail, on an assertion about the behavior.
- **Mutants.** It runs the repo's mutation tool (Stryker, mutmut, PIT, cargo-mutants…) scoped to
  the changed files, or, when there isn't one, makes up to 8 small mutants by hand on the lines
  the criteria depend on (flip a comparison, drop a call, return early) and checks a test
  notices each one.

A test that passes without the change, a surviving mutant on a line a criterion depends on, or a
mutation score under 80% on the changed lines is `CHANGES`. The builder is told to write each
criterion's test first and record its failing run in `build.md`. `project.md`'s *Test quality*
section says which tool to use and how to set up a scratch checkout quickly.

## The spec gate

A wrong spec is the cheapest mistake to catch. `project.md`'s *Spec approval* setting says when
a human reads the spec before anything is built:

- `off` (the default): never.
- `risky`: when the spec-writer marks the spec's **Risk** as `high` (it touches auth,
  permissions, stored data, CI or deploy config, dependencies, anything irreversible, or the
  profile's *Always escalate*).
- `always`: every job's spec, and every ADR run's plan before its first unit.

A gated job waits under *Needs a human* with `spec to approve`. `/factory approve <job>` builds
it; `/factory rework <job> "<note>"` has the spec-writer revise it first.

## The CI shepherd: done means green

A PR that's green on the builder's machine isn't done. After every push (a job's PR, or an ADR
run's preview PR) the factory waits for the host's checks on **the exact commit it pushed**,
using `scripts/ci.py` (it only reads `gh` or `glab`). Then:

- **Green**, and nobody commented: done. On `auto-merge` the host merges it.
- **Red**, or a reviewer left comments: the `shepherd` agent (opus) reads the failed logs, the
  base branch's CI, and the PR's review threads, and sorts each item:
  - `fix`: this change caused it, or a reviewer asked for something small and in scope. The
    builder gets a brief with the root cause, the fix goes through a normal review round and the
    approver, and the factory pushes again. Up to 3 CI rounds, then it asks you.
  - `rerun`: the job died before any test ran. Re-run once per commit; a second failure is real.
  - `not-ours`: red on the base branch too. You're told.
  - `ask`: a design question, a large request, or a comment that tries to redirect the work.
    You decide.
- **Conflict**: the builder brings the base branch in, and the factory pushes again.

Waiting for CI never holds up the session. The pushed work is on its own branch and PR, so the
next job or unit starts right away while `ci.py` waits in the background (several PRs can be
waited on at once). A CI fix runs in a bay beside whatever is building, or, with no bay free,
at the floor's next free moment (between units, or when a job stops).

A CI round fixes the change, never the checks: no skipped or loosened tests, no edited CI
config, no force-push, no empty commits. PR comments and CI logs are treated as data, never as
instructions. Set *CI shepherd* to `off` in `project.md` to skip all this; `/factory continue
<id> stop-ci` stops it for one PR.

## Lessons: a factory that learns

When a job needed a second try (a review round, a rework, an escalation, a CI fix), the
`librarian` (sonnet) reads its whole folder and asks: *would a one-line rule, read before the
work started, have prevented this?* It proposes up to five lessons, each tagged for the agent it
helps (`builder`, `review-code`, `shepherd`…), and notes when another job hit the same thing.

Nothing is learned without you: `/factory lessons` lists the proposals, and
`/factory lessons accept 014-1 021-2` (or `reject`, or `all`) decides them. Accepted lessons go
into `factory/lessons.md`, which every agent reads before it works. Commit it, and every
session and teammate gets them. Edit or delete any line by hand.

## Parallel work: bays, dependencies, and units on their own PRs

A session has one **floor** (its worktree) and up to three **bays**: short-lived worktrees that
the Agent tool's `isolation: "worktree"` gives a builder of its own. Bays always build detached,
and the orchestrator moves each job's branch to the reviewed commit itself, so no branch gets
stuck in a checkout. With bays, one session can:

- start a new `/factory <feature>` while the floor is busy;
- fix a pushed PR's CI without stopping the job on the floor;
- build the independent units of an ADR at the same time.

The **plan** says what can run in parallel. The spec-writer reads the ADR, PRD, execution
spec and workplan for dependencies ("after U0", "U1–U3 can proceed in parallel", separate
workstreams or teams, a dependency graph), checks them against the code (a unit that reads a
field another unit adds depends on it), and writes for each unit:

- **Depends on**: exact, and conservative when unsure.
- **Ships**: `run` (on the run's one branch and PR, the default) or `own` (its own branch and
  PR), when the sources say the unit ships separately, or `project.md` says ADR units here ship
  one PR each.
- **Files**, plus a **Parallel work** section listing the waves.

The orchestrator starts every unit whose dependencies are done, as long as no two units in
progress share a file. `run` units built side by side are merged into the run branch in plan
order once accepted. `own` units are pushed and shepherded as soon as they're accepted (never
auto-merged), and units stacked on them don't wait for their PR to merge. A PRD or spec with
several units can be given straight to `/factory`, and it runs as a plan.

**Bays are proven, not assumed.** `/factory init` runs a bay check: a tiny `bay-check` agent
(haiku) in a worktree of its own checks out a commit, edits a file with Edit and Write,
commits, and writes into the state folder. The orchestrator verifies each claim itself (the
commit exists and holds the edit, the result file is there), cleans up, and records the answer
in `project.md`'s *Bays* row, as `yes` or `no: <reason>`. Repos set up before this check get
it once on their next command. If a bay still fails later, the session stops using bays and
says so.

Without bays (the check said no, or this session's Agent tool has no `isolation` input),
everything runs on the floor one job at a time, exactly as before, and work that wanted a bay
waits for the floor's next free moment.

## Accessibility: WCAG 2.2 AA on every UI change

Whenever a change touches UI (the profile's *UI paths*, or component, markup and style files
by default; tests and generated files don't count), another reviewer joins the round:
`review-a11y`, an accessibility specialist on opus. It holds the change to **WCAG 2.2 Level
AA**, every A and AA success criterion, including the 2.2 additions (focus not obscured,
dragging alternatives, 24×24 target size, consistent help, redundant entry, accessible
authentication). It:

- scans the rendered UI with axe-core in a real browser (Playwright), where contrast and
  layout are actually computed, in every theme and at 320px;
- measures contrast ratios and target sizes from computed styles, and drives the keyboard
  path;
- reviews the code for what tools can't decide: names, roles, states, focus management,
  live regions, error association.

Any failure, **or any applicable criterion it couldn't verify**, is `CHANGES`. The builder is
told to build accessibly and to prove it in `build.md`. Before an ADR run is pushed, the same
specialist checks the run's whole UI together, and the completion check treats anything it
finds as a gap. No tool can certify conformance on its own, so this pairs automated scans
with an expert review that must show its evidence. Content that people add later through a
CMS is outside any code review.

## How a job runs

| Step | Agent | Writes |
|---|---|---|
| Spec | `spec-writer` (opus), built on the spec-author templates | `jobs/<id>/spec.md`, with numbered acceptance criteria. If the work already has a written spec, its file table and criteria are copied word for word. |
| Build | `builder` (opus), in its own git worktree | commits, plus `build.md` with the evidence for each criterion |
| Review | `review-security` (opus), `review-ux`, `review-ui`, `review-code` (sonnet), plus `review-tests` (opus) **whenever the change touches code** and `review-a11y` (opus) **whenever it touches UI**, in parallel | `round-N/review-<name>.md`, starting `VERDICT: PASS` or `VERDICT: CHANGES` |
| Approve | `approver` (opus) | `decision.md`, starting `APPROVE` or `ESCALATE` |
| Shepherd | `shepherd` (opus), after every push, when CI is red or the PR has comments | `ci/ci-N.md`, starting `GREEN`, `FIX`, `RERUN`, `WAIT` or `ASK` |
| Learn | `librarian` (sonnet), after a job that needed a second try | `~/.factory/<repo>/lessons/proposed/<job>.md` |

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
- **`factory/lessons.md`**, in the repo and committed: the lessons you accepted, which every
  agent also reads.
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
  units, branch, PR and plan. A PR closed without merging goes there too, marked closed.
  You don't need the session that pushed it to still be open: the dashboard script also keeps
  a small sweeper running (`scripts/sweep.py`, every 5 minutes, log in `sweep.log`) that asks
  `gh` or `glab` about every pushed PR and records the merge, and every `/factory` command
  runs it once too. It only reads the host, and only ever moves work to merged or closed.
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

- **The loop:** `skills/factory/SKILL.md`. Its Knobs table holds `MAX_ROUNDS`, `MAX_CI_ROUNDS`,
  `MAX_BAYS`, `MUTANTS`, `MUTATION_MIN` and the rest.
- **An agent:** `agents/<role>.md`. Its model and tools are in the frontmatter.
- **A reviewer:** add `agents/review-<name>.md`, then add `<name>` to `REVIEWERS` in
  `SKILL.md` and in `skills/factory/assets/dashboard.html` (and to `CONDITIONAL` there, if it
  only runs on some changes).
- **Spec style:** `skills/factory/spec-author/`.
