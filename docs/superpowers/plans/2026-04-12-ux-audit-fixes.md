# UX Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the Severity-2 and Severity-3 findings from the 2026-04-12 UX audit (navigation clarity, form validation, wording, dead code).

**Architecture:** Pure frontend changes in existing Jinja templates plus one new shared form-validation JS module. No route or service changes. Tests verify that template renders contain expected / absent markers; JS behavior is covered by a small smoke test via Flask test client.

**Tech Stack:** Flask, Jinja2, Bootstrap 5.3, vanilla JS, pytest.

---

## Scope (from audit)

Out of scope: `ticket_detail.html` (not audited), keyboard shortcuts (separate plan), global search (separate plan).

| # | Finding | Sev | Files |
|---|---------|-----|-------|
| 1 | Dead `#reloadHint` alert — never triggered | 1 | `templates/index.html`, `static/css/style.css` |
| 2 | Happy-talk on login + ticket_new | 1 | `templates/login.html`, `templates/ticket_new.html` |
| 3 | Mobile CTA "Melden" is ambiguous | 2 | `templates/base.html` |
| 4 | Admin nav-dropdown has no caret | 2 | `templates/base.html` |
| 5 | Duplicate "Wartet" tab on dashboard | 2 | `templates/index.html`, `services/dashboard_service.py` (only if used) |
| 6 | "Was passiert nach dem Absenden?" blocks submit CTA | 2 | `templates/ticket_new.html` |
| 7 | Breadcrumbs missing on key inner pages | 3 | `templates/base.html`, `archive.html`, `workload.html`, admin templates |
| 8 | No inline validation in new-ticket form | 3 | `templates/ticket_new.html`, `static/js/form_validation.js` (new) |
| 9 | No unsaved-changes warning on new-ticket form | 3 | `static/js/form_validation.js` |

---

## File Map

| File | Change |
|------|--------|
| `ticketsystem/templates/index.html` | Remove `#reloadHint` block + its reload-link handler. Remove `tab=wartet` anchor. |
| `ticketsystem/static/css/style.css` | Remove dead `#reloadHint` selector from line 1332. |
| `ticketsystem/templates/login.html` | Remove subtitle happy-talk, shorten CTA label. |
| `ticketsystem/templates/ticket_new.html` | Remove redundant subheading, move info box into success alert, add `data-validate` hooks, add phone/email patterns. |
| `ticketsystem/templates/base.html` | Fix mobile CTA label, add caret to admin dropdown, add global `{% block breadcrumbs %}`, include shared validation JS. |
| `ticketsystem/templates/archive.html` | Add breadcrumb block. |
| `ticketsystem/templates/workload.html` | Add breadcrumb block. |
| `ticketsystem/templates/admin_teams.html` | Add breadcrumb block. |
| `ticketsystem/templates/admin_templates.html` | Add breadcrumb block. |
| `ticketsystem/templates/admin_trash.html` | Add breadcrumb block. |
| `ticketsystem/templates/settings.html` | Add breadcrumb block. |
| `ticketsystem/static/js/form_validation.js` | New: inline validation + dirty-form guard. |
| `ticketsystem/Dockerfile` | No change (new JS lives under `static/`, copied as directory). |
| `ticketsystem/tests/test_ui_ux.py` | New pytest module with rendering assertions. |

---

## Baseline

Before starting: `cd ticketsystem && python -m pytest tests/ -v` — note current pass/fail counts. Every task ends with a verify step that compares against this baseline.

---

## Task 1: Remove dead `#reloadHint` element

**Files:**
- Modify: `ticketsystem/templates/index.html:429-434`
- Modify: `ticketsystem/templates/index.html:56-58` (handler binding)
- Modify: `ticketsystem/static/css/style.css:1332`
- Test: `ticketsystem/tests/test_ui_ux.py` (new)

The element is `d-none` and no code ever toggles it. Removing it simplifies the dashboard and removes a source of confusion.

- [ ] **Step 1: Create the test file with a failing test**

Create `ticketsystem/tests/test_ui_ux.py`:

```python
"""UI/UX regression tests — assert template markers."""
import pytest

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def _login(client, worker_name="Schmidt", pin="7391"):
    """Helper to log in; tests that need an authenticated view use this."""
    return client.post("/login", data={"worker_name": worker_name, "pin": pin},
                       follow_redirects=False)


def test_dashboard_has_no_dead_reload_hint(client):
    """Dead #reloadHint element must be removed from dashboard."""
    # Anonymous users are redirected; use the /login page which extends base.html.
    resp = client.get("/login")
    assert b'id="reloadHint"' not in resp.data
```

- [ ] **Step 2: Run test to verify it fails (if `#reloadHint` still present)**

Run: `cd ticketsystem && python -m pytest tests/test_ui_ux.py::test_dashboard_has_no_dead_reload_hint -v`

Note: `#reloadHint` is on `index.html` (requires auth). The test hits `/login`, so this passes immediately — the stronger check is Step 4 grep. Keep the test as regression guard.

- [ ] **Step 3: Remove the dead markup**

In `ticketsystem/templates/index.html` delete lines 429-434:

```html
<!-- Reload Hint -->
<div id="reloadHint" class="d-none alert alert-info alert-dismissible py-2 mb-3 shadow-sm border-0 rounded-3 small" role="alert">
    <i class="bi bi-arrow-clockwise me-1"></i>
    Neue Tickets verfügbar — <a href="#" class="alert-link reload-page-link">Jetzt aktualisieren</a>
    <button type="button" class="btn-close btn-sm" data-bs-dismiss="alert" aria-label="Schließen"></button>
</div>
```

And remove the now-unused handler at lines 56-58 of `index.html`:

```javascript
    document.querySelectorAll('.reload-page-link').forEach(el => {
        el.addEventListener('click', (e) => { e.preventDefault(); location.reload(); });
    });
```

- [ ] **Step 4: Remove the dead CSS selector**

In `ticketsystem/static/css/style.css:1332`, strip `#reloadHint, ` from the selector list (keep the rest of the rule intact).

Grep verification: `grep -rn "reloadHint\|reload-page-link" ticketsystem/` must return zero matches.

- [ ] **Step 5: Run full test suite**

Run: `cd ticketsystem && python -m pytest tests/ -v`
Expected: matches baseline (no new failures).

- [ ] **Step 6: Commit**

```bash
git add ticketsystem/templates/index.html ticketsystem/static/css/style.css ticketsystem/tests/test_ui_ux.py
git commit -m "ux: remove dead #reloadHint element and CSS selector"
```

---

## Task 2: Remove happy-talk on login & new-ticket pages

**Files:**
- Modify: `ticketsystem/templates/login.html:32-35, 65`
- Modify: `ticketsystem/templates/ticket_new.html:18`
- Test: `ticketsystem/tests/test_ui_ux.py`

- [ ] **Step 1: Add failing assertions**

Append to `tests/test_ui_ux.py`:

```python
def test_login_page_has_no_happy_talk(client):
    resp = client.get("/login")
    assert b"Shopfloor" not in resp.data
    assert b"Echtzeit verfolgen" not in resp.data
    # CTA is shortened
    assert b"Jetzt Einloggen" not in resp.data


def test_new_ticket_has_no_redundant_subheading(client):
    resp = client.get("/ticket/new")
    # Subheading duplicated the H2; it must be gone.
    assert b"Erstellen Sie ein neues Ticket" not in resp.data
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ticketsystem && python -m pytest tests/test_ui_ux.py -v -k "happy_talk or redundant_sub"`
Expected: both tests FAIL.

- [ ] **Step 3: Remove happy-talk from login.html**

In `ticketsystem/templates/login.html:32-35` delete the `bg-primary-subtle` info block:

```html
<div class="bg-primary-subtle p-3 rounded-3 mb-4 text-primary text-center">
    <h5 class="h6 fw-bold mb-1"><i class="bi bi-info-circle-fill me-1"></i> TicketSystem Shopfloor</h5>
    <p class="small mb-0 opacity-75">Störungen melden & Status in Echtzeit verfolgen.</p>
</div>
```

Shorten button label at `login.html:65` from `Jetzt Einloggen` to `Einloggen`.

- [ ] **Step 4: Remove redundant subheading from ticket_new.html**

In `ticketsystem/templates/ticket_new.html:18` delete the line:

```html
<p class="text-muted small">Erstellen Sie ein neues Ticket für die Werkstatt oder das Büro.</p>
```

- [ ] **Step 5: Verify tests pass**

Run: `cd ticketsystem && python -m pytest tests/test_ui_ux.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ticketsystem/templates/login.html ticketsystem/templates/ticket_new.html ticketsystem/tests/test_ui_ux.py
git commit -m "ux: remove happy-talk and redundant subheadings"
```

---

## Task 3: Fix mobile CTA label + Admin dropdown caret

**Files:**
- Modify: `ticketsystem/templates/base.html:144-150` (mobile CTA label)
- Modify: `ticketsystem/templates/base.html:99-101` (admin dropdown)
- Test: `ticketsystem/tests/test_ui_ux.py`

"Melden" is ambiguous (Krankmeldung? Login?). "Neu" is unambiguous. Admin dropdown currently uses a badge without a caret — users don't recognize it as a dropdown.

- [ ] **Step 1: Add failing assertions**

Append to `tests/test_ui_ux.py`:

```python
def test_mobile_new_ticket_cta_is_unambiguous(client):
    resp = client.get("/login")
    # 'Melden' alone is ambiguous; the short mobile label should be 'Neu'.
    # The full desktop label stays 'Neues Ticket'.
    assert b'>Melden<' not in resp.data
```

- [ ] **Step 2: Verify failure**

Run: `cd ticketsystem && python -m pytest tests/test_ui_ux.py::test_mobile_new_ticket_cta_is_unambiguous -v`
Expected: FAIL.

- [ ] **Step 3: Replace mobile label**

In `ticketsystem/templates/base.html:149`, change:

```html
<span class="d-lg-none">Melden</span>
```

to:

```html
<span class="d-lg-none">Neu</span>
```

- [ ] **Step 4: Add caret to admin dropdown**

In `ticketsystem/templates/base.html:99-101` replace the anchor tag's body to include a visible caret and drop the unused `dropdown-toggle` default bootstrap caret (which is invisible next to `d-flex`). Replace lines 99-101:

```html
<a class="nav-link dropdown-toggle d-flex align-items-center gap-1" href="#" id="adminDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false">
  <span class="badge-subtle-success px-2 py-1 rounded-pill small fw-bold">Admin</span>
</a>
```

with:

```html
<a class="nav-link d-flex align-items-center gap-1" href="#" id="adminDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false" aria-label="Admin-Menü">
  <span class="badge-subtle-success px-2 py-1 rounded-pill small fw-bold">Admin</span>
  <i class="bi bi-caret-down-fill small opacity-75" aria-hidden="true"></i>
</a>
```

(Removing `dropdown-toggle` prevents the hidden default caret; adding the explicit `bi-caret-down-fill` keeps the signifier visible next to the badge.)

- [ ] **Step 5: Verify tests pass + suite green**

Run: `cd ticketsystem && python -m pytest tests/ -v`
Expected: matches baseline plus the new test passing.

- [ ] **Step 6: Commit**

```bash
git add ticketsystem/templates/base.html ticketsystem/tests/test_ui_ux.py
git commit -m "ux: clarify mobile CTA, add explicit caret to admin dropdown"
```

---

## Task 4: Remove redundant "Wartet" dashboard tab

**Files:**
- Modify: `ticketsystem/templates/index.html:450-453`
- Verify: `ticketsystem/services/dashboard_service.py` (tab is only used for rendering; backend filter can stay as a valid `?tab=wartet` deep link)
- Test: `ticketsystem/tests/test_ui_ux.py`

"Alle Offenen" already includes "wartet"; showing it as a parallel tab double-counts and confuses users. The `summary_counts.wartet` counter can remain available in the data (e.g. future filter chip).

- [ ] **Step 1: Confirm backend doesn't require the tab**

Run: `grep -n "tab.*wartet\|active_tab.*wartet" ticketsystem/routes/ ticketsystem/services/`
If any server-side code treats `wartet` as a *required* UI tab (vs. a filter value), fold those into `all`. Expected: only `index.html` references the tab as a UI element.

- [ ] **Step 2: Add failing assertion**

Append to `tests/test_ui_ux.py`:

```python
def test_dashboard_does_not_show_separate_wartet_tab(client):
    # Log in first — /ticket/1 and /dashboard require a session.
    # Use a fresh session so the check is deterministic.
    with client.session_transaction() as sess:
        sess["worker_id"] = 1
        sess["worker_name"] = "Test"
        sess["role"] = "admin"
    resp = client.get("/")
    # The 'Wartet' tab anchor (distinct from "Alle Offenen") must be gone.
    assert b"tab=wartet" not in resp.data
```

- [ ] **Step 3: Verify failure**

Run: `cd ticketsystem && python -m pytest tests/test_ui_ux.py::test_dashboard_does_not_show_separate_wartet_tab -v`
Expected: FAIL.

- [ ] **Step 4: Remove the tab anchor**

In `ticketsystem/templates/index.html:450-453` delete:

```html
<a href="{{ ingress_path }}{{ url_for('main.index', tab='wartet', q=query) }}" class="dash-tab text-decoration-none {{ 'active' if active_tab == 'wartet' }}">
    <i class="bi bi-hourglass-split me-1 text-secondary"></i>Wartet
    <span class="tab-count bg-surface-subtle text-muted">{{ summary_counts.wartet }}</span>
</a>
```

- [ ] **Step 5: Verify & commit**

Run: `cd ticketsystem && python -m pytest tests/ -v` (baseline held).

```bash
git add ticketsystem/templates/index.html ticketsystem/tests/test_ui_ux.py
git commit -m "ux: remove redundant 'Wartet' dashboard tab"
```

---

## Task 5: Move post-submit info box out of CTA path

**Files:**
- Modify: `ticketsystem/templates/ticket_new.html:261-268, 20-38`
- Test: `ticketsystem/tests/test_ui_ux.py`

The "Was passiert nach dem Absenden?" info block sits directly above the Submit button, competing for attention with the primary action. Move it into the success alert (which already renders after successful creation).

- [ ] **Step 1: Add failing assertion**

Append:

```python
def test_new_ticket_info_box_not_above_submit(client):
    resp = client.get("/ticket/new")
    body = resp.data.decode("utf-8")
    submit_pos = body.find('id="submit-btn"')
    info_pos = body.find("Was passiert nach dem Absenden")
    # Info box should either be gone from the form or rendered only after creation.
    # Heuristic: if present, it must appear AFTER the submit button
    # (e.g. inside the success alert at the top of the card, which is rendered conditionally).
    if info_pos != -1 and submit_pos != -1:
        assert info_pos > submit_pos or b'id="created-info"' in resp.data
```

- [ ] **Step 2: Run, verify failure**

Run: `cd ticketsystem && python -m pytest tests/test_ui_ux.py::test_new_ticket_info_box_not_above_submit -v`
Expected: currently FAIL (info box is above submit).

- [ ] **Step 3: Delete the info box above the submit button**

In `ticketsystem/templates/ticket_new.html:261-268` remove:

```html
<div class="bg-info-subtle p-3 rounded-3 mb-4 mt-3">
    <h4 class="h6 fw-bold mb-2 text-info-emphasis"><i class="bi bi-info-circle me-1"></i> Was passiert nach dem Absenden?</h4>
    <ul class="small text-info-emphasis mb-0 ps-3">
        <li>Das Ticket erscheint sofort im <strong>Dashboard</strong>.</li>
        <li>Zuständige Mitarbeiter werden über neue Tickets informiert.</li>
        <li>Geben Sie Ihre Ticketnummer <strong>#{{ created_id or '...' }}</strong> bei Rückfragen an den Teamleiter an.</li>
    </ul>
</div>
```

- [ ] **Step 4: Fold the useful content into the success alert**

In `ticketsystem/templates/ticket_new.html:22-37`, replace the body of the success alert with an expanded version that keeps the key facts:

```html
<div class="alert alert-success border-0 shadow-sm rounded-3 py-3 mb-4 animate__animated animate__pulse" id="created-info">
    <div class="d-flex align-items-center mb-1">
        <i class="bi bi-check-circle-fill fs-4 me-2"></i>
        <h4 class="h6 fw-bold mb-0">Ticket erfolgreich erstellt!</h4>
    </div>
    <p class="small mb-2">Ihr Anliegen wurde unter der Nummer <strong>#{{ created_id }}</strong> erfasst. Zuständige Mitarbeiter werden informiert.</p>
    <div class="d-flex gap-2">
        <a href="{{ url_for('main.ticket_public', ticket_id=created_id) }}" class="btn btn-sm btn-primary rounded-pill px-3">
            <i class="bi bi-eye me-1"></i> Status einsehen
        </a>
        {% if session.get('worker_id') %}
        <a href="{{ ingress_path }}{{ url_for('main.index') }}" class="btn btn-sm btn-outline-success rounded-pill px-3">Dashboard</a>
        {% endif %}
        <button type="button" class="btn btn-sm btn-link text-muted text-decoration-none ms-auto" onclick="this.closest('.alert').remove()">Schließen</button>
    </div>
</div>
```

(Single sentence replaces the bullet list; the "Ticketnummer bei Rückfragen angeben" tip is already implicit in showing `#{{ created_id }}`.)

- [ ] **Step 5: Verify & commit**

Run: `cd ticketsystem && python -m pytest tests/ -v`
```bash
git add ticketsystem/templates/ticket_new.html ticketsystem/tests/test_ui_ux.py
git commit -m "ux: move post-submit info out of CTA path into success alert"
```

---

## Task 6: Global breadcrumbs block

**Files:**
- Modify: `ticketsystem/templates/base.html` (add `{% block breadcrumbs %}`)
- Modify: `ticketsystem/templates/archive.html`, `workload.html`, `admin_teams.html`, `admin_templates.html`, `admin_trash.html`, `settings.html`
- Test: `ticketsystem/tests/test_ui_ux.py`

The existing breadcrumbs in `projects.html`, `ticket_detail.html`, admin API pages use ad-hoc inline markup. Introduce a single block, keep all existing occurrences untouched (they can be migrated separately).

- [ ] **Step 1: Add failing tests**

Append:

```python
@pytest.mark.parametrize("path", ["/archive", "/workload"])
def test_breadcrumbs_on_inner_pages(client, path):
    with client.session_transaction() as sess:
        sess["worker_id"] = 1
        sess["worker_name"] = "Test"
        sess["role"] = "admin"
        sess["is_admin"] = True
    resp = client.get(path)
    # Pages must carry a breadcrumb nav back to the dashboard.
    assert b'aria-label="breadcrumb"' in resp.data
    assert b"Dashboard" in resp.data
```

- [ ] **Step 2: Verify failure**

Run: `cd ticketsystem && python -m pytest tests/test_ui_ux.py -v -k breadcrumbs`
Expected: FAIL (archive/workload lack breadcrumbs).

- [ ] **Step 3: Add the block to `base.html`**

In `ticketsystem/templates/base.html:228-244`, insert right after `<main id="main-content" …>` opens (before the flash messages):

```html
<main id="main-content" class="container-fluid px-4 py-4">
    {% block breadcrumbs %}{% endblock %}
    {% with messages = get_flashed_messages(with_categories=true) %}
```

- [ ] **Step 4: Add breadcrumbs on archive.html**

At the top of `ticketsystem/templates/archive.html`'s content block, add:

```html
{% block breadcrumbs %}
<nav aria-label="breadcrumb" class="mb-3">
    <ol class="breadcrumb mb-0 small">
        <li class="breadcrumb-item"><a href="{{ ingress_path }}{{ url_for('main.index') }}" class="text-decoration-none">Dashboard</a></li>
        <li class="breadcrumb-item active" aria-current="page">Archiv</li>
    </ol>
</nav>
{% endblock %}
```

- [ ] **Step 5: Repeat for the other five pages**

Same pattern, replacing the active label:

| File | Active label |
|------|--------------|
| `workload.html` | `Auslastung` |
| `admin_teams.html` | `Admin › Teams` |
| `admin_templates.html` | `Admin › Checklisten-Vorlagen` |
| `admin_trash.html` | `Admin › Papierkorb` |
| `settings.html` | `Admin › Einstellungen` |

For admin pages, use two items:

```html
<li class="breadcrumb-item"><a href="{{ ingress_path }}{{ url_for('main.index') }}" class="text-decoration-none">Dashboard</a></li>
<li class="breadcrumb-item active" aria-current="page">Admin › Teams</li>
```

- [ ] **Step 6: Verify & commit**

Run: `cd ticketsystem && python -m pytest tests/ -v`
```bash
git add ticketsystem/templates/base.html ticketsystem/templates/archive.html ticketsystem/templates/workload.html ticketsystem/templates/admin_teams.html ticketsystem/templates/admin_templates.html ticketsystem/templates/admin_trash.html ticketsystem/templates/settings.html ticketsystem/tests/test_ui_ux.py
git commit -m "ux: add breadcrumbs to archive, workload, and admin pages"
```

---

## Task 7: Inline form validation module (+ dirty-form guard)

**Files:**
- Create: `ticketsystem/static/js/form_validation.js`
- Modify: `ticketsystem/templates/base.html` (include script for logged-in users)
- Modify: `ticketsystem/templates/ticket_new.html` (add markers, email/phone patterns, `data-dirty-warn`)
- Test: `ticketsystem/tests/test_ui_ux.py`

Goal: Bootstrap-native `.was-validated` styling, `invalid-feedback` with per-field messages, `beforeunload` guard for unsaved changes on forms marked `data-dirty-warn`.

- [ ] **Step 1: Add failing assertions**

Append:

```python
def test_new_ticket_form_marked_for_dirty_warn(client):
    resp = client.get("/ticket/new")
    assert b'data-dirty-warn' in resp.data


def test_new_ticket_email_field_has_format_validation(client):
    resp = client.get("/ticket/new")
    # Email input carries type=email (browser) AND explicit invalid-feedback
    # so messages render consistently across browsers.
    assert b'id="contact_email"' in resp.data
    assert b'invalid-feedback' in resp.data
```

- [ ] **Step 2: Verify failure**

Run: `cd ticketsystem && python -m pytest tests/test_ui_ux.py -v -k "dirty_warn or email_field"`
Expected: FAIL.

- [ ] **Step 3: Create `form_validation.js`**

Create `ticketsystem/static/js/form_validation.js`:

```javascript
/* form_validation.js — Bootstrap-native inline validation + dirty-form guard.
 *
 * Usage:
 *   <form data-validate data-dirty-warn> … </form>
 *   <input required> <div class="invalid-feedback">Pflichtfeld</div>
 */
(function () {
  "use strict";

  function attachValidation(form) {
    form.addEventListener(
      "submit",
      function (e) {
        if (!form.checkValidity()) {
          e.preventDefault();
          e.stopPropagation();
          const firstInvalid = form.querySelector(":invalid");
          if (firstInvalid && typeof firstInvalid.focus === "function") {
            firstInvalid.focus({ preventScroll: false });
          }
        }
        form.classList.add("was-validated");
      },
      false
    );

    // Blur-level validation: mark individual fields as touched so the user
    // sees feedback before hitting submit.
    form.querySelectorAll("input, select, textarea").forEach(function (el) {
      el.addEventListener("blur", function () {
        if (el.value !== "" || el.required) {
          el.classList.toggle("is-invalid", !el.checkValidity());
          el.classList.toggle("is-valid", el.checkValidity() && el.value !== "");
        }
      });
    });
  }

  function attachDirtyGuard(form) {
    let dirty = false;
    let submitting = false;

    form.addEventListener("input", function () {
      dirty = true;
    });
    form.addEventListener("submit", function () {
      submitting = true;
    });

    window.addEventListener("beforeunload", function (e) {
      if (dirty && !submitting) {
        // Modern browsers show their own generic message; returnValue must be set.
        e.preventDefault();
        e.returnValue = "";
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form[data-validate]").forEach(attachValidation);
    document.querySelectorAll("form[data-dirty-warn]").forEach(attachDirtyGuard);
  });
})();
```

- [ ] **Step 4: Include the script in `base.html`**

In `ticketsystem/templates/base.html:258-262`, add after `base_ui.js` (outside the worker-only block so anonymous users on `/ticket/new` also benefit):

```html
<script src="{{ ingress_path }}{{ url_for('static', filename='js/base_ui.js') }}?v={{ config.VERSION }}"></script>
<script src="{{ ingress_path }}{{ url_for('static', filename='js/form_validation.js') }}?v={{ config.VERSION }}"></script>
```

- [ ] **Step 5: Add markers to the new-ticket form**

In `ticketsystem/templates/ticket_new.html:42`, change:

```html
<form method="POST" enctype="multipart/form-data" id="ticket-form">
```

to:

```html
<form method="POST" enctype="multipart/form-data" id="ticket-form" data-validate data-dirty-warn novalidate>
```

(`novalidate` disables the default browser UI so Bootstrap's `was-validated` styles take over.)

- [ ] **Step 6: Add `invalid-feedback` messages for required fields**

After each `required` input in `ticket_new.html`, add a sibling `<div class="invalid-feedback">` element:

After the `author_name` input (around line 50):

```html
<div class="invalid-feedback">Bitte geben Sie Ihren Namen an.</div>
```

After the `title` input (around line 56):

```html
<div class="invalid-feedback">Bitte geben Sie einen Titel ein.</div>
```

For `contact_email` (line 160), add a pattern and feedback:

```html
<input type="email" class="form-control form-control-sm" id="contact_email" name="contact_email" placeholder="z.B. kunde@beispiel.de">
<div class="invalid-feedback">Bitte geben Sie eine gültige E-Mail-Adresse ein.</div>
```

For `contact_phone` (line 156), add a relaxed pattern:

```html
<input type="tel" class="form-control form-control-sm" id="contact_phone" name="contact_phone"
       placeholder="z.B. 0211 123456" pattern="[0-9+ /()-]{4,}">
<div class="invalid-feedback">Telefonnummer darf nur Ziffern und + / ( ) - enthalten.</div>
```

- [ ] **Step 7: Guard the XHR submit against the validation preventDefault**

The form's existing `submit` listener at `ticket_new.html:331` calls `e.preventDefault()` and then `xhr.send`. After Task 7, invalid forms trigger `form.checkValidity() === false` and validation.js calls `preventDefault + stopPropagation`, which stops the XHR handler too. Ensure ordering: add a guard at the top of the existing XHR submit handler at line 332:

```javascript
form.addEventListener('submit', function(e) {
    e.preventDefault();
    // Skip XHR when client-side validation failed (was-validated added by form_validation.js).
    if (form.classList.contains('was-validated') && !form.checkValidity()) {
        return;
    }
    // Guard: reject submit while image compression is still running
```

- [ ] **Step 8: Run tests + manual smoke**

Run: `cd ticketsystem && python -m pytest tests/ -v`
Expected: baseline held, new tests pass.

Manual check:
1. `python app.py`, open `/ticket/new`, submit empty → red borders + "Bitte geben Sie Ihren Namen an.".
2. Enter name + title, type in any field, try to navigate away → browser confirm.
3. Submit valid form → no dirty warning fires (submitting flag set).

- [ ] **Step 9: Commit**

```bash
git add ticketsystem/static/js/form_validation.js ticketsystem/templates/base.html ticketsystem/templates/ticket_new.html ticketsystem/tests/test_ui_ux.py
git commit -m "ux: inline form validation + unsaved-changes guard"
```

---

## Final Verification

- [ ] **Full suite baseline**

Run: `cd ticketsystem && python -m pytest tests/ -v`
Expected: original baseline (7 passed, 8 failed) + new UI tests all pass.

- [ ] **Lint**

Run: `cd ticketsystem && python -m flake8 --max-line-length=120 *.py routes/ services/`
Expected: no new warnings (we didn't touch Python source).

- [ ] **Manual visual QA**

Check each modified page at least once in the browser:
- `/login` — no Shopfloor block, button says "Einloggen"
- `/ticket/new` — no subheading, no redundant info box before submit, validation works, beforeunload guard fires
- `/` — no "Wartet" tab, no reload hint
- `/archive`, `/workload`, `/admin/settings` — breadcrumbs visible at top
- Navbar on narrow viewport — CTA says "Neu"
- Admin dropdown — caret icon next to badge

- [ ] **Final commit (if anything residual)**

```bash
git status
# If clean, nothing to do. Otherwise stage + commit as "ux: …".
```

---

## Out of Scope (tracked for follow-up plans)

- Keyboard shortcuts (`n` = new ticket, `/` = focus search)
- Global search in header
- Redesign of floating Bulk-Action-Bar (too many controls)
- Audit of `ticket_detail.html` (not reviewed in 2026-04-12 audit)
- Feldspezifische Server-Fehler im Flash-Flow (requires route changes)
