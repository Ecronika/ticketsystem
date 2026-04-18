# Design: Konfigurierbarer Berichtsversand

**Datum:** 2026-04-18
**Scope:** SLA-Eskalationsjob — Versandzeit, Wochentage, Feiertage

---

## Problemstellung

Der SLA-Eskalationsjob (E-Mail-Digests für Bearbeiter und Admins) läuft täglich
um 07:00 UTC — auch an Wochenenden und Feiertagen, an denen niemand arbeitet.
Admins sollen Versandzeit, aktive Wochentage und Feiertags-Ausnahmen konfigurieren
können.

## Entscheidungen

| Frage | Entscheidung |
|-------|-------------|
| Welche Jobs konfigurierbar? | Nur SLA-Eskalation (E-Mail-Digests) |
| Feiertage und SLA-Berechnung? | Feiertage betreffen nur Versand, nicht Grace-Period |
| Pausierung | Kompletter Job pausiert an Nicht-Versandtagen (keine Kommentare, keine Notifications, keine E-Mails) |
| Feiertags-Datenbasis | `holidays`-Paket zur Laufzeit + eigene Tabelle für zusätzliche freie Tage |
| Scheduler-Ansatz | Dynamisches Rescheduling via APScheduler |
| Zeitzone | Fest `Europe/Berlin`, Umrechnung via `zoneinfo` (Standardbibliothek) |
| UI-Platzierung | Neuer Abschnitt auf bestehender Settings-Seite |

## Datenmodell

### Neue SystemSettings-Keys

| Key | Beispielwert | Default | Beschreibung |
|-----|-------------|---------|-------------|
| `report_send_time` | `"08:00"` | `"07:00"` | Versandzeit in `Europe/Berlin` (`HH:MM`) |
| `report_weekdays` | `"1,2,3,4,5"` | `"1,2,3,4,5"` | Aktive Wochentage, ISO-Nummern (1=Mo, 7=So) |
| `report_federal_state` | `"NW"` | `null` | ISO-3166-2:DE Kürzel oder null (kein Feiertagsfilter) |

### Neue Tabelle `custom_holiday`

| Spalte | Typ | Beschreibung |
|--------|-----|-------------|
| `id` | Integer, PK | Auto-Increment |
| `date` | Date, unique, not null | Das Datum des freien Tages |
| `label` | String(100), not null | Beschreibung (z.B. "Betriebsferien") |

Alembic-Migration erforderlich.

## Dependency

**Neues Paket:** `holidays` in `requirements.txt`. Keine transitiven Dependencies.
Deckt alle 16 deutschen Bundesländer ab.

**Zeitzonen:** `zoneinfo` aus der Python-Standardbibliothek (ab Python 3.9).
Keine zusätzliche Dependency.

## Scheduler-Logik

### App-Start (`app.py`)

1. `report_send_time` aus `SystemSettings` lesen (Fallback: `"07:00"`)
2. Uhrzeit von `Europe/Berlin` nach UTC umrechnen
3. SLA-Job mit berechneter UTC-Zeit als Cron-Trigger schedulen

### Täglicher Zeitzonen-Hilfsjob (00:05 UTC)

Berechnet die UTC-Uhrzeit des SLA-Jobs anhand der gespeicherten lokalen Zeit
neu und rescheduled den Job. Dadurch bleibt die Uhrzeit auch über
Sommer-/Winterzeit-Wechsel korrekt, ohne manuelles Eingreifen.

**Korrektheit bei Zeitumstellung:** `zoneinfo` berechnet den Offset zum
Zielzeitpunkt, nicht zum aktuellen Zeitpunkt. Um 00:05 UTC ist der Offset
für 08:00 Lokalzeit am selben Tag bereits korrekt bestimmt — die Umstellung
um 03:00 Lokalzeit ändert daran nichts.

### Guard-Check in `process_sla_escalations()`

Ganz am Anfang, vor jeder Logik:

```python
def process_sla_escalations(app):
    today = datetime.now(ZoneInfo("Europe/Berlin")).date()
    weekday = today.isoweekday()  # 1=Mo, 7=So

    allowed_days = _get_allowed_weekdays()  # aus SystemSettings
    if weekday not in allowed_days:
        return  # Kein Versandtag

    state = SystemSettings.get_setting("report_federal_state")
    if state and today in holidays.Germany(state=state, years=today.year):
        return  # Gesetzlicher Feiertag

    if CustomHoliday.query.filter_by(date=today).first():
        return  # Betriebsferien o.ä.

    # ... normale Eskalationslogik (Kommentare, Notifications, E-Mails)
```

### Rescheduling beim Speichern (Admin-Route)

```python
scheduler.reschedule_job(
    "sla_escalation",
    trigger="cron",
    hour=utc_hour,
    minute=utc_minute,
)
```

## Admin-UI

Neuer Abschnitt **"Berichtsversand"** auf der Settings-Seite (`/admin/settings`),
unterhalb der SMTP-Konfiguration.

### Elemente

1. **Versandzeit** — `<input type="time">`, Label: "Versandzeit (Europe/Berlin)",
   Default: "07:00"

2. **Wochentage** — 7 Checkboxen inline (Mo–So), Default: Mo–Fr angehakt

3. **Bundesland** — Dropdown mit 16 Bundesländern + "— Kein Feiertagsfilter —".
   Bei Auswahl: Vorschau der nächsten 5 Feiertage (informativ, readonly)

4. **Zusätzliche freie Tage** — Tabelle mit Datum, Label, Löschen-Button.
   Hinzufügen-Formular mit Von-/Bis-Datepicker und Label-Feld (Bereich wird als
   einzelne Tage mit demselben Label gespeichert)

### Speicher-Logik

- Uhrzeit, Wochentage, Bundesland: gemeinsamer "Speichern"-Button
- Zusätzliche freie Tage: einzeln hinzufügen/löschen (CRUD)

## Bundesland-Mapping

Statisches Python-Dict, ans Template durchgereicht:

| Kürzel | Bundesland |
|--------|------------|
| BW | Baden-Württemberg |
| BY | Bayern |
| BE | Berlin |
| BB | Brandenburg |
| HB | Bremen |
| HH | Hamburg |
| HE | Hessen |
| MV | Mecklenburg-Vorpommern |
| NI | Niedersachsen |
| NW | Nordrhein-Westfalen |
| RP | Rheinland-Pfalz |
| SL | Saarland |
| SN | Sachsen |
| ST | Sachsen-Anhalt |
| SH | Schleswig-Holstein |
| TH | Thüringen |

## Nicht im Scope

- Konfiguration anderer Scheduler-Jobs (Recurring Tickets, Reminders)
- SLA-Grace-Period an Arbeitstagen berechnen
- Zeitzone konfigurierbar machen (fest `Europe/Berlin`)
- Länder außer Deutschland (Österreich, Schweiz)
