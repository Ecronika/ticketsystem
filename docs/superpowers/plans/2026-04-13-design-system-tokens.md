# Design System Tokens & Naming Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the design-system audit / tokenize / naming-convention findings to [style.css](../../../ticketsystem/static/css/style.css): add missing token tiers (spacing, borders, motion, shadows, breakpoints, touch), refactor the focus-ring, fix naming drift, add systematic `:disabled` / `[aria-invalid]` state rules, and replace hardcoded hotspots with token references.

**Architecture:** Single-file CSS refactor. Three tiers of tokens (global primitives → semantic → component) are layered into the existing `:root` and `[data-theme="*"]` blocks without breaking Bootstrap consumers. Migration is grep-verified (before/after counts) rather than unit-tested; manual visual verification in light/dark/high-contrast modes per phase.

**Tech Stack:** Plain CSS custom properties, no preprocessor. Flask + Jinja templates consume via `<link rel="stylesheet">`. Bootstrap 5 utility classes are preserved as-is.

**Out of scope:**
- The 126-instance `!important` cascade refactor (separate plan, unbounded cascade-analysis work).
- Stylelint automation wiring (listed as optional follow-up in the naming convention).
- Template DRY pass for inlined badges/buttons (separate plan — blocked on component specs).

---

## File Structure

**Modified:**
- `ticketsystem/static/css/style.css` — all token additions, renames, new state rules.

**Verification only (no edits):**
- `ticketsystem/templates/**/*.html` — grep to confirm no templates reference renamed tokens directly.
- `ticketsystem/static/js/*.js` — grep to confirm no JS references renamed CSS custom properties via `getComputedStyle`.

No new files created.

---

## Verification Model

CSS has no unit tests. Each task uses two verification mechanisms:

1. **Grep checks** (automatable) — before each replacement, `grep -c` captures the current count; after the change, the count matches an expected delta. Commands use Windows-bash (`/c/...` paths, forward slashes).
2. **Visual verification** (manual, end of each phase) — load these pages in all three themes and eyeball-diff against a screenshot taken before the phase:
   - `/` (index / dashboard)
   - `/tickets/new`
   - `/tickets/<id>` (detail)
   - `/login`
   - `/admin/teams` (a form-heavy page)

Baseline tests from `CLAUDE.md` (`7 passed, 8 failed`) must still hold after every commit.

---

## Phase 1 — Add Tier 1 Global Primitive Tokens

### Task 1: Add spacing, border-width, motion, shadow, breakpoint, touch tokens

**Files:**
- Modify: `ticketsystem/static/css/style.css:74-143` (the `:root` block)

- [ ] **Step 1: Capture baseline grep counts**

Run from `ticketsystem/static/css/`:
```bash
grep -cE '0\.25rem|0\.5rem|0\.75rem|1rem|1\.25rem|1\.5rem' style.css
grep -cE '\b44px\b' style.css
grep -cE '0 [0-9]+px [0-9]+px' style.css
```
Record the numbers in the commit message.

- [ ] **Step 2: Append new primitives to the `:root` block**

Locate the line `--h-qr-selector: 200px;` inside `:root` (around line 142). Add the following block **immediately before** the closing `}` of `:root`:

```css
    /* =========================================
       TIER 1 — GLOBAL PRIMITIVES (theme-agnostic)
       ========================================= */

    /* Spacing scale (4px base, numeric) */
    --space-0: 0;
    --space-1: 0.25rem;   /* 4px */
    --space-2: 0.5rem;    /* 8px */
    --space-3: 0.75rem;   /* 12px */
    --space-4: 1rem;      /* 16px */
    --space-5: 1.25rem;   /* 20px */
    --space-6: 1.5rem;    /* 24px */
    --space-8: 2rem;      /* 32px */
    --space-12: 3rem;     /* 48px */
    --space-16: 4rem;     /* 64px */

    /* Border widths */
    --border-1: 1px;
    --border-2: 2px;
    --border-3: 3px;
    --border-4: 4px;

    /* Motion */
    --duration-fast: 0.15s;
    --duration-base: 0.2s;
    --duration-slow: 0.3s;
    --ease-standard: ease;
    --transition-colors:
        background-color var(--duration-base) var(--ease-standard),
        color var(--duration-base) var(--ease-standard),
        border-color var(--duration-base) var(--ease-standard),
        box-shadow var(--duration-base) var(--ease-standard);

    /* Shadows */
    --shadow-xs: 0 1px 2px rgb(0 0 0 / 6%);
    --shadow-sm: 0 2px 4px rgb(0 0 0 / 8%);
    --shadow-md: 0 4px 8px rgb(0 0 0 / 12%);
    --shadow-lg: 0 8px 24px rgb(0 0 0 / 16%);

    /* Breakpoints (reference only — CSS media queries can't use var()) */
    --bp-sm: 576px;
    --bp-md: 768px;
    --bp-lg: 992px;
    --bp-xl: 1200px;

    /* WCAG 2.5.8 touch target */
    --touch-target-min: 44px;
```

- [ ] **Step 3: Verify CSS is still valid**

Load `http://<local-dev>/` in the browser with DevTools open. Console should report zero new CSS parse errors. Confirm the page still renders identically (no tokens are consumed yet — this is pure addition).

- [ ] **Step 4: Verify import still succeeds and baseline tests hold**

From `ticketsystem/`:
```bash
python -c "from app import app"
python -m pytest tests/ -v
```
Expected: import OK; `7 passed, 8 failed` baseline.

- [ ] **Step 5: Commit**

```bash
git add ticketsystem/static/css/style.css
git commit -m "feat(css): add tier-1 primitive tokens (spacing, borders, motion, shadows, bp, touch)"
```

---

## Phase 2 — Refactor Focus Ring Into Two Tokens

### Task 2: Split `--focus-ring` into width + color primitives

**Files:**
- Modify: `ticketsystem/static/css/style.css:83` (light `:root`), `:158` (dark), `:202` (hc)

- [ ] **Step 1: Find all current focus-ring declarations**

Run:
```bash
grep -nE '^\s*--focus-ring:' style.css
```
Expected three matches (light, dark, hc).

- [ ] **Step 2: Replace the light-mode declaration**

In [style.css:83](../../../ticketsystem/static/css/style.css#L83), change:
```css
    --focus-ring: 3px solid #0d6efd;
```
to:
```css
    --focus-ring-width: var(--border-3);
    --focus-ring-color: #0d6efd;
    --focus-ring: var(--focus-ring-width) solid var(--focus-ring-color);
```

- [ ] **Step 3: Replace the dark-mode declaration**

In [style.css:158](../../../ticketsystem/static/css/style.css#L158), change:
```css
    --focus-ring: 3px solid #3b82f6;
```
to:
```css
    --focus-ring-width: var(--border-3);
    --focus-ring-color: #3b82f6;
    --focus-ring: var(--focus-ring-width) solid var(--focus-ring-color);
```

- [ ] **Step 4: Replace the high-contrast declaration**

In [style.css:202](../../../ticketsystem/static/css/style.css#L202), change:
```css
    --focus-ring: 4px solid #0ff;
```
to:
```css
    --focus-ring-width: var(--border-4);
    --focus-ring-color: #0ff;
    --focus-ring: var(--focus-ring-width) solid var(--focus-ring-color);
```

- [ ] **Step 5: Visual verification of focus rings**

For each of the three themes (toggle via settings or `[data-theme]` attribute in DevTools):
1. Tab through the login page — focus ring should appear identical to before.
2. Tab through the ticket-new form — all inputs show the ring.
3. In HC mode, confirm the 4px cyan ring is unchanged.

- [ ] **Step 6: Commit**

```bash
git add ticketsystem/static/css/style.css
git commit -m "refactor(css): split --focus-ring into width + color primitives"
```

---

## Phase 3 — Add Tier 3 Component Tokens

### Task 3: Define button, input, card, badge component tokens

**Files:**
- Modify: `ticketsystem/static/css/style.css:74-143` (the `:root` block; append after Tier 1)

- [ ] **Step 1: Append Tier 3 block to `:root`**

Immediately after the Tier 1 block added in Task 1, before the closing `}` of `:root`, add:

```css
    /* =========================================
       TIER 3 — COMPONENT TOKENS
       ========================================= */

    /* Button */
    --btn-padding-y: var(--space-2);
    --btn-padding-x: var(--space-3);
    --btn-min-height: var(--touch-target-min);
    --btn-radius: var(--radius-md);

    /* Input / form control */
    --input-min-height: var(--touch-target-min);
    --input-border-width: var(--border-1);
    --input-radius: var(--radius-sm);

    /* Card */
    --card-padding: var(--space-4);
    --card-radius: var(--radius-lg);
    --card-shadow: var(--shadow-sm);

    /* Badge */
    --badge-padding-y: var(--space-1);
    --badge-padding-x: var(--space-2);
    --badge-radius: var(--radius-pill);
```

- [ ] **Step 2: Verify no rendering change**

Page still renders identically (tokens not yet consumed). Open DevTools → Computed tab on `body`, confirm the new custom properties are listed.

- [ ] **Step 3: Commit**

```bash
git add ticketsystem/static/css/style.css
git commit -m "feat(css): add tier-3 component tokens (btn, input, card, badge)"
```

---

## Phase 4 — Add Systematic Disabled / Invalid State Rules

### Task 4: Add `:disabled` and `[aria-invalid]` CSS

**Files:**
- Modify: `ticketsystem/static/css/style.css` — add a new section after the `.btn-outline-theme-warning:hover` block (around line 278)

- [ ] **Step 1: Grep for any existing `:disabled` rules**

```bash
grep -nE ':disabled|aria-invalid|is-invalid' style.css
```
Record current matches. Expected: very few / none — confirmed missing in the audit.

- [ ] **Step 2: Add the new state section**

Insert the following block immediately after the `.btn-outline-theme-warning:hover { ... }` rule (line ~278):

```css
/* =========================================
   SYSTEMATIC STATES (audit finding: disabled/invalid missing)
   ========================================= */

/* Disabled state — buttons */
.btn:disabled,
.btn[aria-disabled="true"],
.btn.disabled {
    opacity: 0.65;
    cursor: not-allowed;
    pointer-events: none;
}

/* Disabled state — form controls */
.form-control:disabled,
.form-select:disabled,
.form-check-input:disabled {
    background-color: var(--bg-surface-subtle);
    color: var(--text-muted);
    cursor: not-allowed;
    opacity: 0.7;
}

/* Invalid state — accepts Bootstrap .is-invalid AND aria-invalid */
.form-control.is-invalid,
.form-control[aria-invalid="true"],
.form-select.is-invalid,
.form-select[aria-invalid="true"] {
    border-color: var(--color-danger);
    box-shadow: 0 0 0 0.25rem rgb(220 38 38 / 25%);
}

/* HC mode: outline instead of coloured shadow */
[data-theme="hc"] .form-control.is-invalid,
[data-theme="hc"] .form-control[aria-invalid="true"],
[data-theme="hc"] .form-select.is-invalid,
[data-theme="hc"] .form-select[aria-invalid="true"] {
    outline: var(--border-3) solid var(--color-danger);
    box-shadow: none;
}
```

- [ ] **Step 3: Visual verification**

1. On the ticket-new form, open DevTools and add `disabled` attribute to a button → it should dim to 0.65 opacity with not-allowed cursor.
2. Add `aria-invalid="true"` to a form input → red border + red focus-shadow appears.
3. Toggle to HC mode, repeat — invalid input shows a 3px red outline instead of the shadow.

- [ ] **Step 4: Baseline tests still pass**

```bash
cd ticketsystem && python -m pytest tests/ -v
```
Expected: `7 passed, 8 failed` unchanged.

- [ ] **Step 5: Commit**

```bash
git add ticketsystem/static/css/style.css
git commit -m "feat(a11y): add systematic :disabled and [aria-invalid] state rules"
```

---

## Phase 5 — Mechanical Token Replacements

Each subtask replaces one value family. Always grep before AND after to verify the delta matches expectations.

### Task 5: Replace `min-height: 44px` with touch-target token

**Files:**
- Modify: `ticketsystem/static/css/style.css` (8 occurrences expected)

- [ ] **Step 1: Count occurrences**

```bash
grep -cE 'min-height:\s*44px' style.css
grep -cE 'min-width:\s*44px' style.css
```
Record the numbers.

- [ ] **Step 2: Replace**

Using a text editor's find-and-replace (regex, case-sensitive):
- Find: `min-height:\s*44px` → Replace: `min-height: var(--touch-target-min)`
- Find: `min-width:\s*44px` → Replace: `min-width: var(--touch-target-min)`

- [ ] **Step 3: Verify zero `44px` literals remain**

```bash
grep -nE '\b44px\b' style.css
```
Expected: no matches (unless one is legitimately non-touch, in which case revert that single instance with a comment).

- [ ] **Step 4: Visual check**

Touch-target sizing on the ticket detail page (action buttons, table buttons) unchanged.

- [ ] **Step 5: Commit**

```bash
git add ticketsystem/static/css/style.css
git commit -m "refactor(css): use --touch-target-min token for 44px rules"
```

### Task 6: Replace inline shadows with shadow tokens

**Files:**
- Modify: `ticketsystem/static/css/style.css`

- [ ] **Step 1: Locate inline shadows**

```bash
grep -nE 'box-shadow:\s*0 [0-9]+px [0-9]+px' style.css
```
Read each match in context. Categorise by size:
- `0 1-2px …` → `--shadow-xs`
- `0 2-3px 4-6px …` → `--shadow-sm`
- `0 4px 8px …` → `--shadow-md`
- `0 8px 24px …` / larger → `--shadow-lg`

- [ ] **Step 2: Replace each match individually**

For each match, edit in place. Example — [style.css:249](../../../ticketsystem/static/css/style.css#L249):
```css
    box-shadow: 0 4px 8px rgb(13 110 253 / 20%);
```
becomes:
```css
    box-shadow: var(--shadow-md);
```

**Exception — focus shadows (`0 0 0 0.25rem ...`)** are NOT regular drop shadows. Leave them alone — they're focus-ring companions and are already semantically tokenised via `--focus-shadow`.

- [ ] **Step 3: Verify focus shadows are untouched**

```bash
grep -cE 'box-shadow:\s*0 0 0 0\.25rem' style.css
```
Number should be unchanged from Phase-1 baseline.

- [ ] **Step 4: Visual check**

Hover over cards, buttons (ticket detail page). Shadows should look near-identical — slight colour shift is acceptable (tokens use neutral black-alpha, inline shadows used tinted colours; this is intentional unification).

- [ ] **Step 5: Commit**

```bash
git add ticketsystem/static/css/style.css
git commit -m "refactor(css): replace inline drop shadows with --shadow-* tokens"
```

### Task 7: Replace spacing rem literals with `--space-*` tokens (padding/margin/gap only)

**Files:**
- Modify: `ticketsystem/static/css/style.css`

**IMPORTANT:** Only replace rem values that appear as **spacing** (padding, margin, gap, top/right/bottom/left). Do NOT replace:
- `rem` in `font-size` (use `--fs-*` tokens — handled in Task 9)
- `rem` in `border-radius` (use `--radius-*` — already tokenised)
- `rem` in `box-shadow` offsets (already handled in Task 6)
- `rem` in `line-height`, `width`, `height` (dimensional, not spacing)

- [ ] **Step 1: Find spacing-context matches for each value**

For each of `0.25rem`, `0.5rem`, `0.75rem`, `1rem`, `1.25rem`, `1.5rem`, `3rem`:
```bash
grep -nE '(padding|margin|gap|top|right|bottom|left|inset)[^;]*\b0\.5rem\b' style.css
```
(repeat per value). Record each match's line number.

- [ ] **Step 2: Replace `0.25rem` → `var(--space-1)` in spacing contexts**

For each line identified in Step 1 with `0.25rem`, replace that specific `0.25rem` with `var(--space-1)`.

- [ ] **Step 3: Replace `0.5rem` → `var(--space-2)`**

Same pattern.

- [ ] **Step 4: Replace `0.75rem` → `var(--space-3)`**

Same pattern.

- [ ] **Step 5: Replace `1rem` → `var(--space-4)`**

Same pattern. **Double-check each match** — `1rem` is very common and also appears in `font-size` and `line-height`. Only replace in the contexts listed at the top of this task.

- [ ] **Step 6: Replace `1.25rem` → `var(--space-5)`, `1.5rem` → `var(--space-6)`, `3rem` → `var(--space-12)`**

Same approach.

- [ ] **Step 7: Verify remaining rem literals are justified**

```bash
grep -nE '\b[0-9]+\.?[0-9]*rem\b' style.css | grep -vE 'font-size|line-height|border-radius|radius-|fs-|space-|focus-shadow|box-shadow.*0\.25rem'
```
Each remaining match should be in a dimensional/exceptional context — add a comment if non-obvious.

- [ ] **Step 8: Full-page visual check across all three themes**

Load `/`, `/tickets/new`, `/tickets/<id>`, `/login`, `/admin/teams`. Layout should look pixel-identical.

- [ ] **Step 9: Baseline tests**

```bash
cd ticketsystem && python -m pytest tests/ -v && python -m flake8 --max-line-length=120 *.py routes/ services/
```
Expected: `7 passed, 8 failed`; flake8 clean.

- [ ] **Step 10: Commit**

```bash
git add ticketsystem/static/css/style.css
git commit -m "refactor(css): migrate spacing rem literals to --space-* tokens"
```

---

## Phase 6 — Naming Drift Fixes

### Task 8: Rename ambiguous `--h-*` scroll-container tokens

**Files:**
- Modify: `ticketsystem/static/css/style.css`
- Verify: `ticketsystem/templates/**/*.html`, `ticketsystem/static/js/*.js`

- [ ] **Step 1: Confirm tokens aren't referenced outside the CSS file**

```bash
cd ticketsystem && grep -rn -- '--h-exchange-list\|--h-logo-preview\|--h-qr-selector' templates/ static/js/
```
Expected: zero matches (they're CSS-internal).

- [ ] **Step 2: Rename in the `:root` block**

In [style.css:140-142](../../../ticketsystem/static/css/style.css#L140-L142):
```css
    --h-exchange-list: 250px;
    --h-logo-preview: 150px;
    --h-qr-selector: 200px;
```
becomes:
```css
    --exchange-list-max-h: 250px;
    --logo-preview-max-h: 150px;
    --qr-selector-max-h: 200px;
```

- [ ] **Step 3: Update all consumers in style.css**

```bash
grep -nE 'var\(--h-(exchange-list|logo-preview|qr-selector)\)' style.css
```
For each match, update the `var()` call to the new name.

- [ ] **Step 4: Verify no stale references**

```bash
grep -cE '\-\-h-(exchange-list|logo-preview|qr-selector)' style.css
```
Expected: `0`.

- [ ] **Step 5: Visual check**

Pages that use these containers (exchange picker / logo upload / QR selector — check in admin templates and ticket settings). Scroll heights unchanged.

- [ ] **Step 6: Commit**

```bash
git add ticketsystem/static/css/style.css
git commit -m "refactor(css): rename --h-* tokens to <comp>-max-h (naming convention)"
```

### Task 9: Remove sub-WCAG `--fs-xxxs` and migrate consumers

**Files:**
- Modify: `ticketsystem/static/css/style.css`

- [ ] **Step 1: Find all consumers of `--fs-xxxs`**

```bash
grep -nE 'var\(--fs-xxxs\)' style.css
```

- [ ] **Step 2: Replace each consumer**

For each consumer, replace `var(--fs-xxxs)` with `var(--fs-xxs)` (0.65rem / ~10.4px — still sub-WCAG for body text, but only used for micro-metadata where that's acceptable; the `xxxs` value of 0.55rem / 8.8px is below any defensible threshold).

- [ ] **Step 3: Remove the token definition**

In [style.css:121](../../../ticketsystem/static/css/style.css#L121), delete the line:
```css
    --fs-xxxs: 0.55rem;
```

- [ ] **Step 4: Verify no stale references**

```bash
grep -c -- '--fs-xxxs' style.css
```
Expected: `0`.

- [ ] **Step 5: Visual check for any shrunken text**

Spot-check pages with tight metadata (dashboard rows, workload view). Minor size increase on a few labels is the expected, intended outcome.

- [ ] **Step 6: Commit**

```bash
git add ticketsystem/static/css/style.css
git commit -m "fix(a11y): drop --fs-xxxs (0.55rem / ~8.8px fails WCAG minimum)"
```

### Task 10: Clean up dead CSS rules

**Files:**
- Modify: `ticketsystem/static/css/style.css:891`, `:1069`

- [ ] **Step 1: Inspect the candidates flagged in the audit**

Read [style.css:889-895](../../../ticketsystem/static/css/style.css#L889-L895). Confirm `.mention-dropdown { display: none; }` is the entire rule for that selector and no other rule enables it.

```bash
grep -nE '\.mention-dropdown' style.css
grep -rn 'mention-dropdown' ticketsystem/templates/ ticketsystem/static/js/
```
If the JS or templates reference `.mention-dropdown` with dynamic display toggling, keep the rule. If not, it's dead.

- [ ] **Step 2: Delete `.mention-dropdown` if unused**

If Step 1 confirmed zero references outside the single always-hidden rule, delete the rule.

- [ ] **Step 3: Inspect `.fade-toggle.hidden`**

Read [style.css:1065-1075](../../../ticketsystem/static/css/style.css#L1065-L1075). The audit flagged redundant `display: none` + `opacity: 0`. Keep whichever is animated from; remove the other.

Typical resolution: if there's a transition on `opacity`, keep `opacity: 0; pointer-events: none;` and drop `display: none` (which breaks transitions). If no transition, keep `display: none` and drop `opacity: 0`.

- [ ] **Step 4: Commit**

```bash
git add ticketsystem/static/css/style.css
git commit -m "chore(css): remove dead/redundant rules flagged by audit"
```

---

## Phase 7 — Final Verification

### Task 11: End-to-end verification and summary

- [ ] **Step 1: Run the full baseline**

From `ticketsystem/`:
```bash
python -c "from app import app"
python -m pytest tests/ -v
python -m flake8 --max-line-length=120 *.py routes/ services/
```
Expected: import OK, `7 passed, 8 failed`, flake8 clean.

- [ ] **Step 2: Manual visual sweep in all three themes**

For each theme (`light` / `dark` / `hc`), load each page and compare against pre-migration screenshots:
- `/` (dashboard / index)
- `/tickets/new` (form-heavy)
- `/tickets/<id>` (detail, comments, attachments)
- `/login`
- `/admin/teams`
- `/workload`
- `/projects`

Pixel-exact is not required; any visible regression must be explained (shadow colour unification is expected).

- [ ] **Step 3: Capture final grep stats for the commit body**

```bash
grep -c '!important' style.css
grep -c -- '--space-' style.css
grep -cE '\b44px\b' style.css
grep -cE '\b[0-9]+\.?[0-9]*rem\b' style.css
```

- [ ] **Step 4: Commit a migration summary (empty commit if no further changes)**

```bash
git commit --allow-empty -m "docs(css): design-system token migration complete

- Added tier-1 primitives (space, border, motion, shadow, bp, touch)
- Added tier-3 component tokens (btn, input, card, badge)
- Split --focus-ring into width + color
- Added systematic :disabled / [aria-invalid] state rules
- Renamed --h-* tokens to <comp>-max-h
- Removed sub-WCAG --fs-xxxs
- Replaced 44px touch targets and inline shadows with tokens

See docs/superpowers/plans/2026-04-13-design-system-tokens.md"
```

---

## Follow-ups (Not in this plan)

1. **`!important` cascade refactor** (126 instances, est. 4–6h). Separate plan — needs per-rule cascade analysis; not mechanical.
2. **Template DRY pass** — move inlined badges/buttons into the `components/` partials (est. 3h, 15+ templates).
3. **Stylelint wiring** — enforce `custom-property-pattern` and `selector-class-pattern` via pre-commit hook.
4. **`/design-systems:audit-system` re-run** — expect token-coverage score 7→9, state-completeness 5→8.
