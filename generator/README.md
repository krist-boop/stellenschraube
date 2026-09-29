# stellenschraube – Vorschau-Generator

Ein Betrieb gibt seine Website oder den Link zum Stelleninserat ein. Der Generator erstellt daraus ein
Bewerbungsformular in Farbe und Logo des Betriebs, erreichbar unter `/employer/<firma>-<id>`.

## Ablauf
1. **Eingabe** (`/vorschau`): Website oder Inserat-Link, optional Stelle und E-Mail
2. **Auslesen** (`extract.py`): Firma, Stelle, Ort, bei jobs.ch & Co. aus den strukturierten Inseratsdaten
3. **Design** (`brand.py`): Hauptfarbe und Logo von der Firmenwebsite
4. **Fragen** (`questions.py`): Abschluss → Erfahrung → Können → wichtigste Anforderung aus dem Inserat.
   Mit `ANTHROPIC_API_KEY` von Claude, sonst aus Branchenvorlagen. Jede Frage wird geprüft
   (keine Fragen zu Alter, Herkunft, Familie, Gesundheit, Lohn).
5. **Kundenseite** (`templates/employer.html`): ohne Hinweis auf stellenschraube
6. **Bewerbungen** landen in SQLite, Übersicht unter `/intern?key=INTERN_TOKEN`

Fehlt die Stelle oder ist die URL nicht erreichbar, fragt die Maske nach, statt etwas zu erfinden.

## Lokal starten
```bash
cd generator
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python app.py          # http://localhost:5050
./venv/bin/python -m pytest -q    # Tests, laufen offline
```

## Auf dem VPS (Ubuntu/Debian mit nginx)
```bash
sudo git clone https://github.com/krist-boop/stellenschraube /opt/stellenschraube
cd /opt/stellenschraube/generator
sudo python3 -m venv venv && sudo ./venv/bin/pip install -r requirements.txt
sudo cp .env.example .env && sudo nano .env        # INTERN_TOKEN setzen
sudo mkdir -p /opt/stellenschraube/data && sudo chown www-data /opt/stellenschraube/data
sudo cp deploy/stellenschraube.service /etc/systemd/system/
sudo systemctl enable --now stellenschraube
sudo cp deploy/nginx.conf /etc/nginx/sites-available/stellenschraube
sudo ln -s /etc/nginx/sites-available/stellenschraube /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d stellenschraube.ch -d www.stellenschraube.ch
```
Update: `cd /opt/stellenschraube && sudo git pull && sudo systemctl restart stellenschraube`

## Noch offen
- Benachrichtigung an den Betrieb bei neuer Bewerbung (Mail/SMS) – Stellen im Code mit `TODO` markiert
- Vorschau-Link per Mail an den Anfragenden
- Hero-Formular der Landingpage auf `/vorschau` verlinken
