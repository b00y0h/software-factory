# Clarifying Question Banks

Before writing, identify which of these you **cannot** answer from the repo or the conversation, and ask only those — batched into one round. Skip any the codebase already answers. Never silently guess a blocking input.

Use the `AskUserQuestion` tool when the answer is a choice among discrete options; ask in prose when it's open-ended. If the user says "just draft it," proceed and record every assumption in the doc's `OPEN QUESTIONS` / `Locked Decisions` / deferred notes so it's reviewable.

---

## PRD

Blocking (ask if unknown — you'd otherwise fabricate):

1. **Problem & users.** What's broken today, and for whom? What's the current painful workflow?
2. **Success definition.** How will we know it worked? What's observably true when it ships? (Drives SUCCESS CRITERIA.)
3. **Scope boundary.** What is explicitly *out* of scope for v1? (Drives "What This Is NOT".)
4. **Locked decisions.** Which choices are already settled and not up for debate?

Often derivable from repo (check before asking):

5. Data model — what entities/collections exist that this touches? (Read the schema.)
6. Stack & constraints — framework, DB, hosting, multi-tenancy. (Read `package.json`, config, CLAUDE.md.)
7. Companion docs to cross-link. (Scan `docs/`.)

Worth asking if the initiative is large:

8. **Rollout shape.** Can this ship in independently-valuable slices, or is it all-or-nothing?
9. **Metrics.** Any numeric target with a time horizon (e.g. "30 pages in 90 days")?
10. **Non-blocking unknowns** to park in OPEN QUESTIONS.

---

## ADR

Blocking:

1. **The decision.** What exactly are we deciding? (One decision — if two, that's two ADRs.)
2. **The alternatives.** What other options are real candidates, including "do nothing"? An ADR with no rejected alternatives has no value.
3. **The forces.** What constraints drive this — cost, existing stack, team size, time, vendor limits, compliance?
4. **Status.** Is this Proposed (deciding now) or Accepted (recording a choice already made)? Does it supersede an existing ADR?

Often derivable / worth confirming:

5. Scope — which subsystem does this govern?
6. Deciders & date.
7. The trade-off — what do we knowingly give up by choosing this? (If the user hasn't named a downside, probe for one; every real decision has costs.)

---

## Execution Spec

Blocking:

1. **Source of truth.** Which PRD/ADR (or decision) does this implement? Read it first.
2. **Target files.** What's the actual current state of the code being changed? (Verify every path with Glob/Read — do not write a path you haven't confirmed.)
3. **Granularity.** Is this one mergeable change or several with ordering between them?

Often derivable / worth confirming:

4. Codegen boundaries — which files are generated and must not be hand-edited?
5. Test expectations — what level of test coverage does each spec need? (Check repo conventions.)
6. Deliberate simplifications — is the implementer allowed to simplify vs. the PRD, and where? Call these out explicitly in the spec.
7. Output path & whether multiple specs go in one doc or separate files.

---

## General

- Ask once, act on the answers. Don't drip questions across multiple turns.
- Distinguish *blocking* (would force a fabrication) from *nice-to-have* (can default sensibly or park in OPEN QUESTIONS). Only block on the former.
- If an answer reveals the user actually wants a different doc type than requested, say so before writing.
