"""
Kontextsensitive Hilfetexte für das TicketSystem.

Struktur je Seite:
  'title'  – Seitenüberschrift im Hilfe-Panel
  'intro'  – Kurze Erklärung (1-2 Sätze) für alle Rollen
  'sections' – Liste von {'heading': str, 'text': str, 'roles': list|None}
               roles=None → für alle Rollen sichtbar
  'fields' – Dict {field_key: {'title': str, 'text': str}} für Popover-Icons

Rollen: 'admin', 'management', 'worker', 'viewer', 'hr'
"""

HELP = {

    # ------------------------------------------------------------------ #
    # Dashboard / Alle Tickets                                             #
    # ------------------------------------------------------------------ #
    'index': {
        'title': 'Alle Tickets – Übersicht',
        'intro': 'Hier sehen Sie alle offenen Aufgaben Ihres Betriebs auf einen Blick.',
        'sections': [
            {
                'heading': 'Statuskarten oben',
                'text': (
                    'Die drei Karten zeigen die Gesamtanzahl der Tickets je Status: '
                    '<strong>Offen</strong> (rot) – noch nicht begonnen, '
                    '<strong>In Bearbeitung</strong> (gelb) – wird gerade bearbeitet, '
                    '<strong>Wartet</strong> (grau) – bewusst pausiert, z.&nbsp;B. auf Lieferung oder Rückruf.'
                ),
                'roles': None,
            },
            {
                'heading': 'Filter und Suche',
                'text': (
                    'Mit dem Statusfilter schränken Sie die Ansicht auf einen Statustyp ein. '
                    'Die Schaltfläche <em>Mir zugewiesen</em> zeigt nur Ihre eigenen Tickets. '
                    '<em>Nicht zugewiesen</em> listet Tickets ohne Verantwortlichen auf – '
                    'ideal um offene Aufgaben zu verteilen. '
                    'Direktsprung: Geben Sie <code>#42</code> in die Suche ein, um Ticket Nr.&nbsp;42 direkt zu öffnen.'
                ),
                'roles': None,
            },
            {
                'heading': 'Meine Tickets (rechte Spalte)',
                'text': (
                    'Die rechte Spalte zeigt immer Ihre persönlich zugewiesenen Tickets, '
                    'unabhängig vom gewählten Filter. So behalten Sie den Überblick '
                    'über Ihre eigenen Aufgaben.'
                ),
                'roles': None,
            },
            {
                'heading': 'Automatische Aktualisierung',
                'text': (
                    'Das Dashboard prüft alle 10&nbsp;Sekunden ob neue Tickets vorliegen. '
                    'Erscheint der Hinweis „Neue Tickets verfügbar", klicken Sie darauf '
                    'um die Seite zu aktualisieren.'
                ),
                'roles': None,
            },
        ],
        'fields': {},
    },

    # ------------------------------------------------------------------ #
    # Meine Aufgaben / Queue                                               #
    # ------------------------------------------------------------------ #
    'my_queue': {
        'title': 'Meine Aufgaben',
        'intro': 'Ihre persönliche Aufgabenliste, nach Dringlichkeit sortiert.',
        'sections': [
            {
                'heading': 'Spalte: Sofort handeln (rot)',
                'text': (
                    'Enthält Tickets, die <strong>bereits überfällig</strong> sind '
                    'oder <strong>heute fällig</strong> werden und hohe Priorität haben. '
                    'Diese Aufgaben benötigen sofortige Aufmerksamkeit.'
                ),
                'roles': None,
            },
            {
                'heading': 'Spalte: Heute erledigen (blau)',
                'text': (
                    'Tickets die heute fällig werden, aber keine hohe Priorität haben. '
                    'Sollten noch heute abgeschlossen oder auf einen neuen Termin gesetzt werden.'
                ),
                'roles': None,
            },
            {
                'heading': 'Spalte: Woche &amp; Zukunft (grau)',
                'text': (
                    'Alle weiteren Tickets – fällig in den nächsten Tagen oder ohne Fälligkeit. '
                    'Mit dem Horizont-Filter oben rechts können Sie den Zeitraum anpassen '
                    '(7, 14 oder 30 Tage, oder alle Tickets).'
                ),
                'roles': None,
            },
            {
                'heading': 'Hinweis',
                'text': (
                    'Tickets mit Status <em>Wartet</em> erscheinen hier ebenfalls, '
                    'damit Sie nichts übersehen. Den Status können Sie direkt im Ticket ändern.'
                ),
                'roles': None,
            },
        ],
        'fields': {},
    },

    # ------------------------------------------------------------------ #
    # Projekte / Baustellen                                                #
    # ------------------------------------------------------------------ #
    'projects': {
        'title': 'Projekte & Baustellen',
        'intro': 'Tickets gruppiert nach Auftragsnummer – ideal für die Projektübersicht.',
        'sections': [
            {
                'heading': 'Was ist eine Auftragsnummer?',
                'text': (
                    'Die Auftragsnummer (Kunden-/Auftragsnummer) wird beim Erstellen eines Tickets '
                    'im Feld <em>Kunden- / Auftragsnummer</em> eingetragen. '
                    'Alle Tickets mit derselben Nummer erscheinen als ein Projekt. '
                    'So lassen sich mehrere Einzelaufgaben zu einer Baustelle bündeln.'
                ),
                'roles': None,
            },
            {
                'heading': 'Fortschrittsbalken',
                'text': (
                    'Der Fortschritt berechnet sich aus dem Anteil erledigter Tickets '
                    'plus dem Abschlussgrad der Checklisten-Einträge innerhalb des Projekts.'
                ),
                'roles': None,
            },
            {
                'heading': 'Aktiv vs. Abgeschlossen',
                'text': (
                    'Ein Projekt gilt als <em>Aktiv</em>, solange mindestens ein Ticket '
                    'den Status Offen, In Bearbeitung oder Wartet hat. '
                    'Sind alle Tickets erledigt, wechselt das Projekt automatisch auf <em>Abgeschlossen</em>.'
                ),
                'roles': None,
            },
        ],
        'fields': {},
    },

    # ------------------------------------------------------------------ #
    # Arbeitsauslastung (Admin / Management)                               #
    # ------------------------------------------------------------------ #
    'workload': {
        'title': 'Arbeitsauslastung',
        'intro': 'Zeigt offene Tickets je Mitarbeiter – nur für Admin und Management sichtbar.',
        'sections': [
            {
                'heading': 'Handlungsbedarf (roter Bereich)',
                'text': (
                    'Erscheint, wenn ein <strong>abwesender Mitarbeiter</strong> Tickets hat, '
                    'die sofortige Aufmerksamkeit erfordern. '
                    'Ein Ticket gilt als <em>kritisch</em>, wenn es '
                    '<strong>hohe Priorität</strong> hat, <strong>bereits überfällig</strong> ist '
                    'oder die <strong>Fälligkeit in der laufenden Kalenderwoche</strong> liegt '
                    '(Mo–Fr). So bleibt genug Reaktionszeit, bevor beim Kunden etwas schief läuft.'
                ),
                'roles': ['admin', 'management'],
            },
            {
                'heading': 'Nicht-kritische Tickets (eingeklappt)',
                'text': (
                    'Tickets des abwesenden Mitarbeiters ohne dringende Frist werden '
                    'eingeklappt angezeigt mit dem Hinweis „warten auf Rückkehr". '
                    'Diese müssen <em>nicht</em> sofort umverteilt werden.'
                ),
                'roles': ['admin', 'management'],
            },
            {
                'heading': 'Einzelzuweisung',
                'text': (
                    'Über den <em>Zuweisen</em>-Button bei jedem Ticket öffnet sich ein Fenster, '
                    'in dem Sie einen Ziel-Mitarbeiter auswählen. '
                    'Nur das einzelne Ticket wird übertragen – kein Massenumzug. '
                    'Die Zuweisung wird im Ticket-Protokoll dokumentiert.'
                ),
                'roles': ['admin', 'management'],
            },
            {
                'heading': 'Auslastung anwesender Mitarbeiter',
                'text': (
                    'Die untere Sektion zeigt alle aktiven Mitarbeiter mit offenen Tickets, '
                    'sortiert nach Anzahl. Auch hier können Sie einzelne Tickets umverteilen, '
                    'z.&nbsp;B. bei Überlastung.'
                ),
                'roles': ['admin', 'management'],
            },
        ],
        'fields': {},
    },

    # ------------------------------------------------------------------ #
    # Neues Ticket erstellen                                               #
    # ------------------------------------------------------------------ #
    'ticket_new': {
        'title': 'Neues Ticket erstellen',
        'intro': 'Melden Sie hier einen neuen Vorgang, eine Aufgabe oder ein Problem.',
        'sections': [
            {
                'heading': 'Pflichtfelder',
                'text': (
                    'Nur <em>Titel</em> und <em>Dringlichkeit</em> sind Pflichtfelder. '
                    'Je mehr Informationen Sie angeben, desto besser kann der Vorgang '
                    'bearbeitet werden.'
                ),
                'roles': None,
            },
            {
                'heading': 'Erweiterte Optionen',
                'text': (
                    'Über die Schaltfläche <em>Erweiterte Ticket-Optionen</em> öffnen sich '
                    'weitere Felder: Auftragsnummer, Fälligkeit, Zuweisung, '
                    'Checklisten-Vorlage und Serienticket.'
                ),
                'roles': None,
            },
        ],
        'fields': {
            'priority': {
                'title': 'Dringlichkeit',
                'text': (
                    '<strong>Hoch:</strong> Sofortiger Handlungsbedarf – Kundenauftrag gefährdet oder '
                    'Sicherheitsrisiko.<br>'
                    '<strong>Mittel:</strong> Normaler Betriebsvorgang, sollte zeitnah erledigt werden.<br>'
                    '<strong>Niedrig:</strong> Kann warten, kein sofortiger Schaden.'
                ),
            },
            'order_reference': {
                'title': 'Kunden- / Auftragsnummer',
                'text': (
                    'Tragen Sie hier die Auftragsnummer oder Projektkennzeichnung ein '
                    '(z.&nbsp;B. <code>A-2024-123</code>). '
                    'Alle Tickets mit gleicher Nummer werden in der Projektansicht '
                    'zusammengefasst.'
                ),
            },
            'is_confidential': {
                'title': 'Vertraulich',
                'text': (
                    'Vertrauliche Tickets sind nur sichtbar für: '
                    'die zugewiesene Person, Admins, HR und Management. '
                    'Nutzen Sie diese Option für sensible Personalangelegenheiten '
                    'oder interne Vorgänge.'
                ),
            },
            'due_date': {
                'title': 'Fälligkeitsdatum',
                'text': (
                    'Das Datum bis wann der Vorgang erledigt sein muss. '
                    'Überfällige Tickets werden rot hervorgehoben. '
                    'In der Auslastungsansicht gilt: Fälligkeit in der laufenden '
                    'Woche = Handlungsbedarf.'
                ),
            },
            'recurrence_rule': {
                'title': 'Serienticket',
                'text': (
                    'Wählen Sie ein Intervall, damit das Ticket automatisch '
                    'neu erstellt wird, sobald es erledigt wurde. '
                    'Geeignet für wiederkehrende Wartungsaufgaben oder Prüfungen.'
                ),
            },
            'assigned_to_id': {
                'title': 'Zuweisung',
                'text': (
                    'Weisen Sie das Ticket direkt einem Mitarbeiter oder Team zu. '
                    'Nicht zugewiesene Tickets erscheinen im Dashboard unter '
                    '<em>Nicht zugewiesen</em> und sollten zeitnah verteilt werden.'
                ),
            },
            'template_id': {
                'title': 'Checklisten-Vorlage',
                'text': (
                    'Fügt dem Ticket automatisch eine vordefinierte Checkliste hinzu. '
                    'Vorlagen werden vom Admin unter <em>Checklisten-Vorlagen</em> verwaltet. '
                    'Ideal für wiederkehrende Abläufe mit festen Arbeitsschritten.'
                ),
            },
        },
    },

    # ------------------------------------------------------------------ #
    # Ticket-Detail                                                        #
    # ------------------------------------------------------------------ #
    'ticket_detail': {
        'title': 'Ticket-Detailansicht',
        'intro': 'Alle Informationen, Kommentare und Aufgaben zu einem Vorgang.',
        'sections': [
            {
                'heading': 'Statuswechsel',
                'text': (
                    'Den Status ändern Sie über das Dropdown oben im Ticket. '
                    'Ablauf: <strong>Offen → In Bearbeitung → Erledigt</strong>. '
                    '<em>Wartet</em> nutzen Sie, wenn der Vorgang auf externe Informationen '
                    'oder Materialien wartet. Jeder Statuswechsel wird automatisch '
                    'im Protokoll festgehalten.'
                ),
                'roles': None,
            },
            {
                'heading': 'Kommentare und Protokoll',
                'text': (
                    'Kommentare mit grauem Hintergrund sind <em>Systemereignisse</em> '
                    '(automatisch erzeugt bei Statuswechsel, Zuweisung usw.). '
                    'Weiß hinterlegte Einträge sind manuelle Kommentare von Mitarbeitern. '
                    'Das Protokoll kann nicht gelöscht werden.'
                ),
                'roles': None,
            },
            {
                'heading': 'Checkliste',
                'text': (
                    'Teilaufgaben innerhalb eines Tickets. Einzelne Punkte können '
                    'an spezifische Mitarbeiter delegiert werden. '
                    'Abhängigkeiten zwischen Punkten sind möglich – '
                    'ein Punkt mit Abhängigkeit kann erst abgehakt werden, '
                    'wenn der vorherige erledigt ist.'
                ),
                'roles': None,
            },
            {
                'heading': 'Freigabe-Workflow',
                'text': (
                    'Bestimmte Tickets können zur Freigabe durch die Geschäftsführung '
                    'eingereicht werden. Während die Freigabe aussteht, ist das Ticket '
                    'gesperrt. Bei Ablehnung muss ein Ablehnungsgrund angegeben werden, '
                    'und das Ticket wird wieder geöffnet.'
                ),
                'roles': None,
            },
        ],
        'fields': {},
    },

    # ------------------------------------------------------------------ #
    # Archiv                                                               #
    # ------------------------------------------------------------------ #
    'archive': {
        'title': 'Archiv',
        'intro': 'Alle erledigten Tickets – zur Nachverfolgung und Dokumentation.',
        'sections': [
            {
                'heading': 'Suche und Filter',
                'text': (
                    'Sie können nach Stichwörtern im Titel oder nach dem Ersteller filtern. '
                    'Mit den Datumsfeldern grenzen Sie den Zeitraum ein, '
                    'in dem die Tickets erstellt wurden.'
                ),
                'roles': None,
            },
            {
                'heading': 'Tickets reaktivieren',
                'text': (
                    'Öffnen Sie ein Ticket und setzen Sie den Status zurück auf '
                    '<em>Offen</em> oder <em>In Bearbeitung</em>, '
                    'um es wieder in die aktive Ansicht zu bringen.'
                ),
                'roles': None,
            },
        ],
        'fields': {},
    },

    # ------------------------------------------------------------------ #
    # Freigaben                                                            #
    # ------------------------------------------------------------------ #
    'approvals': {
        'title': 'Freigaben',
        'intro': 'Tickets die auf Ihre Genehmigung warten.',
        'sections': [
            {
                'heading': 'Wann ist eine Freigabe nötig?',
                'text': (
                    'Ein Mitarbeiter kann bei jedem Ticket eine Freigabe anfordern, '
                    'z.&nbsp;B. für außerplanmäßige Ausgaben oder sensitive Arbeiten. '
                    'Das Ticket wird dann gesperrt, bis Sie entscheiden.'
                ),
                'roles': ['admin', 'management'],
            },
            {
                'heading': 'Freigabe erteilen oder ablehnen',
                'text': (
                    'Mit <em>Freigabe erteilen</em> wird das Ticket entsperrt und '
                    'der Mitarbeiter kann weiterarbeiten. '
                    'Bei <em>Ablehnen</em> müssen Sie einen Grund angeben – '
                    'dieser erscheint im Ticket-Protokoll und der Ersteller wird benachrichtigt.'
                ),
                'roles': ['admin', 'management'],
            },
        ],
        'fields': {},
    },

    # ------------------------------------------------------------------ #
    # Mitarbeiterverwaltung (Admin)                                        #
    # ------------------------------------------------------------------ #
    'workers': {
        'title': 'Mitarbeiterverwaltung',
        'intro': 'Verwalten Sie Mitarbeiter, Rollen und Abwesenheiten.',
        'sections': [
            {
                'heading': 'Rollen im Überblick',
                'text': (
                    '<strong>Admin:</strong> Vollzugriff – Mitarbeiter verwalten, Tickets löschen, '
                    'Freigaben erteilen, Einstellungen ändern.<br>'
                    '<strong>Management:</strong> Kann die Auslastungsansicht sehen und '
                    'Freigaben erteilen – kein Zugriff auf Admin-Einstellungen.<br>'
                    '<strong>Worker:</strong> Normaler Mitarbeiter – Tickets erstellen, '
                    'bearbeiten, kommentieren.<br>'
                    '<strong>Viewer:</strong> Nur lesen – kann Tickets sehen, aber nicht ändern.<br>'
                    '<strong>HR:</strong> Wie Worker, sieht zusätzlich vertrauliche Tickets.'
                ),
                'roles': ['admin'],
            },
            {
                'heading': 'PIN zurücksetzen',
                'text': (
                    'Klicken Sie auf <em>PIN zurücksetzen</em>, um einen temporären PIN '
                    'für den Mitarbeiter zu vergeben. '
                    'Der Mitarbeiter wird beim nächsten Login aufgefordert, '
                    'einen neuen persönlichen PIN zu wählen.'
                ),
                'roles': ['admin'],
            },
            {
                'heading': 'Abwesenheit & Vertretung',
                'text': (
                    'Setzen Sie einen Mitarbeiter auf <em>Abwesend</em>, '
                    'wenn er krank oder im Urlaub ist. '
                    'Neue Tickets, die ihm zugewiesen werden, '
                    'können automatisch an eine Vertretung weitergeleitet werden. '
                    'In der Auslastungsansicht erscheinen seine offenen Tickets '
                    'dann im roten Handlungsbedarf-Bereich.'
                ),
                'roles': ['admin'],
            },
            {
                'heading': 'Mitarbeiter deaktivieren',
                'text': (
                    'Deaktivierte Mitarbeiter können sich nicht mehr anmelden, '
                    'bleiben aber als Ersteller oder Kommentator in der Historie erhalten. '
                    'Offene Tickets bleiben bestehen und müssen manuell umverteilt werden.'
                ),
                'roles': ['admin'],
            },
        ],
        'fields': {},
    },

    # ------------------------------------------------------------------ #
    # Checklisten-Vorlagen (Admin)                                         #
    # ------------------------------------------------------------------ #
    'admin_templates': {
        'title': 'Checklisten-Vorlagen',
        'intro': 'Vordefinierte Aufgabenlisten für wiederkehrende Vorgänge.',
        'sections': [
            {
                'heading': 'Wozu Vorlagen?',
                'text': (
                    'Mit einer Vorlage fügen Sie einem neuen Ticket automatisch '
                    'eine Checkliste mit vordefinierten Schritten hinzu. '
                    'So stellen Sie sicher, dass bei Standardvorgängen '
                    'kein Schritt vergessen wird.'
                ),
                'roles': ['admin'],
            },
            {
                'heading': 'Vorlage anwenden',
                'text': (
                    'Beim Erstellen eines Tickets wählen Sie im Feld '
                    '<em>Checklisten-Vorlage</em> die gewünschte Vorlage aus. '
                    'Sie kann auch nachträglich im Ticket-Detail hinzugefügt werden.'
                ),
                'roles': ['admin'],
            },
        ],
        'fields': {},
    },
}
