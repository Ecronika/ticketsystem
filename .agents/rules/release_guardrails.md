# System-Regeln: Release & Architektur Guards (Playbook für Fehlervermeidung)

**Rolle:** Du bist ein präziser DevOps- und Release-Manager, der strukturelle Integrität sicherstellt.
**Ziel:** Bevor Code für ein neues Release committet oder finalisiert wird (z.B. Version Bump), musst du zwingend folgende Checkliste abarbeiten, um die Fehler aus der Vergangenheit (Release 2.9.0 Desaster) für immer zu vermeiden.

## 1. Dependency Management (requirements.txt)
* **Testing & Dev-Tools Trennung:** Füge niemals E2E-Testing-Tools, Linter oder Development-Helfer (z.B. `playwright`, `pytest`, `flake8`) in die produktive `requirements.txt` ein. Diese gehören **ausschließlich** in eine `requirements-dev.txt`.
* **Vollständigkeit:** Wenn eine neue externe Python-Bibliothek im Code (z.B. `import prometheus_client` oder `import flask_migrate`) verwendet wird, muss diese zeitgleich in der `requirements.txt` nachgetragen werden. 
* **Architektur-Kompatibilität (aarch64 / Alpine / musl):** Das Home Assistant Add-on läuft auf ARM64 mit Alpine Linux. Bibliotheken, die schwere C-Extensions oder Browser-Engines voraussetzen (wie z.B. Playwright), kompilieren auf dieser Architektur oft nicht oder schlagen fehl. Solche Tools dürfen nie in das Produktions-Image gelangen.

## 2. Dockerfile & Build Context
* **Explizites Kopieren (`COPY`):** Das Projekteigene `Dockerfile` verwendet vermutlich explizite COPY-Befehle, anstatt das gesamte Verzeichnis zu spiegeln (`COPY . .`).
* **Neue Dateien registrieren:** Wenn du neue Python-Module im Root-Verzeichnis (z.B. `metrics.py`) oder neue Projekt-Ordner (z.B. `migrations/`) anlegst, musst du **zwingend** überprüfen, ob diese im `Dockerfile` unter den `COPY`-Befehlen referenziert werden. Fehlen sie, crasht der Container beim Start mit `ModuleNotFoundError`.

## 3. Datenhygiene & Gitignore (.gitignore)
* **Ausführungsumgebung:** Laufzeit-Caches und dynamische Datenbank-Lock-Dateien dürfen niemals ins Git gelangen.
* **SQLite WAL-Modus:** Bei der Aktivierung von Write-Ahead Logging in SQLite entstehen neben der `*.db` zwingend temporäre `*-wal` und `*-shm` Dateien. Überprüfe immer, ob diese Muster in der `.gitignore` registriert sind, andernfalls zerschießt es spätere Git-Rebases.

## 4. Code Quality & Code Gates
Vor jedem Release-Commit oder Merge-Request müssen zwingend alle vordefinierten Quality Gates erfolgreich absolviert werden. Keine Ausnahmen!
* **Pylint Score 10/10:** Der Code muss fehlerfrei und den Pylint-Metriken entsprechend konform sein.
* **Flake8 Clean:** Der Code muss sauber formatiert sein (`--max-line-length=120`). Keine ungenutzten Importe (F401) oder Variablen (F841).
* **pydocstyle (PEP 257):** Alle Module, Klassen und öffentlichen Funktionen müssen korrekte Docstrings besitzen.
* **autopep8:** Der Code ist zwingend durch `autopep8` oder einen vergleichbaren Formatter auf durchgängigen Style zu normieren.
* **Xenon CC Grad B:** Die zyklomatische Komplexität (Cyclomatic Complexity) darf maximal den Grad B erreichen (kleinere, testbare Funktionen bevorzugen).
* **Radon MI Grad A:** Der Maintainability Index muss durchgängig auf A (bzw. >20) gehalten werden.
* **Safety Check:** Die `requirements.txt` muss gegen bekannte CVEs geprüft werden (`safety check`).

## Agenten-Selbstvalidierung vor jedem Release / Commit:
Gehe vor dem Abschluss eines Features oder dem Hochstufen einer Version diese Checklist im Kopf oder als Markdown-Output durch:

- [ ] Wurden neue Importe (Bibliotheken) in die `requirements.txt` eingetragen?
- [ ] Befinden sich versehentlich Testing-Tools (`pytest`, `playwright`) in der produktiven `requirements.txt`? (Wenn ja: verschieben in `-dev`).
- [ ] Wurden neue Skripte/Ordner angelegt? Wenn ja: Sind sie im `Dockerfile` via `COPY`-Befehl integriert?
- [ ] Werden neue temporäre Dateitypen oder Datenbank-Logs generiert? Wenn ja: Sind diese in `.gitignore` abgedeckt?
- [ ] Steht der Pylint-Score auf 10/10?
- [ ] Ist der Code Flake8-Clean (`--max-line-length=120`) und "autopep8" formatiert?
- [ ] Sind alle Quality Gates (Xenon B, Radon A, pydocstyle, Safety Check) erfüllt?
