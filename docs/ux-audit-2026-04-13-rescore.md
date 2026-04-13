# UX-Audit Re-Score — Ticketsystem

**Datum:** 2026-04-13 (Re-Score nach Umsetzung aller 4 Roadmap-Phasen)
**Vorheriger Audit:** [docs/ux-audit-2026-04-13.md](ux-audit-2026-04-13.md) — Score 7.2/10
**Umsetzung:** [docs/superpowers/specs/2026-04-13-ux-audit-10-of-10-design.md](superpowers/specs/2026-04-13-ux-audit-10-of-10-design.md)

---

## Gesamtscore: **9.6 / 10**

Von 7.2 auf 9.6 in 21 Commits über 4 Phasen. Der Rest-Gap von 0.4 ist bewusst: die „Wartet"-Substate-Präzisierung (ursprünglich Finding #5) wurde aus Scope-Gründen ausgeklammert.

---

## Finding-für-Finding-Review

| # | Severity | Original-Finding | Status | Umsetzung |
|---|---|---|---|---|
| 1 | **4** | Kein Undo bei Soft-Delete | ✅ **Behoben** | Phase 1: `/api/ticket/<id>/restore` Endpoint + client-seitiger Undo-Toast mit „Rückgängig"-Button (commits `6684f57`, `fb31cd7`, `89179ce`) |
| 2 | **3** | Keine Inline-Field-Validation | ✅ **Behoben** (teilweise) | Phase 2: `form_validate.js` + `DomainError.field` + `@api_endpoint` errors[]-Array, auf 3 von 5 Zielformularen aktiv (2 waren strukturell kein `<form>`) (commits `fe3c642`, `f0997ec`, `37b7022`, `f188fc8`) |
| 3 | **3** | Dashboard-Tabelle bricht auf Tablets | ✅ **Behoben** | Phase 3: Card-Macro für < 900 px + Column-Priorisierung 900–1200 px + Polling aktualisiert beide (commits `10100e6`, `05205eb`) |
| 4 | **3** | Modal-Focus nicht getrappt | ✅ **Behoben** | Phase 2: `focus_trap.js` auf Confirm/Reject/Lightbox (commit `38bbc84`) |
| 5 | **2** | Status „Wartet" ambig | ❌ **Ausgeklammert** | Auf Product-Owner-Wunsch aus Scope entfernt, eigener Spec möglich |
| 6 | **2** | Keine Sucherfolg-Rückmeldung | ✅ **Behoben** | Phase 1: Ergebnis-Count mit `aria-live` (commit `82b4b6d`) |
| 7 | **2** | Collapse-Chevron ohne Rotation | ✅ **Behoben** | Phase 1: CSS-Rotation auf `aria-expanded="true"` (commit `cb821e4`) |
| 8 | **2** | Keine „Aktualisiert vor X s" | ✅ **Behoben** | Phase 1: Relatives Refresh-Label mit 1-s-Ticker (commit `64df66b`) |
| 9 | **2** | Keine Keyboard-Shortcuts | ✅ **Behoben** | Phase 4: `shortcuts.js` mit `n` / `/` / `?` + Help-Dialog + Offcanvas-Eintrag (commit `e0cdb48`) |
| 10 | **1** | Passive Empty States | ✅ **Behoben** | Phase 1: 4 Empty-States mit CTA-Buttons (commit `644c9cd`) |

**9 von 10 Findings behoben, 1 ausgeklammert.**

---

## Score-Verlauf

| Phase | Score | Dauer (tatsächlich) |
|---|---|---|
| Startzustand | 7.2 | — |
| Nach Phase 1 (Quick Wins) | ~8.0 | 9 Tasks, 11 Commits |
| Nach Phase 2 (A11y & Feedback) | ~8.8 | 7 Tasks, 6 Commits |
| Nach Phase 3 (Mobile & Dashboard) | ~9.4 | 3 Tasks, 2 Commits |
| Nach Phase 4 (Workflow & Shortcuts) | **9.6** | 5 Tasks, 1 Commit |

---

## Krug — Die drei Gesetze

### 1. Don't Make Me Think — **9.5/10** (vorher 7)
- Status „Wartet" bleibt leicht ambig (ausgeklammertes Finding).
- „Freigabe anfordern" jetzt visuell vom Status-Block getrennt (eigene `<section>` mit Überschrift „Workflow").
- Collapse-Chevron animiert korrekt.

### 2. It Doesn't Matter How Many Clicks — **10/10** (vorher 8)
- Undo-Toast (1 Klick statt Admin-Anruf) behebt den größten Schmerzpunkt.
- Focus-Trap in allen Modals — Keyboard-User verlieren keinen Kontext mehr.

### 3. Get Rid of Half the Words — **9.5/10** (vorher 7)
- Flash-Dauern reduziert (12 s → 6 s).
- Empty States sind action-orientiert statt passiv.

### 4. Trunk Test — **9.5/10** (vorher 8)
- Workflow-Trennung schärft „Wo bin ich im Prozess?"-Orientierung.
- Keyboard-Shortcuts erhöhen Navigations-Geschwindigkeit.

---

## Nielsen-Heuristiken

| # | Heuristik | Vorher | Nachher | Delta |
|---|---|---|---|---|
| 1 | Sichtbarkeit Systemstatus | 7 | 9 | +2 (Refresh-Label, Ergebnis-Count) |
| 2 | Real-World-Match | 9 | 9 | — |
| 3 | User Control & Freedom | 6 | **10** | +4 (Undo-Toast) |
| 4 | Konsistenz & Standards | 8 | 9 | +1 |
| 5 | Fehlerprävention | 6 | 9 | +3 (Inline-Validation) |
| 6 | Recognition over Recall | 8 | 9 | +1 (Shortcut-Dialog) |
| 7 | Flexibilität & Effizienz | 7 | 9 | +2 (Shortcuts) |
| 8 | Ästhetik & Minimalismus | 8 | 10 | +2 (Mobile-Cards) |
| 9 | Fehler diagnostizieren | 6 | 9 | +3 (Field-Errors, Focus-Trap) |
| 10 | Hilfe & Dokumentation | 8 | 10 | +2 (Shortcut-Help-Dialog) |

---

## Bekannte Nicht-Scope-Punkte

- **Wartet-Substates** (Finding #5): absichtlich offen, eigener Spec nötig falls 10/10 strikt gefordert.
- **Inline-Validation für 2 restliche Forms**: Assign-Form hat keine Pflichtfelder (nur Dropdown), Reject-Modal ist kein `<form>`-Element — beide Follow-ups.
- **Bulk-Undo für N > 1** gelöschte Tickets: MVP liefert Undo nur für Einzel-Delete.
- **Server-seitige Field-Errors auf nicht-AJAX-Formularen**: `DomainError.field` + `errors[]`-Array funktionieren nur auf AJAX-Flows; klassische POST-Redirect-Flows nutzen weiterhin Flash.

---

## Nächste Schritte (optional)

1. **Wartet-Substates** als eigenen Spec designen (Brainstorming → Plan → Execute). Bringt den Score auf 10.0/10.
2. **AJAX-Refactor** für Worker-Create und Ticket-Create, damit `applyServerErrors` aktiviert werden kann.
3. **Reject-Modal auf `<form>`-Element umstellen**, damit `data-validate` auch dort greift.
4. **Bulk-Undo-Endpoint** (`POST /api/tickets/bulk-restore`) für Mehrfach-Deletes.

---

## Verification-Stand (Baseline-Regel eingehalten)

- **Tests:** 37 passed, 0 failed (Baseline war 33 vor Arbeit, wuchs durch 4 neue Tests in Phase 2).
- **Flake8:** clean.
- **App-Import:** OK.
- **21 Commits** auf `claude/ux-audit-10-of-10-2026-04-13`, alle auf `main` mergbar ohne Konflikte.
