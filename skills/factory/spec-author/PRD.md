# PRD Template & Style Guide

A PRD frames **what** we're building and **why**, with success criteria concrete enough to test against. Derived from the house style in `docs/*-PRD.md`.

## Required structure

```markdown
# <ProjectName> — <Feature Name>

## <One-line tagline: the outcome in a single sentence>

---

## CONTEXT

<2–4 paragraphs. Where does this sit in the system today? What's the
current (painful) workflow? Name companion docs. Be specific and concrete —
name the actual collections, routes, operators, real numbers.>

The motivating gaps:

1. **<Gap name>.** <Why today's state is inadequate. One tight paragraph.>
2. **<Gap name>.** <…>
3. <…>

### Locked Scope Decisions

<Decisions already made and NOT up for re-litigation. Each is a numbered
bold claim + rationale. This is what keeps the build from drifting.>

1. **<Decision>.** <Rationale — why this and not the alternative.>
2. **<Decision>.** <…>

### What This Is NOT

<Explicit non-goals. This list is a signature of the house style — it is
the single best defense against scope creep. Be generous with it.>

- Not <a thing a reader might assume is in scope>. <Why it's out.>
- Not <…>.

---

## SUCCESS CRITERIA

<Numbered, TESTABLE statements. A reviewer must be able to read each one and
say "yes, that's true now" or "no, it isn't." No vague adjectives. Reference
specific UI surfaces, fields, routes, and behaviors.>

1. Every <entity> has <concrete, observable property> visible in <specific place>.
2. <Specific behavior> happens when <specific trigger>, producing <specific output>.
3. The feature adds zero <forbidden thing> to <protected path>.
4. A failure where <X> degrades gracefully — <observable fallback behavior>.

---

## DATA MODEL CHANGES   ← include when the feature touches persistence

### New Collection / Table — `<name>`

<One-line purpose.>

```
<name>: collection
  - field: type [constraints]                 // inline comment with example value
  - field: type
```

### Changes to existing — `<name>`

<What fields are added/changed and why.>

---

## FEATURE N — <NAME>          ← one section per major capability

<Behavior, data flow, edge cases, and the contract this feature exposes.
Use code fences for schemas, request/response shapes, and prompt structures.
This is where the PRD gets concrete enough to build from.>

---

## API ROUTES                  ← include when new endpoints are added

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/...` | <who> | <what> |

## ENVIRONMENT VARIABLES       ← reference by NAME only, never values

| Var | Purpose | Example (placeholder) |
|---|---|---|
| `SERVICE_API_KEY` | <what it's for> | `YOUR_SERVICE_API_KEY` |

## TESTING STRATEGY

<What's tested at which level (unit / integration / e2e), the key scenarios,
and the must-pass regression cases.>

---

## MILESTONES  /  ROLLOUT PLAN

<Slices that are each INDEPENDENTLY SHIPPABLE. A table works well. State the
standalone value of each slice — slice N must not require slice N+1 to be useful.>

| Slice | Scope | Value delivered alone |
|---|---|---|
| S1 — <name> | <what ships> | <why it's useful on its own> |

---

## OPEN QUESTIONS

<Unresolved-but-non-blocking decisions. Each: the question, the options, and
when the decision must be made by. This is where uncertainty lives honestly —
do NOT resolve these by guessing.>

1. **<Question>.** <Options / tradeoffs.> Decide before <trigger>.

## RISKS                       ← optional but encouraged

- **<Risk>.** <Likelihood/impact and the mitigation.>

## SUCCESS METRICS             ← optional; for measurable initiatives

<Numeric targets with a time horizon, e.g. "≥ 30 pages shipped in 90 days.">

---

## SOURCES & RELATED DOCS

- `<path/to/companion-doc.md>` — <relationship>
```

## Style rules

- **Title:** `# <ProjectName> — <Feature>`. Tagline as an `##` directly under it.
- **Concrete over abstract.** Name real collections, routes, env vars, operators, competitors, numbers. The example PRDs read like the author has the code open.
- **Success criteria must be falsifiable.** If you can't write a test or do a manual check that proves it, rewrite it.
- **Always include `What This Is NOT` and `OPEN QUESTIONS`.** Even a short list. They are the house signature.
- **No secrets.** Env vars by name; placeholder example values only.

## Sections to keep vs. drop

| Always | Include if relevant | Drop if N/A |
|---|---|---|
| CONTEXT, SUCCESS CRITERIA, What This Is NOT, OPEN QUESTIONS, SOURCES | DATA MODEL, FEATURE N, API ROUTES, ENV VARS, TESTING, MILESTONES | RISKS, SUCCESS METRICS (small features) |
