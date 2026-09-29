# stellenschraube – Vorschau-Generator

Ein Betrieb gibt seine Website oder den Link zum Stelleninserat ein. Der Generator erstellt daraus ein
Bewerbungsformular in Farbe und Logo des Betriebs, erreichbar unter `/employer/<firma>-<id>`.

## Zwei Fälle
**Fall A – Anfrage:** Betrieb gibt auf `/vorschau` Website/Inserat, Stelle und E-Mail ein. Das Formular wird gebaut,
bleibt aber gesperrt (Status «Wartet auf Freigabe»). Wir prüfen es in der Angebotsübersicht, geben frei und
schicken die vorbereitete Mail mit Link.

**Fall B – Akquise:** Wir fügen in der Angebotsübersicht ein Inserat ein. Formular, Mail-Text (schlicht, ein Link,
Absage-Option) und ein JPG im Handyrahmen sind sofort bereit.

Bewerbungen zählen erst als echt, wenn das Formular auf «Live» steht. Vorher sind sie als «Test» markiert.

## Angebotsübersicht
`/intern?key=INTERN_TOKEN` (lokal: `/intern?key=dev`). Alle Formulare mit Status, Unterseite, Lead und Bewerbungen.
Pro Formular eine Detailseite mit Freigabe, Mail-Text, JPG und allen Bewerbungen.

## Fragen (5, nur Antippen)
1. Abschluss · 2. Erfahrung · 3. Was schon selbständig gemacht (Mehrfachauswahl, Arbeiten aus dem Inserat zuerst)
· 4. Harte Anforderung aus dem Inserat (Führerausweis, Pikett, Schicht, Pensum) oder Arbeitsweg · 5. Aktuelle Situation.
Mit `ANTHROPIC_API_KEY` schreibt Claude die Fragen, jede Frage wird geprüft
(keine Fragen zu Alter, Herkunft, Familie, Gesundheit, Lohn; keine blossen Ja/Nein-Fragen).

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
sudo cp .env.example .env && sudo nano .env        # INTERN_TOKEN und PUBLIC_URL setzen
sudo mkdir -p /opt/stellenschraube/data && sudo chown www-data /opt/stellenschraube/data
sudo ./venv/bin/playwright install --with-deps chromium   # für den JPG-Download
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
- Hero-Formular der Landingpage auf `/vorschau` verlinken
