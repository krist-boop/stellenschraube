"""Testlauf: Fall A (Anfrage mit Freigabe) und Fall B (Akquise). Jeder Schritt als Screenshot in testlauf/.

Voraussetzung: Server läuft (python app.py) mit frischer Datenbank, sonst greift der Duplikat-Schutz.
Start:  ./venv/bin/python testlauf/run.py
Braucht Internet (liest frutiger.com und burkhalter.ch) und Chrome oder `playwright install chromium`.
"""
import json, os, re, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5050"
OUT = Path(__file__).parent
# Landingpage aus dem Repo (liegt eine Ebene über generator/)
LANDING = (Path(__file__).resolve().parents[2] / "index.html").as_uri()
log, n = [], 1

def shot(page, case, name, note, full=False):
    global n
    f = f"{n:02d}-{name}.png"
    page.screenshot(path=OUT / f, full_page=full)
    log.append({"n": n, "case": case, "file": f, "note": note})
    print(f"{n:02d} [{case}] {note}"); n += 1

def phone_walkthrough(ph, case, picks):
    ph.locator("#form").scroll_into_view_if_needed()
    for i, pick in enumerate(picks):
        step = ph.locator(f'.step[data-i="{i}"]')
        for p in (pick if isinstance(pick, list) else [pick]):
            step.locator(".opt").nth(p).click()
        ph.locator("#form").scroll_into_view_if_needed()
        q = step.locator("h2").inner_text()
        shot(ph, case, f"frage-{i+1}", f"Frage {i+1}: {q}")
        ph.click("#next")
    ph.fill("#name", "Luca Meier"); ph.fill("#tel", "079 123 45 67")
    ph.locator("#form").scroll_into_view_if_needed()
    shot(ph, case, "kontakt", "Kontaktangaben (E-Mail freiwillig)")
    ph.click("#next"); ph.wait_for_selector("#success.on")
    ph.locator("#success").scroll_into_view_if_needed()
    shot(ph, case, "danke", "Bestätigung für den Bewerber")

with sync_playwright() as p:
    try:
        b = p.chromium.launch(channel=os.getenv("PLAYWRIGHT_CHANNEL") or "chrome", headless=True)
    except Exception:
        b = p.chromium.launch(headless=True)  # Chromium aus `playwright install chromium`
    betrieb = b.new_page(viewport={"width": 1280, "height": 800})                     # der anfragende Betrieb
    wir = b.new_context(viewport={"width": 1280, "height": 900}).new_page()             # wir, intern
    mobile = dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)

    # ================= Fall A: Anfrage mit Freigabe =================
    A = "A"
    betrieb.goto(LANDING); betrieb.wait_for_timeout(1000)
    shot(betrieb, A, "landingpage", "Betrieb sieht auf stellenschraube.ch die Box «Kostenlose Vorschau»")
    betrieb.goto(f"{BASE}/vorschau")
    shot(betrieb, A, "maske-leer", "Eingabemaske /vorschau – E-Mail ist jetzt Pflicht")
    betrieb.fill("#url", "www.frutiger.com"); betrieb.fill("#job", "Maurer EFZ 100%")
    betrieb.fill("#email", "hr@frutiger-test.ch"); betrieb.fill("#name", "Anna Frutiger")
    shot(betrieb, A, "maske-ausgefuellt", "Website, Stelle, E-Mail und Name eingegeben")
    t = time.time(); betrieb.click("#go"); betrieb.wait_for_selector("#done.on", timeout=30000); dauer_a = time.time() - t
    shot(betrieb, A, "anfrage-erhalten", f"Nach {dauer_a:.1f} s: Anfrage erhalten – noch kein Link, wir prüfen zuerst")

    wir.goto(f"{BASE}/intern?key=dev")
    slug_a = wir.locator("table a[href^='/intern/']").first.get_attribute("href").split("/")[-1]
    link_a = f"{BASE}/employer/{slug_a}"
    blocked = b.new_page(); r = blocked.goto(link_a)
    shot(blocked, A, "gesperrt", f"Kundenseite vor der Freigabe öffentlich gesperrt (HTTP {r.status})"); blocked.close()
    shot(wir, A, "uebersicht-wartet", "Angebotsübersicht: neue Anfrage «Wartet auf Freigabe» mit Lead-Kontakt")
    wir.goto(f"{BASE}/intern/{slug_a}")
    shot(wir, A, "detail-vor-freigabe", "Detailseite: erkannte Daten, alle 5 Fragen, Knopf «Freigeben»", full=True)
    wir.click("button:has-text(\"Freigeben\")"); wir.wait_for_load_state()
    shot(wir, A, "detail-freigegeben", "Nach der Freigabe: fertige Mail an den Lead mit Link", full=True)

    ph = b.new_page(**mobile); ph.goto(link_a); ph.wait_for_timeout(800)
    shot(ph, A, "kundenseite", "Betrieb öffnet den Link auf dem Handy: Logo, Farbe, Stelle")
    phone_walkthrough(ph, A, [0, 2, [0, 2, 3], 1, 2])
    wir.goto(f"{BASE}/intern/{slug_a}")
    wir.locator("text=Bewerbungen (1)").scroll_into_view_if_needed()
    shot(wir, A, "bewerbung-test", "Bewerbung gespeichert – als «Test» markiert, weil die Seite noch nicht live ist")

    # ================= Fall B: Akquise =================
    B = "B"
    inserat = ("https://www.burkhalter.ch\n\nElektroinstallateur EFZ 80-100% (m/w/d)\n"
               "Für unsere Niederlassung in Zürich suchen wir eine motivierte Fachkraft. Deine Aufgaben: "
               "Installationen in Neubau und Umbau, Montage von Photovoltaik-Anlagen, Störungsbehebung im "
               "Pikettdienst. Du bringst mit: Lehre als Elektroinstallateur EFZ, Führerausweis Kat. B.")
    wir.goto(f"{BASE}/intern")
    wir.click("summary")
    wir.fill("#input", inserat); wir.fill("#name", "Herr Muster"); wir.fill("#email", "info@burkhalter-test.ch")
    shot(wir, B, "akquise-eingabe", "Wir fügen ein Inserat ein (Firmen-Website + Inseratstext) und die Ansprechperson")
    t = time.time(); wir.click("button:has-text(\"Formular erstellen\")"); wir.wait_for_url(re.compile(r"/intern/[a-z0-9-]+$"), timeout=30000)
    dauer_b = time.time() - t
    slug_b = wir.url.split("/")[-1]
    shot(wir, B, "akquise-detail", f"Nach {dauer_b:.1f} s: Akquise-Vorschlag mit Mail-Text, JPG und Fragen", full=True)

    img = urllib.request.urlopen(urllib.request.Request(f"{BASE}/intern/{slug_b}/vorschau.jpg?key=dev")).read()
    (OUT / f"{n:02d}-vorschau-jpg.jpg").write_bytes(img)
    log.append({"n": n, "case": B, "file": f"{n:02d}-vorschau-jpg.jpg", "note": "JPG für LinkedIn, Brief oder zweite Mail"})
    print(f"{n:02d} [B] JPG erzeugt ({len(img)//1024} KB)"); n += 1

    ph2 = b.new_page(**mobile); ph2.goto(f"{BASE}/employer/{slug_b}"); ph2.wait_for_timeout(800)
    shot(ph2, B, "akquise-kundenseite", "Der angeschriebene Betrieb öffnet den Vorschlag auf dem Handy")
    for i in (0, 1):  # wie ein echter Nutzer bis Frage 3 klicken
        ph2.locator(f".step[data-i='{i}'] .opt").first.click(); ph2.click("#next")
    ph2.locator(".step[data-i='2'] .opt").nth(3).click()
    ph2.locator("#form").scroll_into_view_if_needed()
    shot(ph2, B, "akquise-frage-3", "Frage 3 kennt die Arbeiten aus dem Inserat: Neubau, Umbau, Störungen, Photovoltaik stehen oben")

    wir.goto(f"{BASE}/intern")
    shot(wir, "A+B", "uebersicht-final", "Angebotsübersicht: beide Fälle an einem Ort, mit Status und Unterseite")
    b.close()

(OUT / "log.json").write_text(json.dumps({"slug_a": slug_a, "slug_b": slug_b, "dauer_a": round(dauer_a, 1),
    "dauer_b": round(dauer_b, 1), "steps": log}, ensure_ascii=False, indent=1))
print("fertig", slug_a, slug_b)
