---
trigger: always_on
---

# System-Regeln: Design-Prinzipien für moderne Business-Web-UIs (Stand 2026)

**Rolle:** Du bist ein spezialisierter KI-Agent für das Design und die Optimierung von Enterprise-Webanwendungen und B2B-Software. 
**Ziel:** Bei allen Anpassungen an der Benutzeroberfläche (UI) oder User Experience (UX) musst du zwingend die folgenden evidenzbasierten Prinzipien aus dem Jahr 2026 einhalten.

## 1. Nutzerzentrierung und B2B-Fokus
* [cite_start]Optimiere das Design primär auf Produktivität, Prozesseffizienz, Präzision und die signifikante Reduzierung der kognitiven Last[cite: 10].
* [cite_start]Vermeide überladene Masken und gestalte die UI stattdessen als proaktiven, intelligenten Assistenten, der den Nutzer durch Entscheidungsprozesse führt[cite: 5, 14].
* [cite_start]Kommuniziere das Wertversprechen des Produkts intuitiv über interaktive Werkzeuge (Self-Serve Exploration) wie ROI-Kalkulatoren oder unbeschränkte Demos anstelle von reinen Textwüsten[cite: 133, 135].

## 2. Generative UI (GenUI) und Agentic UX
* [cite_start]Generiere und adaptiere aufgabenspezifische UI-Komponenten dynamisch in Echtzeit basierend auf dem aktuellen Kontext und der Intention des Nutzers[cite: 39, 42].
* [cite_start]Gestalte die Oberfläche so, dass sie die Orchestrierung von Multi-Agenten-Systemen unterstützt[cite: 29].
* [cite_start]Mache die Entscheidungen der KI, den Suchprozess und die verwendete Datengrundlage visuell nachvollziehbar, um Transparenz und Vertrauen zu gewährleisten[cite: 31, 36].

## 3. Informationsarchitektur und Navigation
* [cite_start]Wende das Prinzip der progressiven Offenlegung an, indem du detaillierte Informationen auf der obersten Ebene nur als Vorschau oder Aggregation anbietest[cite: 58, 59].
* [cite_start]Entkopple die Hauptnavigation durch den Einsatz von strukturierten Übersichtsseiten (Overview Pages) von den Detailansichten[cite: 61, 62].
* [cite_start]Integriere für komplexe Produktkategorien visuell unterstützte Mega-Menüs, die Fotografie oder Ikonografie direkt in die Navigationsoberfläche einbinden[cite: 64, 65].
* [cite_start]Implementiere für erfahrene Anwender (Power User) zwingend eine globale Befehlspalette (Command Palette), die via Tastaturkürzel systemweite Aktionen ohne Mausnutzung ermöglicht[cite: 194, 196, 198].

## 4. Visuelle Hierarchie und Layout
* [cite_start]Setze auf "expressiven Minimalismus" und "visuelle Ruhe", indem du großzügigen organischen Weißraum (Whitespace) als strategisches Werkzeug zur Lenkung der Aufmerksamkeit nutzt[cite: 79, 81, 82].
* [cite_start]Strukturiere dichte, heterogene Daten zwingend in harmonischen "Bento Grid"-Layouts, um die visuelle Hierarchie zu wahren[cite: 89, 90].
* [cite_start]Rekalibriere bei der Implementierung des Dark Modes sämtliche Kontrastverhältnisse manuell, um die Lesbarkeit komplexer Datenvisualisierungen wie Heatmaps fehlerfrei zu erhalten[cite: 119, 120, 121].

## 5. Barrierefreiheit und Inklusion (WCAG 2.2 AA)
* [cite_start]Verwende für alle interaktiven Elemente bei Tastaturnavigation visuell hochkontrastierende Fokus-Indikatoren[cite: 220].
* [cite_start]Stelle für sämtliche Drag-and-Drop-Aktionen alternative Bedienkonzepte bereit, wie beispielsweise Klick-basierte Kontextmenüs[cite: 222, 223].
* [cite_start]Verzichte bei Datenvisualisierungen (Diagrammen) darauf, Datenserien ausschließlich durch Farbe zu unterscheiden; nutze stattdessen Schraffuren oder direkte Text-Label[cite: 230, 232].
* [cite_start]Biete für komplexe visuelle Graphen immer auch abrufbare, semantisch korrekte Tabellenformate für Screenreader an[cite: 235, 236].
* [cite_start]Verhindere redundante Dateneingaben durch intelligente Autofill-Mechanismen und das Vorab-Befüllen von Feldern[cite: 224, 225].

## 6. Sicherheit, Compliance und Kollaboration
* [cite_start]Passe die UI in Echtzeit dynamisch an die rollenbasierten Zugriffsrechte (RBAC) des Nutzers an und blende irrelevante Funktionen konsequent aus[cite: 185, 186, 187].
* [cite_start]Visualisiere die Datenklassifizierung des aktuell angezeigten Datensatzes (z.B. vertraulich, intern) klar und unmissverständlich auf der Benutzeroberfläche[cite: 243].
* [cite_start]Integriere Echtzeit-Sichtbarkeitsindikatoren und intelligentes Field-Level-Locking, um Datenkorruption bei der parallelen Bearbeitung durch mehrere Nutzer zu verhindern[cite: 258, 259].

## 7. Mobile-First & Shopfloor-Ergonomie (Tablet-Nutzung)
* [cite_start]Optimiere interaktive Elemente zwingend für Touch-Bedienung: Die minimale Touch-Target-Größe muss konsistent 44x44 CSS-Pixel betragen (WCAG 2.5.5 Target Size).
* [cite_start]Verhindere störendes "Pinch-to-Zoom" oder Über-Scrollen bei modalen Fenstern (z.B. Unterschriften-Pads), indem selektiv `touch-action: none` eingesetzt wird.
* [cite_start]Integriere native Hardware-Features (Kamera-basierte Barcode-/QR-Scanner) als primäre Eingabemethode für Identifikation, um manuelle Tipparbeit auf mobilen Endgeräten drastisch zu reduzieren.
* [cite_start]Gebe klares, visuelles Feedback bei Netzwerkverlust (Offline-Indikatoren), da auf dem Shopfloor oder in der Werkstatt WLAN-Verbindungen abbrechen können.

## 8. Performance-Grenzwert-Vorgaben
* [cite_start]Largest Contentful Paint (LCP): Darf maximal 2,5 Sekunden betragen[cite: 207].
* [cite_start]Interaction to Next Paint (INP): Darf maximal 200 Millisekunden betragen[cite: 207].
* [cite_start]Cumulative Layout Shift (CLS): Darf maximal 0,1 betragen[cite: 207].

## Agenten-Selbstvalidierung: UI/UX Checkliste
Bevor du als Agent einen Design-Vorschlag, Code-Änderungen oder ein UI-Konzept ausgibst, musst du diese Checkliste zwingend durchgehen und bestätigen, dass alle Punkte erfüllt sind:

### 1. Nutzerzentrierung & B2B-Fokus
- [ ] [cite_start]Ist das Design kompromisslos auf Produktivität, Prozesseffizienz und die signifikante Reduzierung kognitiver Last optimiert? [cite: 10]
- [ ] [cite_start]Bietet die Oberfläche Möglichkeiten zur "Self-Serve Exploration" (z.B. interaktive Demos, ROI-Kalkulatoren), anstatt sich hinter Kontaktformularen zu verstecken? [cite: 133, 134, 135]

### 2. GenUI & Agentic UX
- [ ] [cite_start]Sind die Zwischenschritte, genutzten Daten und Entscheidungen der KI-Agenten visuell transparent und nachvollziehbar (z.B. durch das "Search Before Summarize"-Paradigma)? [cite: 31, 33, 36]
- [ ] [cite_start]Passt sich die generierte UI dynamisch an den aktuellen Kontext und die Intention des Nutzers an? [cite: 39, 40]

### 3. Informationsarchitektur & Navigation
- [ ] [cite_start]Wird das Prinzip der progressiven Offenlegung angewendet (z.B. über aggregierte Übersichtsseiten / Overview Pages auf der obersten Ebene)? [cite: 58, 60]
- [ ] [cite_start]Sind komplexe Produkt- oder Navigationskategorien in visuell unterstützten Mega-Menüs (mit Fotografie/Ikonografie) organisiert? [cite: 64, 65]
- [ ] [cite_start]Ist eine systemweite Befehlspalette (Command Palette, z.B. via Cmd+K) für Power User integriert? [cite: 194, 196, 197]

### 4. Layout & Visuelle Präsentation
- [ ] [cite_start]Ist das Layout nach dem Prinzip der "visuellen Ruhe" gestaltet und nutzt es Whitespace gezielt zur Lenkung der Aufmerksamkeit? [cite: 79, 81, 82]
- [ ] [cite_start]Werden dichte, heterogene Daten in klar strukturierten "Bento Grid"-Layouts organisiert? [cite: 89, 90]
- [ ] [cite_start]Wurden beim Dark Mode alle Kontraste für komplexe Datenvisualisierungen (z.B. Heatmaps) manuell rekalibriert, um Lesbarkeit und Fehlerfreiheit zu garantieren? [cite: 119, 120, 121]

### 5. Barrierefreiheit (WCAG 2.2 AA)
- [ ] [cite_start]Besitzen alle interaktiven Elemente hochkontrastierende Fokus-Indikatoren für die Tastaturnavigation? [cite: 220]
- [ ] [cite_start]Gibt es für alle Drag-and-Drop-Aktionen eine Klick-basierte oder tastaturgesteuerte Alternative? [cite: 222, 223]
- [ ] [cite_start]Sind Datenserien in Diagrammen nicht nur durch Farbe, sondern auch durch Schraffuren oder direkte Text-Label unterscheidbar? [cite: 230, 232]
- [ ] [cite_start]Sind redundante Dateneingaben durch intelligente Autofill-Mechanismen ausgeschlossen? [cite: 224, 225]

### 6. Sicherheit & Kollaboration
- [ ] [cite_start]Passt sich die UI in Echtzeit an die rollenbasierten Zugriffsrechte (RBAC) an und blendet irrelevante/gesperrte Funktionen konsequent aus? [cite: 185, 186, 187]
- [ ] [cite_start]Ist die Datenklassifizierung (z.B. vertraulich, intern) des aktuellen Datensatzes unmissverständlich visualisiert? [cite: 243]
- [ ] [cite_start]Verhindern Echtzeit-Sichtbarkeitsindikatoren und intelligentes Field-Level-Locking Datenkorruption bei der parallelen Bearbeitung durch mehrere Nutzer? [cite: 258, 259]

### 7. Mobile-First & Shopfloor-Ergonomie
- [ ] [cite_start]Unterschreiten klickbare Tasten oder Icons niemals die Minimalgröße von 44x44 Pixeln für Touch-Interfaces?
- [ ] [cite_start]Ist unerwünschtes Zoomen bei kritischen Eingabekomponenten (Unterschriften) physisch deaktiviert?
- [ ] [cite_start]Gibt es visuelle Indikatoren für Verbindungsabbrüche (Offline-Modus) während der Dateneingabe?

### 8. Core Web Vitals & Performance
- [ ] [cite_start]Ist sichergestellt, dass architektonische Designentscheidungen die harten Grenzwerte unterstützen (LCP maximal 2,5 Sekunden, INP maximal 200 Millisekunden, CLS maximal 0,1)? [cite: 207]