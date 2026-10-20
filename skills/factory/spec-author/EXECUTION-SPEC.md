# Execution Spec Template & Style Guide

An execution spec turns approved work into **ordered, file-level implementation steps**. It's the bridge from "we decided to build this" (PRD/ADR) to "here's exactly what to change and in what order." Derived from `docs/IMPLEMENTATION-SPECS.md`.

A spec doc contains one or more **Specs** (numbered units of work) and ends with a **Suggested execution order** that explains the dependencies between them. Each Spec should be independently mergeable.

## Document structure

```markdown
# <ProjectName> — <Initiative> Implementation Specs

<1–2 sentence framing: what these specs collectively accomplish, and what the
starting state is. Link the PRD/ADR(s) they implement.>

---

## Spec 1 — <imperative title, e.g. "Build the ServiceAreaMap block">

### Problem

<The concrete current state — what exists, what's stubbed, what's wrong, and
where (real file paths). Then what the target state is. Cite the PRD/ADR
section that requires this. Note any deliberate simplifications vs. the PRD.>

### Files to touch

| File | Action |
|---|---|
| `path/to/file.ts` | Add fields / Create new file / Wire up / Regenerate (do not hand-edit) |

### Acceptance criteria

<Numbered, testable, observable. Same bar as PRD success criteria but scoped
to this one spec. "Renders without the placeholder anywhere on the live site.">

1. <criterion>
2. <criterion>

### Implementation

<Ordered, sub-numbered steps (2A, 2B, …). For each: which file, what change,
and — where it removes ambiguity — the actual code to write in a fenced block.
Be concrete enough that someone could execute it without re-deriving the design,
but don't pad with code that's obvious. Call out anything explicitly deferred
("a mapEmbedUrl field is added but documented as future").>

#### 1A. <step — file + change>

```ts
// real, paste-ready code where it resolves ambiguity
```

#### 1B. <step>

---

## Spec 2 — <title>

<…same shape…>

---

## Suggested execution order

<Ordered list explaining WHY this order — the dependencies between specs, not
just a restatement. Note which specs block which, and which are independently
mergeable.>

1. Run Spec 1 first — <reason: smallest change / unblocks the rest / highest-visibility fix>.
2. Run Spec 2 — <reason: depends on Spec 1's output>.
3. Run Spec 3 — <reason>.

<Closing line on the net effect: what state the codebase reaches after all specs.>
```

## Style rules

- **Every file path must be real.** Verify with `Glob`/`Read` before writing the spec. A spec that names a nonexistent file, or misroutes a real one, is a defect — this is the single most important rule.
- **"Files to touch" is a table, action-annotated.** The action verb (Add / Create / Wire / Regenerate / Delete) tells the implementer the shape of the change at a glance.
- **Generated files are flagged "do not hand-edit"** (e.g. `payload-types.ts` → "Regenerate"). Respect the repo's codegen boundaries.
- **Acceptance criteria per spec, testable.** Mirror PRD discipline at spec granularity.
- **Paste-ready code only where it removes ambiguity.** Show the full file when replacing a stub; show a snippet when adding to a known file; describe in prose when the change is mechanical. Don't dump code the implementer would obviously write.
- **Each Spec is independently mergeable** and the execution order explains the dependency graph. If Spec 2 truly needs Spec 1, say so and why.
- **Deliberate simplifications vs. the PRD are called out**, not silently dropped (e.g. "skip per-block map center; use an auto-computed centroid instead").
- **No secrets** — env vars by name only.

## When to write one Spec vs. many

- One Spec = one coherent, mergeable change (a block, a route, a migration).
- Split into multiple Specs when work has internal ordering or independent review surfaces.
- If there's only one Spec, you can drop the "Suggested execution order" section — but keep it the moment there are two.
