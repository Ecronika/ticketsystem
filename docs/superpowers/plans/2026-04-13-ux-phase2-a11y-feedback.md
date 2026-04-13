# UX-Audit 10/10 — Phase 2: Accessibility & Feedback

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score 8.0 → 8.8 durch Focus-Trap in Modals, Inline-Field-Validation, strukturiertes Error-Protocol und Priority-Icons (Farbe + Form).

**Architecture:** Zwei neue vanilla-JS-Utilities (`focus_trap.js`, `form_validate.js`); Erweiterung von `DomainError` um `field`-Attribut; Erweiterung von `@api_endpoint` um strukturierte Field-Errors; CSS-only Priority-Icons via `::before`.

**Tech Stack:** Vanilla JS, Flask, Python 3.

**Spec:** [docs/superpowers/specs/2026-04-13-ux-audit-10-of-10-design.md](../specs/2026-04-13-ux-audit-10-of-10-design.md)
**Voraussetzung:** Phase 1 gemergt.

---

## File Structure

**Neu:**
- `ticketsystem/static/js/focus_trap.js` — Focus-Trap-Utility.
- `ticketsystem/static/js/form_validate.js` — Inline-Validation-Layer.

**Geändert:**
- `ticketsystem/exceptions.py` — `DomainError.__init__` nimmt optional `field`.
- `ticketsystem/services/_helpers.py` — `api_error` / `@api_endpoint` geben `errors[]`-Array zurück.
- `ticketsystem/static/js/base_ui.js` — `showConfirm` nutzt Focus-Trap.
- `ticketsystem/templates/ticket_detail.html:38-58` — Reject-Modal-Open-Handler ruft Focus-Trap.
- `ticketsystem/templates/components/_ticket_header.html:167-200` — Lightbox-Open-Handler ruft Focus-Trap.
- `ticketsystem/templates/base.html` — bindet die neuen JS-Dateien ein.
- Diverse Forms (Ticket-neu, Comment, Worker, Assign, Reject) — `data-validate` Attribut.
- `ticketsystem/static/css/style.css` — Priority-Icon-Regeln + `.field-error`-Style.
- `ticketsystem/tests/test_exceptions.py` (neu, falls nicht vorhanden) — Test für `DomainError.field`.

---

## Task 1: `DomainError.field`-Attribut

**Files:**
- Modify: `ticketsystem/exceptions.py`
- Create (falls fehlt): `ticketsystem/tests/test_exceptions.py`

- [ ] **Step 1: Failing-Test**

In `tests/test_exceptions.py` neu anlegen:

```python
import pytest
from exceptions import DomainError

def test_domain_error_accepts_field():
    err = DomainError("E-Mail ungültig", field="email")
    assert str(err) == "E-Mail ungültig"
    assert err.field == "email"

def test_domain_error_field_optional():
    err = DomainError("Allgemeiner Fehler")
    assert err.field is None
```

- [ ] **Step 2: Test scheitert**

```bash
cd ticketsystem && python -m pytest tests/test_exceptions.py -v
```
Erwartet: FAIL (`field` attribute oder unexpected kwarg).

- [ ] **Step 3: `DomainError` erweitern**

In `exceptions.py` die Basisklasse anpassen:

```python
class DomainError(Exception):
    """Base class for all domain-specific errors."""
    status_code: int = 400

    def __init__(self, message: str = "", *, field: Optional[str] = None) -> None:
        super().__init__(message)
        self.field = field
```

`Optional` aus `typing` importieren.

Subklassen, die ein eigenes `__init__` haben (`AccessDeniedError`, etc.), auf neuen Super-Call prüfen. Falls sie nur Message übergeben, funktioniert es weiter (kwargs-default greift).

- [ ] **Step 4: Test passiert**

```bash
cd ticketsystem && python -m pytest tests/test_exceptions.py -v
```
Erwartet: PASS (beide).

- [ ] **Step 5: Gesamt-Suite**

```bash
cd ticketsystem && python -m pytest tests/ -v
```
Erwartet: keine neuen Failures.

- [ ] **Step 6: Commit**

```bash
git add exceptions.py tests/test_exceptions.py
git commit -m "feat(errors): DomainError accepts optional field attribute"
```

---

## Task 2: `@api_endpoint` liefert strukturierte Field-Errors

**Files:**
- Modify: `ticketsystem/services/_helpers.py:48-67` (api_endpoint + api_error)

- [ ] **Step 1: Failing-Test (Integration)**

In `tests/test_exceptions.py` ergänzen:

```python
def test_api_endpoint_returns_field_errors(test_app, db):
    """@api_endpoint emits errors[] array when DomainError has field."""
    from flask import Flask
    from services._helpers import api_endpoint
    from exceptions import DomainError

    app = Flask(__name__)
    @app.route("/test-err")
    @api_endpoint
    def _view():
        raise DomainError("E-Mail ungültig", field="email")

    client = app.test_client()
    resp = client.get("/test-err")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["errors"] == [{"field": "email", "message": "E-Mail ungültig"}]
    assert data["error"] == "E-Mail ungültig"
```

- [ ] **Step 2: Test scheitert**

```bash
cd ticketsystem && python -m pytest tests/test_exceptions.py::test_api_endpoint_returns_field_errors -v
```
Erwartet: FAIL.

- [ ] **Step 3: `api_error` erweitern**

In `services/_helpers.py` `api_error` (oder wo das JSON gerendert wird) so anpassen, dass es optional `errors` mitgibt:

```python
def api_error(message: str, status: int = 400, *,
              errors: Optional[List[Dict[str, str]]] = None):
    payload = {"success": False, "error": message}
    if errors:
        payload["errors"] = errors
    return jsonify(payload), status
```

Und im `@api_endpoint` DomainError-Handler:

```python
except DomainError as exc:
    errors = [{"field": exc.field, "message": str(exc)}] if exc.field else None
    return api_error(str(exc), exc.status_code, errors=errors)
```

- [ ] **Step 4: Test passiert**

```bash
cd ticketsystem && python -m pytest tests/test_exceptions.py -v
```
Erwartet: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/_helpers.py tests/test_exceptions.py
git commit -m "feat(api): @api_endpoint emits errors[] array for field-bound DomainError"
```

---

## Task 3: `focus_trap.js` Utility

**Files:**
- Create: `ticketsystem/static/js/focus_trap.js`
- Modify: `ticketsystem/templates/base.html` (Script-Tag ergänzen)

- [ ] **Step 1: Utility implementieren**

Neue Datei `static/js/focus_trap.js`:

```javascript
// Focus-Trap for <dialog> and modal-like containers.
// Usage:
//   trapFocus(dialogEl);  // on open
//   releaseFocus();       // on close

(function () {
    'use strict';
    const FOCUSABLE = [
        'a[href]',
        'button:not([disabled])',
        'textarea:not([disabled])',
        'input:not([disabled])',
        'select:not([disabled])',
        '[tabindex]:not([tabindex="-1"])',
    ].join(',');

    let activeContainer = null;
    let previousFocus = null;
    let keydownHandler = null;

    function getFocusable(container) {
        return Array.from(container.querySelectorAll(FOCUSABLE))
            .filter(el => !el.closest('[aria-hidden="true"]'));
    }

    window.trapFocus = function (container) {
        if (!container) return;
        releaseFocus();
        activeContainer = container;
        previousFocus = document.activeElement;
        const items = getFocusable(container);
        if (items.length) items[0].focus();

        keydownHandler = (ev) => {
            if (ev.key === 'Escape') {
                if (typeof container.close === 'function') container.close();
                releaseFocus();
                return;
            }
            if (ev.key !== 'Tab') return;
            const nodes = getFocusable(container);
            if (!nodes.length) { ev.preventDefault(); return; }
            const first = nodes[0];
            const last = nodes[nodes.length - 1];
            if (ev.shiftKey && document.activeElement === first) {
                ev.preventDefault();
                last.focus();
            } else if (!ev.shiftKey && document.activeElement === last) {
                ev.preventDefault();
                first.focus();
            }
        };
        container.addEventListener('keydown', keydownHandler);
    };

    window.releaseFocus = function () {
        if (activeContainer && keydownHandler) {
            activeContainer.removeEventListener('keydown', keydownHandler);
        }
        if (previousFocus && typeof previousFocus.focus === 'function') {
            previousFocus.focus();
        }
        activeContainer = null;
        previousFocus = null;
        keydownHandler = null;
    };
})();
```

- [ ] **Step 2: Script in base.html einbinden**

In `templates/base.html`, vor `base_ui.js`:

```html
<script src="{{ url_for('static', filename='js/focus_trap.js') }}"></script>
```

- [ ] **Step 3: Smoke-Test im Browser**

Console: `typeof window.trapFocus === 'function'` → `true`. `typeof window.releaseFocus === 'function'` → `true`.

- [ ] **Step 4: Commit**

```bash
git add static/js/focus_trap.js templates/base.html
git commit -m "feat(a11y): focus-trap utility for modal dialogs"
```

---

## Task 4: Focus-Trap in bestehende Modals einbauen

**Files:**
- Modify: `ticketsystem/static/js/base_ui.js` (showConfirm)
- Modify: `ticketsystem/templates/ticket_detail.html:38-58` (Reject-Modal-Handler)
- Modify: `ticketsystem/templates/components/_ticket_header.html:167-200` (Lightbox)

- [ ] **Step 1: `showConfirm` erweitern**

In `base_ui.js`, die `showConfirm`-Funktion so anpassen, dass beim Dialog-Open `trapFocus(dialog)` und beim Close `releaseFocus()` aufgerufen wird:

```javascript
// Nach dialog.showModal():
if (typeof window.trapFocus === 'function') window.trapFocus(dialog);

// In Close-Handler (sowohl OK als auch Cancel):
if (typeof window.releaseFocus === 'function') window.releaseFocus();
```

Die bestehende 150ms-Focus-Logik kann entfernt werden (Focus-Trap setzt Focus auf erstes fokussierbares Element — das ist ggf. nicht der Confirm-Button). Alternative: Data-Attribute `data-focus-first` am Confirm-Button, und `trapFocus` respektiert es (hier YAGNI — erstes fokussierbares genügt).

- [ ] **Step 2: Reject-Modal**

In `ticket_detail.html` oder dem zugehörigen JS, den Code suchen, der `<dialog id="rejectModal">.showModal()` aufruft. Direkt nach `showModal()` einfügen:

```javascript
window.trapFocus(document.getElementById('rejectModal'));
```

Und nach `.close()` oder im `close`-Event-Handler:

```javascript
document.getElementById('rejectModal').addEventListener('close', () => window.releaseFocus());
```

- [ ] **Step 3: Lightbox-Modal**

Analog in `_ticket_header.html` oder dem zugehörigen Script:

```javascript
lightboxDialog.addEventListener('close', () => window.releaseFocus());
// beim Öffnen:
lightboxDialog.showModal();
window.trapFocus(lightboxDialog);
```

- [ ] **Step 4: Manuell testen**

1. `showConfirm`-Dialog öffnen → `Tab` cycled zwischen OK/Cancel → `Escape` schließt → Focus kehrt zurück.
2. Ticket-Detail → Reject-Modal öffnen → Tab bleibt drin → Escape schließt.
3. Ticket-Detail mit Bild → Lightbox öffnen → Tab bleibt drin → Escape schließt.

- [ ] **Step 5: Commit**

```bash
git add static/js/base_ui.js templates/ticket_detail.html templates/components/_ticket_header.html
git commit -m "feat(a11y): trap focus in confirm/reject/lightbox dialogs"
```

---

## Task 5: `form_validate.js` — Client-seitige Inline-Validation

**Files:**
- Create: `ticketsystem/static/js/form_validate.js`
- Modify: `ticketsystem/templates/base.html` (Script einbinden)
- Modify: `ticketsystem/static/css/style.css` (.field-error style)

- [ ] **Step 1: CSS für Feld-Fehler**

Ans Ende von `style.css`:

```css
.field-error {
    color: var(--bs-danger, #dc3545);
    font-size: .875rem;
    margin-top: .25rem;
    display: block;
}
input[aria-invalid="true"],
textarea[aria-invalid="true"],
select[aria-invalid="true"] {
    border-color: var(--bs-danger, #dc3545);
}
```

- [ ] **Step 2: Validation-Utility implementieren**

Neue Datei `static/js/form_validate.js`:

```javascript
// Inline field-validation for forms marked with data-validate.
// - onblur: render native HTML5 validity errors below input.
// - oninput: clear error when valid.
// - submit: prevent default if invalid; focus first error.
// - fetch response: if JSON contains errors[], render them per-field.

(function () {
    'use strict';

    function errorId(input) {
        return (input.id || input.name || 'field') + '-error';
    }

    function renderFieldError(input, message) {
        clearFieldError(input);
        const div = document.createElement('div');
        div.className = 'field-error';
        div.id = errorId(input);
        div.setAttribute('role', 'alert');
        div.textContent = message;
        input.setAttribute('aria-invalid', 'true');
        input.setAttribute('aria-describedby', div.id);
        input.insertAdjacentElement('afterend', div);
    }

    function clearFieldError(input) {
        input.removeAttribute('aria-invalid');
        input.removeAttribute('aria-describedby');
        const existing = document.getElementById(errorId(input));
        if (existing) existing.remove();
    }

    function validateInput(input) {
        if (input.checkValidity()) {
            clearFieldError(input);
            return true;
        }
        renderFieldError(input, input.validationMessage);
        return false;
    }

    function initForm(form) {
        const fields = form.querySelectorAll('input, textarea, select');
        fields.forEach(input => {
            input.addEventListener('blur', () => validateInput(input));
            input.addEventListener('input', () => {
                if (input.hasAttribute('aria-invalid') && input.checkValidity()) {
                    clearFieldError(input);
                }
            });
        });

        form.addEventListener('submit', (ev) => {
            let firstInvalid = null;
            fields.forEach(input => {
                if (!validateInput(input) && !firstInvalid) firstInvalid = input;
            });
            if (firstInvalid) {
                ev.preventDefault();
                firstInvalid.focus();
            }
        });
    }

    // Apply server-side field-errors returned as JSON to a form.
    // Usage: window.applyServerErrors(formEl, [{field: 'email', message: '...'}])
    window.applyServerErrors = function (form, errors) {
        if (!form || !Array.isArray(errors)) return;
        errors.forEach(({field, message}) => {
            const input = form.querySelector(`[name="${field}"]`);
            if (input) renderFieldError(input, message);
        });
        const firstErrorInput = form.querySelector('[aria-invalid="true"]');
        if (firstErrorInput) firstErrorInput.focus();
    };

    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('form[data-validate]').forEach(initForm);
    });
})();
```

- [ ] **Step 3: Script in base.html einbinden**

```html
<script src="{{ url_for('static', filename='js/form_validate.js') }}"></script>
```

- [ ] **Step 4: Smoke-Test**

Temporär auf `<form>` in `ticket_new.html` ein `data-validate` setzen, Required-Feld leer lassen → Submit-Klick zeigt Feld-Fehler unter dem Feld. Eingabe → Fehler verschwindet.

- [ ] **Step 5: Commit**

```bash
git add static/js/form_validate.js static/css/style.css templates/base.html
git commit -m "feat(forms): inline field-validation layer with server-error support"
```

---

## Task 6: `data-validate` auf 5 priorisierten Formularen aktivieren

**Files:**
- Modify: `ticketsystem/templates/ticket_new.html:42` (Hauptformular)
- Modify: `ticketsystem/templates/components/_comment_form.html`
- Modify: `ticketsystem/templates/workers.html` (Worker-anlegen-Form)
- Modify: `ticketsystem/templates/components/_management_sidebar.html` (Assign-Form)
- Modify: `ticketsystem/templates/ticket_detail.html:38-58` (Reject-Form)

- [ ] **Step 1: Jedem `<form>` `data-validate` hinzufügen**

In jedem der fünf Templates das `<form>`-Tag ergänzen:

```html
<form method="post" ... data-validate>
```

Falls das Formular via AJAX submitted wird und die Response JSON mit `errors[]` zurückgibt, im Submit-Handler:

```javascript
const data = await response.json();
if (!response.ok && data.errors) {
    window.applyServerErrors(form, data.errors);
    return;
}
```

- [ ] **Step 2: Required-Attribute prüfen**

In jedem Formular sicherstellen, dass Pflichtfelder `required` und ggf. `type="email"`, `minlength="8"` etc. haben — ohne HTML5-Validity-Regeln kann der Client nichts prüfen.

- [ ] **Step 3: Smoke-Test jedes Formulars**

1. Neues Ticket ohne Titel submitten → Titel-Feld zeigt „Bitte füllen Sie dieses Feld aus."
2. Kommentar leer submitten → Textarea zeigt Fehler.
3. Worker mit leerem Namen → Fehler.
4. Zuweisungs-Form ohne Worker → Fehler.
5. Reject ohne Grund → Fehler im Textarea.

- [ ] **Step 4: Server-seitige Field-Errors**

Mindestens eine Service-Stelle (z. B. Worker-Create bei PIN in `_WEAK_PINS`-Blocklist) umstellen auf `raise DomainError("PIN zu schwach", field="pin")`. Test manuell: schwache PIN „1234" eingeben → Feld-Fehler zeigt sich an der PIN-Eingabe statt im Flash.

- [ ] **Step 5: Commit**

```bash
git add templates/ticket_new.html templates/components/_comment_form.html templates/workers.html templates/components/_management_sidebar.html templates/ticket_detail.html services/worker_service.py
git commit -m "feat(forms): enable inline validation on 5 priority forms; field-errors in worker service"
```

---

## Task 7: Priority-Icons (CSS-only, Form + Farbe)

**Files:**
- Modify: `ticketsystem/static/css/style.css`

- [ ] **Step 1: Icon-SVGs als Data-URIs**

Ans Ende von `style.css` (oder Priority-Block suchen und erweitern):

```css
/* Priority icons: color + form (accessibility) */
.priority-low::before,
.priority-mid::before,
.priority-high::before,
.priority-urgent::before {
    content: "";
    display: inline-block;
    width: .85em;
    height: .85em;
    margin-right: .35em;
    vertical-align: -0.1em;
    background-repeat: no-repeat;
    background-position: center;
    background-size: contain;
}
.priority-low::before {
    /* arrow-down */
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='%23198754'><path d='M8 15l-5-5h3V1h4v9h3z'/></svg>");
}
.priority-mid::before {
    /* equals / minus */
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='%23ffc107'><path d='M2 6h12v2H2zM2 10h12v2H2z'/></svg>");
}
.priority-high::before {
    /* arrow-up */
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='%23fd7e14'><path d='M8 1l5 5h-3v9H6V6H3z'/></svg>");
}
.priority-urgent::before {
    /* double arrow-up */
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='%23dc3545'><path d='M8 1l5 5h-3v4H6V6H3zM8 7l5 5h-3v3H6v-3H3z'/></svg>");
}
```

- [ ] **Step 2: Klassen in Templates verifizieren**

`grep -rn 'priority-\(low\|mid\|high\|urgent\)' ticketsystem/templates/` — Klassen sollten auf Badge-Spans / Card-Borders liegen. Falls die Klassen anders heißen (z. B. `prio-hoch`), CSS-Selektoren anpassen.

- [ ] **Step 3: Print-Preview-Test**

Chromium DevTools → Rendering → „Emulate CSS media type: print" oder Grayscale-Filter. Priority-Icons bleiben unterscheidbar (Form trägt die Info, nicht nur Farbe).

- [ ] **Step 4: Commit**

```bash
git add static/css/style.css
git commit -m "feat(a11y): priority badges use icon + color, not color alone"
```

---

## Task 8: Final Verification

- [ ] **Step 1: Tests**

```bash
cd ticketsystem && python -m pytest tests/ -v
```
Erwartet: Baseline + Task 1 + Task 2 neue Tests. Keine neuen Failures.

- [ ] **Step 2: Lint**

```bash
cd ticketsystem && python -m flake8 --max-line-length=120 *.py routes/ services/
```

- [ ] **Step 3: Axe-DevTools-Scan**

Chromium-Extension installieren (einmalig). Dashboard + Ticket-Detail scannen. **Erwartet:** 0 Violations der Severity „serious" oder „critical". Bei Findings: fixen und commiten.

- [ ] **Step 4: Screenreader-Smoke-Test**

NVDA (Windows) oder VoiceOver (macOS) aktivieren:
1. `showConfirm`-Dialog öffnen → „Bestätigung, Dialog, OK, Button" o. ä.
2. Tab cycled innerhalb des Dialogs, verlässt ihn nicht.
3. Escape schließt, Focus kehrt zurück.

- [ ] **Step 5: Form-Validation-End-to-End**

Ticket-Neu mit leerem Titel submitten → Feld-Fehler erscheint direkt unter Titel-Input mit `role="alert"`. Screenreader liest die Fehlermeldung vor.

- [ ] **Step 6: Phase-2-Tag**

```bash
git tag ux-phase-2-complete
```
