# PromptLab — Design Direction (FROZEN)

## Mandatory
Any agent doing frontend work MUST invoke the **`emil-design-eng`** skill (Skill tool) BEFORE
writing a single component, and follow it. It governs component design, interaction polish,
animation decisions, and the small details that separate a real tool from a generated dashboard.
This is a hard requirement from the user, not a suggestion.

## What this app is
A dense, professional developer instrument — the thing you leave open on a second monitor while
iterating on a production prompt. Closer to Linear / Vercel / Raycast than to a marketing site.
It should feel fast and quiet. The data is the interface.

## Foundations
- **Theme**: dark-first, with a working light theme. Neutral zinc/stone surfaces, layered by
  elevation rather than by borders everywhere. One accent colour used sparingly — for the primary
  action and the current selection, not decoration.
- **Type**: Inter (or system UI stack) for chrome; **JetBrains Mono** for every prompt, model output,
  JSON, variable name, and score. Tabular numerals for all score columns so they align.
- **Semantic colour** is reserved for meaning: score quality (low/mid/high), run status, and A/B
  win/loss. Never decorative.
- **Density**: compact rows, real tables, no oversized cards. Generous space between *sections*,
  tight space *within* them.
- **Motion**: purposeful only — streaming rows arriving during a run, drawer open/close, score
  count-up. Respect `prefers-reduced-motion`. No entrance animations on static content.

## Explicitly banned
Purple/indigo gradients. Glassmorphism. Emoji used as icons. Centred hero layouts. Rounded-3xl
pill-everything. Generic "AI product" chrome. Placeholder lorem. Icon libraries used for decoration.

## Required states
Every view must handle: empty (with a real next action, not just "No data"), loading (skeletons that
match final layout, not spinners-in-a-box), error (with what failed and how to retry), and the
in-progress case — a run streaming results live is a first-class state, not an afterthought.

## Screens
1. **Prompts** — list; editor with `{{variable}}` syntax highlighting and a live detected-variables
   chip row; version history rail with diff-against-previous; "Save as new version" with a notes field.
2. **Datasets** — list; detail is an editable table of cases. Three entry paths as peer affordances:
   Generate (domain description, count, mode standard/adversarial/mixed), Add case, Import file
   (drop zone -> preview -> column->variable mapping -> confirm).
3. **Graders** — per prompt. Add/remove/reorder, weight sliders that show the resulting normalized
   contribution, per-type config forms (rubric textarea, schema editor, pattern lists, budget inputs).
4. **Run** — launch panel (version, dataset, model, temperature, concurrency) with a pre-flight
   variable-compatibility check. Then live progress: a table that fills in as SSE events land, with a
   running average. On completion: headline average score, distribution, per-grader and
   **per-category** breakdowns (the category view is the point — it shows *which kind* of input the
   prompt fails on). Click any row for a detail drawer: rendered prompt, raw output, latency/tokens/
   cost, and each grader's score + reasoning.
5. **Compare** — pick two runs on the same dataset. Summary deltas, win/loss/tie counts, per-case
   rows with both scores and a delta, expandable to side-by-side outputs.
6. **Settings** — API key presence (read-only), default models, concurrency, pricing table.

## Non-negotiable interaction details
- Prompt and output text must be selectable and copyable; every code/output surface gets a copy button.
- Long outputs collapse with an explicit expand, never silently truncate without a signal.
- Score colour must never be the only signal — pair with the number.
- Keyboard: `cmd+k` command palette is optional; `esc` closing drawers and `cmd+enter` submitting
  the run launch form are not.
