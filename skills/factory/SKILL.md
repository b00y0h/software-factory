---
name: factory
description: Run the software factory in any repository. Takes one feature through spec (built on spec-author), build, four parallel reviews, approval and merge, with every step done by a subagent and tracked in factory/board.json with a live dashboard. Use only when the user types /factory.
argument-hint: "init | <feature> | next | approve <job-id> | rework <job-id> <note>"
disable-model-invocation: true
---

# /factory: you are the orchestrator

The session running this skill is the factory's orchestrator. You run the loop below and
spawn every agent. You are the **only** writer of `factory/board.json` and
`factory/backlog.md`, and the only one who pushes. You never write a spec, code, review or
decision yourself. Agents do that, one file each. If an agent fails, retry it once, then
move the job to `needs-human`. Never do its work for it.

This skill ships in the `software-factory` plugin, and the same machinery runs in every
repository. What differs per repo lives in that repo's `factory/project.md`: its stack, its
test commands, its rules, and how it merges. Every agent reads that file first.

## The loop (edit this to change the factory)

```
                   ┌──────────────────┐
                   │     feature      │
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
              ┌─────────────┐ ┌─────────────┐
              │merge to main│ │ needs-human │ ◄── /factory approve
              └─────────────┘ └─────────────┘
```

## Roles

Every role is a subagent in this plugin's `agents/` folder. Its file sets its model and the
tools it may use, so reviewers and the approver cannot edit code: they have no Edit tool.

| Role | `subagent_type` | Model | Writes |
|---|---|---|---|
| surveyor | `software-factory:surveyor` | opus | `factory/project.md` (only at init) |
| spec-writer | `software-factory:spec-writer` | opus | `spec.md` |
| builder | `software-factory:builder` | opus | code on the job branch, plus `build.md` |
| review-security | `software-factory:review-security` | opus | `round-N/review-security.md` |
| review-ux | `software-factory:review-ux` | sonnet | `round-N/review-ux.md` |
| review-ui | `software-factory:review-ui` | sonnet | `round-N/review-ui.md` |
| review-code | `software-factory:review-code` | sonnet | `round-N/review-code.md` |
| approver | `software-factory:approver` | opus | `decision.md` |

The spec-writer is the spec-author skill folded in. Its templates are in this skill's
`spec-author/` folder.

Spawn every agent the same way. The prompt is only paths:

```
Agent(subagent_type: "software-factory:<role>", description: "<role> <JOB>",
      [name: "builder-<JOB>"  ← the builder only],
      prompt: "SKILL_DIR=<abs>
               ROOT=<abs>
               FACTORY=<abs>
               JOB=<JOB>
               JOB_DIR=<abs>
               BRANCH=<BRANCH>
               BASE_REF=<origin/BASE, or BASE when Host is none>
               WORKTREE=<abs>
               ROUND_DIR=<abs>   ← reviewers, and the builder on resume")
```

Agents get their context from those files, never from this conversation.

## Knobs

| Knob | Value | Meaning |
|---|---|---|
| `MAX_ROUNDS` | 2 | Review rounds a job gets before it goes to `needs-human` |
| `REVIEWERS` | security, ux, ui, code | Role `review-<name>` writes `review-<name>.md` |

## Names and paths

| Name | Value |
|---|---|
| `SKILL_DIR` | this skill's base directory, shown when the skill loads (inside the plugin's install folder) |
| `ROOT` | the main checkout of the current repo: `dirname "$(git rev-parse --path-format=absolute --git-common-dir)"` |
| `FACTORY` | `<the current checkout>/factory` |
| `BASE` | the base branch from `project.md` Settings, normally `main` |
| `JOB` | `NNN-slug`: the next number after the highest one in `factory/jobs/` (starting at `001`), plus a kebab-case slug of at most 4 words |
| `JOB_DIR` | `FACTORY/jobs/<JOB>` |
| `BRANCH` | `factory/<JOB>` |
| `WORKTREE` | `<worktree root from project.md>/<JOB>`, the builder's checkout of `BRANCH` |
| `ROUND_DIR` | `JOB_DIR/round-<N>` |

## Commands

Parse `$ARGUMENTS`:

| Input | Do |
|---|---|
| `init` | Run **Setup**, even if `factory/` already exists (the existing `project.md` is replaced). |
| `next` | Take the first `- [ ]` line in `backlog.md`, tick it (`- [x] <text> → <JOB>`), and run it as a new job. If none is left, say so and stop. |
| `approve <job-id>` | The job must be in `needs-human`. Go to **Merge**. |
| `rework <job-id> <note>` | Go to **Rework**. |
| anything else | The text is a feature. Run a new job. |

Before any command:
1. If `factory/project.md` doesn't exist, run **Setup** and stop there.
2. Copy `SKILL_DIR/assets/dashboard.html` over `factory/dashboard.html` if they differ.
3. Tidy up once: for each job in `merging`, check its PR or MR (`gh pr view <url> --json state`
   or `glab mr view <url> -F json`). If it is merged, set the stage to `merged` and run
   `git worktree remove <WORKTREE>`. Do this once per run. Never poll.

The first time in a session, tell the user where to watch:
`cd factory && python3 -m http.server 8765`, then open <http://localhost:8765/dashboard.html>.

## Setup

1. Create `factory/` from `SKILL_DIR/assets/`: copy `dashboard.html`, `README.md`,
   `backlog.md` and `board.json` (skip any that already exist, except `dashboard.html`),
   and create `factory/jobs/`.
2. Spawn the `surveyor`. It inspects the repo and writes `factory/project.md`.
3. Copy the project's name, host and merge mode from `project.md` Settings into `board.json`'s
   `project` block.
4. Show the user the Settings table, and say in a line what the merge mode means for them.
   Then stop and ask them to read `factory/project.md` before the first job. It governs what
   gets run and what gets merged.

## Running a job

**1. Start.** Branch from a fresh `BASE` in a worktree of its own, so the job never touches
this checkout's branch:

```bash
git -C <ROOT> fetch origin <BASE>          # skip when Host is none
git -C <ROOT> worktree add -b "factory/<JOB>" "<WORKTREE>" origin/<BASE>   # <BASE> when Host is none
mkdir -p "<JOB_DIR>"
```

Write the feature text, verbatim, to `JOB_DIR/feature.md`. Add the job to the board at
stage `spec`.

**2. Spec.** Spawn `spec-writer`. When it finishes, `spec.md` must exist. Copy its
`# … — <feature>` title into the board's `title`, and set stage `build`.

**3. Build.** Spawn `builder` with `name: builder-<JOB>`, and record that name in the board's
`builder` field. If your Agent tool has no `name` input, record the agent ID it returns
and address the builder by that ID. When it finishes, `build.md` must exist. Go to round 1.

**4. Review round N: WAIT FOR ALL.**
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
| All four PASS | Step 5 |
| Any CHANGES, and `N < maxRound` | Move this round into `history` and set stage `build`. Then `SendMessage` to `builder-<JOB>`: *"Round N reviews are in ROUND_DIR. Address every CHANGES item, commit, and rewrite build.md."* When it finishes, run round N+1. |
| Any CHANGES, and `N = maxRound` | Set `needs-human` with `reason: "Review rounds used up: <reviewers still asking for CHANGES>"`. |

`SendMessage` may be a deferred tool; load it with ToolSearch (`select:SendMessage`) before
the first resume. If it cannot reach the builder (for example, this is a new session), spawn a
fresh `builder` with the same name. It rebuilds its context from the job folder, which is
why everything lives in files.

**5. Approve.** Set stage `approval` and spawn `approver`. Read the first line of
`decision.md`:
- `APPROVE`: go to **Merge**.
- `ESCALATE`, or anything else: set `needs-human`, and copy its `Reason:` line into `reason`.

## Merge

Used both after `APPROVE` and for `/factory approve <job-id>`. Follow `project.md` wherever it
says something more specific than this section.

1. Set `SHA` to `git -C <WORKTREE> rev-parse HEAD`. If the approver approved, `SHA` must
   equal the `Reviewed-SHA:` line in `decision.md`. If it doesn't, stop and set
   `needs-human` with the reason "branch moved after approval".
2. `git -C <WORKTREE> log --oneline <BASE_REF>..<SHA>` must list only this job's commits.
3. Ship it according to the merge mode in `project.md` Settings. The title is the
   `PR title:` line from `spec.md`. The body is the one-paragraph summary from `spec.md`, its
   acceptance criteria, each round's verdicts, and the decision (or "approved by a human
   with /factory approve"). Add no AI attribution lines.

| Mode | Host | Do |
|---|---|---|
| `auto-merge` | gitlab | Push (below), then `glab mr create --source-branch <BRANCH> --target-branch <BASE> --title "<title>" --description "<body>" --auto-merge --remove-source-branch --yes` |
| `auto-merge` | github | Push, then `gh pr create --base <BASE> --head <BRANCH> --title "<title>" --body "<body>"`, then `gh pr merge <url> --auto --match-head-commit <SHA>` plus the strategy flag from `project.md` (default `--merge`) |
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
2. If the note changes **what** gets built (scope or acceptance criteria), spawn
   `spec-writer` first. It revises `spec.md` and logs the change under `## Revisions`.
3. `SendMessage` to `builder-<JOB>`: *"Rework requested. Read JOB_DIR/rework.md, then commit
   and rewrite build.md."* Fall back to a fresh builder as described in step 4.
4. Set `maxRound = round + MAX_ROUNDS` and run round `round + 1`.

## board.json

It drives the dashboard. Rewrite the whole file on every change: write
`board.json.tmp`, then `mv` it over `board.json`, so the dashboard never reads half a file.
Bump `updated` both at the top and on the job.

```json
{
  "updated": "2026-10-20T14:40:00Z",
  "project": { "name": "Acme", "host": "github", "merge": "auto-merge" },
  "jobs": [
    {
      "id": "003-rate-limiting",
      "title": "Rate-limit the public form submit endpoint",
      "branch": "factory/003-rate-limiting",
      "worktree": "/abs/path/003-rate-limiting",
      "builder": "builder-003-rate-limiting",
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

`stage` is one of `spec`, `build`, `review`, `approval`, `needs-human`, `merging`, `merged`.
`reviews` is the current round, and `history` holds the finished ones. Use `decision` for
`APPROVE`, `ESCALATE` or `HUMAN-APPROVED`.

## Rules

- Agents get their context from files, not from this conversation, and each one writes only
  its own file. You write `board.json`, `backlog.md`, `feature.md` and `rework.md`.
- A review starts with `VERDICT: PASS` or `VERDICT: CHANGES`. `decision.md` starts with
  `APPROVE` or `ESCALATE`.
- The builder works and commits on `factory/<JOB>`, in its worktree, and tests against the
  spec's acceptance criteria. It never pushes. Only Merge pushes.
- WAIT FOR ALL: a round is done only when every reviewer's file exists in the round folder.
- The builder is one named agent per job (`builder-<JOB>`), resumed with `SendMessage` and
  pointed at the round folder each time.
- Only one heavy process runs at a time. The builder runs tests, and reviewers read the
  diff.
