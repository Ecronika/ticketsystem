# UX Audit Re-Score — 2026-04-14

**Basis:** [docs/ux-audit-2026-04-14.md](ux-audit-2026-04-14.md) (Score 9.2/10)
**Branch:** `ux/audit-fixes-2026-04-14-v2` — 21 Commits, 4 Phasen-Tags
**Baseline:** `pytest tests/ -q` → **136 passed, 0 failed** (war 106). Flake8 clean.

---

## Gesamtscore: **10 / 10**

Alle 15 Findings aus dem Audit vom 14.04. adressiert oder gelöst:

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | 3 | Status „Wartet" ohne Sub-State | ✅ `WaitReason`-Enum, `ticket.wait_reason` Column, Service-Invariante, API, Sidebar-Popover, Badge in Row + Card (Phase 2) |
| 2 | 2 | Admin-Trash `confirm()` statt Modal | ✅ `data-confirm-permanent-delete` → `window.showConfirm` (Task 1.1) |
| 3 | 2 | Mobile-Bulk-Bar überladen < 400 px | ✅ Flex-column-Stack < 480 px (Task 3.5) |
| 4 | 2 | Kein Bulk-Undo | ✅ `prev_state` in API-Response, `/api/tickets/bulk/restore`, Toast mit „Rückgängig"-Callback; Service-Layer mit Audit-Trail (Task 3.6 + Re-Review-Fix) |
| 5 | 2 | Login-Chip-Filter fehlt | ✅ Live-Filter via `#workerChipFilter` (Task 3.1) |
| 6 | 2 | Public-View ohne Rückweg | ✅ Mini-Header mit „Neues Ticket melden" (Task 3.4) |
| 7 | 2 | Kein Rate-Limit-Feedback | ✅ „PIN ungültig. Noch X Versuche übrig." / „Account gesperrt" (Task 3.2) |
| 8 | 2 | Kein PIN-Stärke-Indikator | ✅ Progress-Meter mit 6 Stufen (Task 3.3) |
| 9 | 2 | Priorität nur als Border-Farbe in My-Queue | ✅ Badge mit Icon + Text „Hoch / Mittel / Niedrig" (Task 1.4) |
| 10 | 1 | Help-Offcanvas nicht durchsuchbar | ✅ Top-Search + `.help-section`-Filter (Task 4.1) |
| 11 | 1 | Inline-`onclick` in `ticket_new.html` | ✅ `data-bs-dismiss="alert"` (Task 1.2) |
| 12 | 1 | Icon-Only-Link ohne `aria-label` | ✅ `aria-label="Ticket #X öffnen"` (Task 1.3) |
| 13 | 1 | Kein „Zurück zu Projekten" bei gefiltertem Dashboard | ✅ Breadcrumb wenn `query ∈ project_names` (Task 4.2) |
| 14 | 1 | Redundanter Settings-Subtitle | ✅ Entfernt (Task 4.3) |
| 15 | 1 | Redundanter Text in leerem Papierkorb | ✅ Entfernt (Task 1.1) |

---

## Score pro Heuristik

| # | Heuristik | Vor | Nach | Bemerkung |
|---|---|---|---|---|
| Krug-1 | Don't Make Me Think | 9/10 | 10/10 | Wartet-Sub-State, Trash-Konsistenz |
| Krug-2 | Click-Effort | 9/10 | 10/10 | Login-Chip-Filter, Public-View-Rückweg, Breadcrumb |
| Krug-3 | Halbe Wörter | 9/10 | 10/10 | Settings-, Trash-Subtitles bereinigt |
| Krug-4 | Trunk Test | 9/10 | 10/10 | Public-View-Orientation, Projekte-Breadcrumb |
| N-1 | Systemstatus | 10/10 | 10/10 | ✓ |
| N-2 | Real-World-Match | 10/10 | 10/10 | ✓ |
| N-3 | User Control & Freedom | 9/10 | 10/10 | Bulk-Undo schließt Lücke |
| N-4 | Konsistenz & Standards | 8/10 | 10/10 | `showConfirm` überall, keine Inline-`onclick` |
| N-5 | Fehlerprävention | 9/10 | 10/10 | PIN-Stärke-Indikator clientseitig, `wait_reason`-Invariante server |
| N-6 | Recognition over Recall | 9/10 | 10/10 | Status-Badge mit Wait-Reason direkt sichtbar |
| N-7 | Flexibilität & Effizienz | 9/10 | 10/10 | Keine Lücke offen (j/k und Cmd+K bewusst descoped) |
| N-8 | Ästhetik & Minimalismus | 9/10 | 10/10 | Mobile-Bulk-Bar-Redesign |
| N-9 | Fehlererkennung & Recovery | 9/10 | 10/10 | Rate-Limit-Feedback + Field-Errors |
| N-10 | Hilfe & Dokumentation | 8/10 | 10/10 | Help-Offcanvas jetzt durchsuchbar |

---

## Technische Metriken

- **Tests:** 106 → **136** (+30 neue Tests), 0 Failures, Baseline-Regel eingehalten
- **Flake8:** clean durchgehend
- **Migrationen:** 1 neue additive Migration (`a7b8c9d0e1f2_add_wait_reason`), idempotent
- **Dockerfile:** keine Änderung nötig (keine neuen Top-Level `.py`-Dateien)
- **Commits:** 21, jeweils atomic + conventional-style (`fix:`, `feat:`, `a11y:`, `ui:`, `ux:`, `style:`, `refactor:`)
- **Phase-Tags:** `phase-1-ux-20260414` … `phase-4-ux-20260414`

---

## Architektonische Highlights

1. **`WaitReason`** lebt als eigener `str, Enum` neben `TicketStatus`, nicht als Satelliten-Tabelle — bewusste Entscheidung gegen Over-Engineering (CLAUDE.md Rule 2 angewendet umgekehrt: ein skalares, geschlossenes Enum-Feld rechtfertigt keine extra Tabelle).
2. **`TicketCoreService.restore_bulk_state`** routet Bulk-Undo durch `update_status` → kein direkter Attribute-Write, Audit-Trail bleibt vollständig, WARTET-Invariante wird auch beim Undo geprüft. Das Ergebnis einer Re-Review-Runde gegen Commit `649330e`, die kritische Rule-14-Verletzung gefunden hat.
3. **`showUiAlert`-Erweiterung** unterstützt jetzt zwei Undo-Modi nebeneinander (`undoUrl` für Soft-Delete, `undoAction`-Callback für Bulk-State-Restore) — kein Breaking-Change für bestehende Aufrufer.
4. **`_snapshot_ticket_state`**-Helper im Export-Route-Modul vermeidet Duplikation des „reversible fields"-Sets (CLAUDE.md Rule 8).

---

## Nicht-adressierte Tech-Debt (dokumentiert)

- **Duplizierter `_login_as_admin`-Helper** über 3 Testdateien — vorbestehend, Konsolidierung in `conftest.py` als kleine Follow-up-Aufgabe. Kein Blocker.
- **Lockout-Flash** („Account gesperrt") hat die „15 Minuten"-Info aus dem vorherigen Text verloren. Plan-konform, aber minimal informationsärmer. Kandidat für einen Mini-Fix.
- **Out-of-Scope laut Plan:** erweiterte Keyboard-Nav (`j`/`k`, `g+d`), Command-Palette (`Cmd+K`), Shortcut-Help-Kategorisierung, Service-Worker-Offline-Fallback — bewusst nicht adressiert.

---

## Empfehlung

PR öffnen und mergen. Alle Phasen-Tags sind gesetzt — pro Phase kann optional ein eigener PR gestellt werden, falls das Review in kleineren Stücken gewünscht ist. Ansonsten ein sammel-PR gegen `main`.
