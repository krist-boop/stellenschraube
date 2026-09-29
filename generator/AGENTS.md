# Anleitung für KI-Assistenten (und Menschen): stellenschraube-Generator

Diese Datei erklärt einem KI-Assistenten (Claude Code, Cursor, Copilot usw.), wie dieses Projekt
funktioniert, wie man es startet und testet und welche Regeln gelten. Lies sie ganz, bevor du etwas änderst.

## Worum es geht
stellenschraube findet Fachkräfte für Schweizer Handwerksbetriebe (5–30 Mitarbeitende) über
Instagram/Facebook-Werbung. Dieser Ordner enthält den **Vorschau-Generator**: Aus einer Firmen-Website
oder einem Stelleninserat wird automatisch ein kurzes Handy-Bewerbungsformular im Design des Betriebs
gebaut, erreichbar unter `/employer/<firma>-<6 Zeichen>`.

Die Landingpage (`../index.html`) ist statisch und liegt im Repo-Hauptordner. Dieser Generator liegt in
`generator/` und wird von GitHub Pages bewusst nicht ausgeliefert (`../_config.yml`).

## Die zwei Abläufe
**Fall A – Anfrage** (öffentlich, `/vorschau`)
1. Betrieb gibt Website oder Inserat-Link, optional Stelle, **E-Mail (Pflicht)**, optional Name/Telefon ein
2. Formular wird gebaut, Status `wartet`, die Seite ist **gesperrt** (404 für alle ausser uns)
3. Wir prüfen in der Angebotsübersicht und klicken «Freigeben» → Status `freigegeben`
4. Die Detailseite zeigt eine fertige Mail mit Link (öffnet das eigene Mailprogramm, kein Versanddienst)
5. Sagt der Betrieb zu: «Kunde · live schalten» → Status `live`

**Fall B – Akquise** (intern)
1. In der Angebotsübersicht ein Inserat einfügen → Status `akquise`, Seite sofort per Link erreichbar
2. Detailseite liefert Mail-Vorlage (schlicht, ein Link, Absage-Option) und ein JPG im Handyrahmen

**Bewerbungen** zählen nur als echt, wenn das Formular `live` ist. Alles davor wird mit `test: true`
gespeichert (der Betrieb klickt sich durch die Vorschau).

## Schnellstart (lokal)
```bash
cd generator
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env                  # ANTHROPIC_API_KEY optional, lokal kann alles leer bleiben
./venv/bin/python app.py              # startet auf http://localhost:5050
```
Danach im Browser:
- Öffentliche Eingabemaske: http://localhost:5050/vorschau
- Angebotsübersicht (intern): http://localhost:5050/intern?key=dev  (lokal ist der Schlüssel `dev`,
  auf dem Server gilt `INTERN_TOKEN` aus `.env`; einmal mit `?key=` aufrufen, danach merkt es sich ein Cookie)

## Testen
```bash
./venv/bin/python -m pytest -q        # 53 Tests, laufen offline in unter 2 Sekunden
```
Die Tests simulieren alle Webseiten (`fake_fetch` in `tests/test_pipeline.py`), es geht nichts ins Internet.
**Vor jedem Commit müssen alle Tests grün sein.** Neue Funktion = neuer Test.

Kompletter Ablauf im echten Browser mit Screenshots (braucht Internet und Chrome):
```bash
rm -f data.sqlite3                    # frische Datenbank, sonst greift der Duplikat-Schutz
./venv/bin/python app.py &            # Server im Hintergrund
./venv/bin/python testlauf/run.py     # spielt Fall A und B durch, Screenshots landen in testlauf/
```
Kein Chrome installiert? Einmalig `./venv/bin/playwright install chromium`.

## Aufbau
| Datei | Aufgabe |
|---|---|
| `app.py` | Startpunkt, ruft `stellenschraube.app.create_app()` |
| `stellenschraube/app.py` | Alle Routen, `build_form()` (ganzer Ablauf ohne Web), `mail_text()` |
| `stellenschraube/extract.py` | Firma, Stelle, Ort aus URL oder Text (JSON-LD `JobPosting`, Seitentitel, Regex), SSRF-Schutz in `fetch()` |
| `stellenschraube/brand.py` | Hauptfarbe und Logo der Firmenwebsite, lesbare Textfarbe (`on_color`) |
| `stellenschraube/questions.py` | Die 5 Fragen (Vorlagen pro Branche oder Claude) und `check_questions()` |
| `stellenschraube/store.py` | SQLite: Formulare mit Status/Lead, Bewerbungen, Duplikat-Suche |
| `stellenschraube/preview_image.py` | JPG der Kundenseite im Handyrahmen (Playwright) |
| `stellenschraube/templates/` | `index.html` (Maske), `employer.html` (Kundenseite), `intern*.html` (Übersicht), `404.html` |
| `tests/test_pipeline.py` | Alle Tests |
| `testlauf/run.py` | Browser-Durchlauf mit Screenshots |
| `deploy/` | systemd-Dienst und nginx-Konfiguration für den VPS |

## Routen
| Route | Wer | Zweck |
|---|---|---|
| `GET /vorschau` | öffentlich | Eingabemaske Fall A |
| `POST /api/preview` | öffentlich | baut Formular, Status `wartet` (Rate-Limit 20/Std.) |
| `GET /employer/<slug>` | öffentlich* | Kundenseite (*bei `wartet` nur intern) |
| `POST /api/apply/<slug>` | öffentlich* | Bewerbung speichern |
| `GET /intern` | intern | Angebotsübersicht |
| `POST /intern/neu` | intern | Akquise-Vorschlag (Fall B) |
| `GET /intern/<slug>` | intern | Detailseite mit Freigabe, Mail, Bewerbungen |
| `POST /intern/<slug>/status` | intern | `wartet` / `freigegeben` / `akquise` / `live` |
| `GET /intern/<slug>/vorschau.jpg` | intern | JPG herunterladen |

## Regeln, die nicht gebrochen werden dürfen
1. **Kundenseiten nennen stellenschraube nirgends.** Der Bewerber sieht nur den Betrieb. (Test prüft das.)
2. **Kundenseiten werden nicht indexiert**: `meta robots` und `X-Robots-Tag: noindex, nofollow`.
3. **Keine heiklen Fragen**: nie Alter, Herkunft, Nationalität, Bewilligung, Religion, Familie, Kinder,
   Gesundheit, Lohn. `check_questions()` erzwingt das, auch für Fragen von Claude.
4. **Fragen bleiben einfach**: 5 Fragen, nur Antippen, 4 abgestufte Antworten (Frage 3: Mehrfachauswahl,
   5 Optionen), keine blossen Ja/Nein-Fragen. Jede Antwort muss dem Betrieb vor dem Anruf etwas sagen.
5. **Nichts erfinden**: Fehlt die Stelle oder ist die URL nicht erreichbar, fragt die Maske nach
   (HTTP 422 mit `field`), statt eine Vorschau mit geratenen Angaben zu bauen.
6. **Sicherheit**: Jinja-Autoescape nicht ausschalten (kein `|safe` für Nutzereingaben); `fetch()` ruft nur
   öffentliche Adressen ab (SSRF-Schutz, auch bei Weiterleitungen).
7. **Sprache**: Schweizer Hochdeutsch, «ss» statt «ß», Du-Form auf Kundenseiten.
8. **Schreibstil der UI**: aus Sicht des Nutzers, konkrete Knopftexte («Freigeben», «Vorschau anfragen»),
   Fehlermeldungen sagen, was zu tun ist.

## Typische Aufgaben
- **Neue Branche**: in `questions.py` einen Eintrag in `BRANCHES` (Stichwörter) und `TASKS` (5 konkrete
  Arbeiten mit Stichwörtern) ergänzen, dann einen Fall in `JOBS` in den Tests.
- **Neue Anforderung für Frage 4**: Eintrag in `REQUIREMENTS` (Reihenfolge = Priorität).
- **Berufsbezeichnung wird nicht erkannt**: Wort in `JOB_WORDS` in `extract.py`, Fall in `REGRESSION` in den Tests.
- **Firma ohne AG/GmbH wird nicht erkannt**: Wort in `TRADE_RE` in `extract.py`.

## Konfiguration (`.env`)
| Variable | Bedeutung |
|---|---|
| `INTERN_TOKEN` | Schlüssel für `/intern` (lokal leer → `dev`). Auf dem Server unbedingt setzen. |
| `PUBLIC_URL` | Adresse in den Mail-Links, z.B. `https://stellenschraube.ch` |
| `ANTHROPIC_API_KEY` | Optional. Mit Schlüssel schreibt Claude die Fragen, sonst Branchenvorlagen |
| `CLAUDE_MODEL` | Optional, Standard `claude-sonnet-5-5` |
| `DB_PATH` | Speicherort der SQLite-Datenbank |
| `PREVIEWS_PER_HOUR` | Rate-Limit für `/api/preview` pro IP |
| `PLAYWRIGHT_CHANNEL` | `chrome` lokal, leer auf dem Server (dann Chromium von `playwright install`) |

## Noch offen (Stand 29.09.2026)
- Betrieb bei neuer Bewerbung benachrichtigen (Mail/SMS): im Code als `TODO` in `apply()` markiert
- Landingpage-Box «Kostenlose Vorschau» mit `/vorschau` verbinden
- Deployment auf den VPS: Anleitung in `README.md`
- Meta-Werbung: prüfen, ob die Kategorie «Beschäftigung» in der Schweiz Pflicht ist (schränkt Targeting ein)

## Arbeitsweise im Repo
- Änderungen auf einem eigenen Branch, dann Pull Request gegen `main`
- `data.sqlite3`, `.env`, `venv/` und erzeugte Bilder werden nicht eingecheckt (`.gitignore`)
