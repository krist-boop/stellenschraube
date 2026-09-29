# stellenschraube – Überblick für KI-Assistenten

Zwei Teile in diesem Repo:

- **Landingpage** (`index.html`, `employer/…`): statische Seiten, ausgeliefert über GitHub Pages.
  Reines HTML/CSS, kein Build-Schritt.
- **Vorschau-Generator** (`generator/`): Python/Flask-App, die aus einer Firmen-Website oder einem Inserat
  ein Bewerbungsformular im Design des Betriebs baut, plus interne Angebotsübersicht.
  **Alles Wichtige dazu steht in [`generator/AGENTS.md`](generator/AGENTS.md)**: Start, Tests, Aufbau, Regeln.

`_config.yml` schliesst `generator/` von GitHub Pages aus, damit der Code nicht öffentlich ausgeliefert wird.
