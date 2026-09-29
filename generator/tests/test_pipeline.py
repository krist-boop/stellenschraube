"""Offline-Tests: Webseiten werden simuliert, es geht nichts ins Internet."""

import json
import re

import pytest

from stellenschraube import store
from stellenschraube.app import build_form, create_app
from stellenschraube.brand import pick_accent, usable
from stellenschraube.extract import is_public_url, parse_input
from stellenschraube.questions import detect_branch

JOBS_CH = """<html><head><title>Polymechaniker EFZ 100% - Bieli Maschinenbau AG - jobs.ch</title>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting",
"title":"Polymechaniker EFZ 80-100% (m/w/d)","description":"<p>CNC-Fräsen, Drehen, Montage</p>",
"hiringOrganization":{"@type":"Organization","name":"Bieli Maschinenbau AG","sameAs":"https://www.bieli.ch"},
"jobLocation":{"@type":"Place","address":{"addressLocality":"Aarau"}}}</script></head><body></body></html>"""

ELEKTRO = """<html><head><title>Elektro Minder AG | Ihr Elektriker in Zürich</title>
<meta name="theme-color" content="#ffffff"><style>:root{--color-primary:#0055A4}</style></head>
<body><img src="/img/logo-minder.svg" alt="Elektro Minder Logo"><h1>Willkommen</h1></body></html>"""

NO_TITLE = """<html><head><title>Startseite</title></head><body><a style="background:#e30613">Kontakt</a>
<a style="background:#e30613">Offerte</a></body></html>"""

PAGES = {
    "https://www.jobs.ch/de/stellenangebote/detail/123/": JOBS_CH,
    "https://www.bieli.ch": "<html><head><style>.btn{background:#F28C00}</style></head></html>",
    "https://www.elektro-minder.ch": ELEKTRO,
    "https://www.meier-sanitaer.ch": NO_TITLE,
}


def fake_fetch(url, timeout=8):
    return PAGES.get(url.rstrip("/") if url.rstrip("/") in PAGES else url), url


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "t.sqlite3"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


# ---------- Erkennung aus Freitext und URLs ----------

TEXT_CASES = [
    ("Schreinerei Sutter AG sucht per sofort einen Schreiner EFZ 100%", "Schreinerei Sutter AG", "Schreiner EFZ 100%", "holz"),
    ("Wir suchen einen Polymechaniker EFZ (m/w/d) bei Bieli Maschinenbau AG", "Bieli Maschinenbau AG", "Polymechaniker EFZ (m/w/d)", "metall"),
    ("Kaufmann Keramik AG sucht Sanitärinstallateur EFZ 100%. Installation, Service.", "Kaufmann Keramik AG", "Sanitärinstallateur EFZ 100%", "sanitaer"),
    ("Maler EFZ 80-100% gesucht – Malerei Brunner GmbH, Luzern", "Malerei Brunner GmbH", "Maler EFZ 80-100%", "maler"),
    ("Koch EFZ gesucht. Restaurant Torre Baden sucht Verstärkung.", None, "Koch EFZ", "gastro"),
]


@pytest.mark.parametrize("text,company,title,branch", TEXT_CASES)
def test_freitext(text, company, title, branch):
    info = parse_input(text, fetcher=fake_fetch)
    if company:
        assert info["company_name"] == company
    assert info["job_title"] == title
    assert detect_branch(text, title=info["job_title"]) == branch


def test_jobs_ch_jsonld():
    info = parse_input("https://www.jobs.ch/de/stellenangebote/detail/123/", fetcher=fake_fetch)
    assert info["company_name"] == "Bieli Maschinenbau AG"
    assert info["job_title"] == "Polymechaniker EFZ 80-100% (m/w/d)"
    assert info["location"] == "Aarau"
    assert info["company_url"] == "https://www.bieli.ch"  # Portal-URL darf nicht als Firmenseite gelten


def test_firmenwebsite():
    info = parse_input("www.elektro-minder.ch", job_title="Elektroinstallateur EFZ", fetcher=fake_fetch)
    assert info["company_name"] == "Elektro Minder AG"
    assert info["company_url"] == "https://www.elektro-minder.ch"


def test_firma_aus_domain_wenn_titel_nichtssagend():
    info = parse_input("https://www.meier-sanitaer.ch", fetcher=fake_fetch)
    assert info["company_name"] == "Meier Sanitaer"
    assert "Stelle nicht erkannt" in info["warnings"]


def test_nicht_erreichbar_gibt_warnung_statt_absturz():
    info = parse_input("https://gibts-nicht-xyz.ch", fetcher=lambda u, timeout=8: (None, u))
    assert info["company_name"] == "Gibts Nicht Xyz"
    assert "Seite konnte nicht geladen werden" in info["warnings"]


# ---------- Farben ----------

def test_farbe_css_variable_schlaegt_weisse_theme_color():
    form = build_form("www.elektro-minder.ch", fetcher=fake_fetch)
    assert form["brand"]["accent"] == "#0055a4"
    assert form["brand"]["logo_url"] == "https://www.elektro-minder.ch/img/logo-minder.svg"


def test_farbe_aus_verlinkter_firmenseite_bei_portal():
    form = build_form("https://www.jobs.ch/de/stellenangebote/detail/123/", fetcher=fake_fetch)
    assert form["brand"]["accent"] == "#f28c00"


def test_unbrauchbare_farben_werden_ignoriert():
    assert not usable("#ffffff") and not usable("#111111") and not usable("#777777")
    assert pick_accent(["body{color:#333;background:#fff}"])[1] == "fallback"


# ---------- Sicherheit ----------

@pytest.mark.parametrize("url", ["http://127.0.0.1:5050", "http://localhost/", "http://169.254.169.254/latest",
                                 "http://10.0.0.1", "file:///etc/passwd", "ftp://example.com"])
def test_ssrf_blockiert(url):
    assert not is_public_url(url)


M = "chef@betrieb.ch"


def test_xss_wird_escaped():
    c = create_app().test_client()
    c.post("/api/preview", json={"input": "<script>alert(1)</script> Firma X AG sucht Maler EFZ",
                                 "job_title": "<img src=x onerror=alert(2)>", "email": M})
    slug = store.list_forms()[0]["slug"]
    page = c.get(f"/employer/{slug}?key=dev").get_data(as_text=True)
    assert "<script>alert(1)" not in page and "<img src=x" not in page
    assert "&lt;img src=x" in page


# ---------- Fall A: Anfrage mit Freigabe ----------

def test_fall_a_anfrage_freigabe(monkeypatch):
    monkeypatch.setattr("stellenschraube.extract.fetch", fake_fetch)
    c = create_app().test_client()

    assert c.post("/api/preview", json={"input": "Schreinerei Sutter AG sucht Schreiner EFZ 100%"}).status_code == 400
    r = c.post("/api/preview", json={"input": "Schreinerei Sutter AG sucht Schreiner EFZ 100%", "email": M,
                                     "name": "Hans Sutter", "telefon": "041 123 45 67"})
    d = r.get_json()
    assert r.status_code == 200 and "path" not in d and d["email"] == M  # kein Link vor der Freigabe

    row = store.list_forms()[0]
    slug = row["slug"]
    assert re.fullmatch(r"schreinerei-sutter-[0-9a-f]{6}", slug)
    assert row["status"] == "wartet" and row["lead"] == {"email": M, "name": "Hans Sutter", "telefon": "041 123 45 67"}

    assert c.get(f"/employer/{slug}").status_code == 404          # gesperrt für die Öffentlichkeit
    assert c.post(f"/api/apply/{slug}", json={}).status_code == 404
    resp = c.get(f"/employer/{slug}?key=dev")                      # für uns sichtbar
    assert resp.status_code == 200 and resp.headers["X-Robots-Tag"] == "noindex, nofollow"
    page = resp.get_data(as_text=True)
    assert "Schreiner EFZ gesucht." in page and "stellenschraube" not in page.lower()
    assert page.count('class="step"') == 6  # 5 Fragen + Kontakt
    assert "data-multi" in page

    detail = c.get(f"/intern/{slug}?key=dev").get_data(as_text=True)
    assert "Freigeben" in detail and "In Mailprogramm öffnen" not in detail  # Mail erst nach Freigabe
    c.post(f"/intern/{slug}/status?key=dev", data={"status": "freigegeben"})
    assert store.get(slug)["status"] == "freigegeben" and store.get(slug)["approved"]
    assert c.get(f"/employer/{slug}").status_code == 200
    detail = c.get(f"/intern/{slug}?key=dev").get_data(as_text=True)
    assert "mailto:chef%40betrieb.ch" in detail and "Grüezi Hans Sutter," in detail


def test_test_bewerbungen_vs_echte(monkeypatch):
    monkeypatch.setattr("stellenschraube.extract.fetch", fake_fetch)
    c = create_app().test_client()
    c.post("/api/preview", json={"input": "Maler EFZ bei Test AG", "email": M})
    slug = store.list_forms()[0]["slug"]
    c.post(f"/intern/{slug}/status?key=dev", data={"status": "freigegeben"})
    c2 = create_app().test_client()  # ohne intern-Cookie, wie der Betrieb
    bew = {"name": "Luca Meier", "telefon": "079 123 45 67", "antworten": [{"frage": "Q", "antwort": "A"}]}
    assert c2.post(f"/api/apply/{slug}", json={"name": "M", "telefon": "1"}).status_code == 400
    c2.post(f"/api/apply/{slug}", json=bew)                        # Betrieb klickt Vorschau durch
    c.post(f"/intern/{slug}/status?key=dev", data={"status": "live"})
    c2.post(f"/api/apply/{slug}", json=bew)                        # echte Bewerbung nach live
    tests = [a["test"] for a in store.list_applications(slug)]
    assert sorted(tests) == [False, True]


# ---------- Fall B: Akquise ----------

def test_fall_b_akquise(monkeypatch):
    monkeypatch.setattr("stellenschraube.extract.fetch", fake_fetch)
    c = create_app().test_client()
    r = c.post("/intern/neu?key=dev", data={"input": "https://www.jobs.ch/de/stellenangebote/detail/123/",
                                            "name": "Herr Bieli", "email": "info@bieli.ch"})
    assert r.status_code == 302
    row = store.list_forms()[0]
    assert row["status"] == "akquise" and row["data"]["company_name"] == "Bieli Maschinenbau AG"
    assert c.get(f"/employer/{row['slug']}").status_code == 200    # Vorschlag ist per Link sichtbar
    detail = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "Euer Inserat «Polymechaniker EFZ»" in detail and "Kein Interesse?" in detail
    assert "Grüezi Herr Bieli," in detail and "JPG herunterladen" in detail
    ov = c.get("/intern").get_data(as_text=True)                   # Cookie von vorher
    assert f"/employer/{row['slug']}" in ov and "Akquise-Vorschlag" in ov


def test_akquise_ohne_stelle_fragt_nach(monkeypatch):
    monkeypatch.setattr("stellenschraube.extract.fetch", fake_fetch)
    c = create_app().test_client()
    r = c.post("/intern/neu?key=dev", data={"input": "www.elektro-minder.ch"})
    assert "msg=" in r.headers["Location"] and store.list_forms() == []


def test_fehlerfaelle():
    c = create_app().test_client()
    assert c.post("/api/preview", json={"input": "", "email": M}).status_code == 400
    assert c.get("/employer/gibts-nicht-000000").status_code == 404
    assert c.post("/api/apply/gibts-nicht-000000", json={}).status_code == 404
    assert c.post("/intern/neu", data={"input": "x"}).status_code == 404  # ohne Schlüssel


def test_rate_limit(monkeypatch):
    monkeypatch.setattr("stellenschraube.app.MAX_PER_HOUR", 2)
    c = create_app().test_client()
    codes = [c.post("/api/preview", json={"input": "Maler EFZ bei Test AG", "email": M}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_intern_mit_token(monkeypatch):
    monkeypatch.setenv("INTERN_TOKEN", "geheim")
    c = create_app().test_client()
    assert c.get("/intern").status_code == 404
    assert c.get("/intern?key=dev").status_code == 404
    assert c.get("/intern?key=geheim").status_code == 200
    assert c.get("/intern").status_code == 200  # danach per Cookie


REGRESSION = [
    ("Für unser Team suchen wir per 1. Januar einen Metallbauer EFZ. Metallbau Fässler GmbH", "Metallbau Fässler GmbH", "Metallbauer EFZ", "metall"),
    ("Gipser-Trockenbauer EFZ gesucht. Stuckateur Weber GmbH", "Stuckateur Weber GmbH", "Gipser-Trockenbauer EFZ", "maler"),
    ("Koch/Köchin EFZ 100% Gasthof Ochsen, Stans", "Gasthof Ochsen", "Koch/Köchin EFZ 100%", "gastro"),
    ("CNC-Fräser (m/w/d) 100% – Präzisionsmechanik Frei AG", "Präzisionsmechanik Frei AG", "CNC-Fräser (m/w/d) 100%", "metall"),
    ("Projektleiter Elektro 100% – Elektro Burkhalter AG", "Elektro Burkhalter AG", "Projektleiter Elektro 100%", "elektro"),
    ("Bäcker-Konditor EFZ 80% – Bäckerei Wüthrich", "Bäckerei Wüthrich", "Bäcker-Konditor EFZ 80%", "gastro"),
    ("Die Müller Elektro AG in Winterthur sucht eine/n Elektroinstallateur/in EFZ 80-100%", "Müller Elektro AG", "Elektroinstallateur/in EFZ 80-100%", "elektro"),
]


@pytest.mark.parametrize("text,company,title,branch", REGRESSION)
def test_regression(text, company, title, branch):
    info = parse_input(text, fetcher=lambda u, timeout=8: (None, u))
    assert (info["company_name"], info["job_title"]) == (company, title)
    assert detect_branch(text, title=info["job_title"]) == branch


# ---------- Qualität der Fragen ----------

from stellenschraube.questions import check_questions, template_questions  # noqa: E402

JOBS = [
    ("Sanitärinstallateur EFZ 100%", "Führerschein Kat. B zwingend", "Führerausweis"),
    ("Elektroinstallateur EFZ", "Bereitschaft für Pikettdienst", "Pikett"),
    ("Polymechaniker EFZ", "Arbeit im 2-Schichtbetrieb", "Schicht"),
    ("Koch EFZ", "Teildienst, Wochenenden", "Arbeitszeiten"),
    ("Maler EFZ 80-100%", "Innen und Fassaden", "Pensum"),
    ("Schreiner EFZ", "Möbelbau", "Arbeitsweg"),
    ("Chauffeur Kat. C", "Führerausweis C", "Arbeitsweg"),  # Ausweis kommt schon in Frage 3
]


@pytest.mark.parametrize("title,text,q4", JOBS)
def test_fragen_qualitaet(title, text, q4):
    branch, qs = template_questions(title, text)
    assert check_questions(qs) == []
    assert len(qs) == 5
    assert [q["eyebrow"] for q in qs] == ["Abschluss", "Erfahrung", "Können", q4, "Situation"]
    assert qs[2]["multi"] and len(qs[2]["options"]) == 5
    assert all(len(q["options"]) >= 4 for q in qs)  # keine blossen Ja/Nein-Fragen


def test_konkrete_arbeiten_aus_inserat_zuerst():
    _, qs = template_questions("Elektroinstallateur EFZ", "Du montierst Photovoltaik-Anlagen und machst Messungen")
    assert qs[2]["options"][:2] == ["Photovoltaik montiert", "Messungen / Sicherheitsnachweis"]


def test_arbeitsweg_mit_ort():
    _, qs = template_questions("Schreiner EFZ", "", location="Aarau")
    assert qs[3]["question"] == "Wie lange wäre dein Arbeitsweg nach Aarau?"


def test_pensum_optionen():
    _, qs = template_questions("Maler EFZ 60-100%", "")
    assert qs[3]["options"] == ["100%", "80%", "60%", "Weniger als 60%"]


@pytest.mark.parametrize("bad", [
    {"question": "Wie alt bist du?", "options": ["18-25", "26-35"]},
    {"question": "Was ist deine Lohnvorstellung?", "options": ["5000", "6000"]},
    {"question": "Woher kommst du", "options": ["CH", "EU"]},
    {"question": "Hast du Kinder?", "options": ["Ja", "Nein"]},
    {"question": "Bist du gross?", "options": ["Ja", "ja"]},
])
def test_pruefung_faengt_schlechte_fragen(bad):
    good = template_questions("Maler EFZ", "")[1][:4]
    assert check_questions(good + [bad])


def test_claude_antwort_wird_geprueft(monkeypatch):
    """Liefert Claude verbotene Fragen, fällt das System auf die Vorlage zurück."""
    import stellenschraube.questions as q
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    def fake_claude(*a):
        out = [{"eyebrow": "X", "question": "Wie alt bist du?", "options": ["jung", "alt", "mittel", "?"]}] * 5
        issues = q.check_questions(out)
        raise ValueError(issues)
    monkeypatch.setattr(q, "claude_questions", fake_claude)
    branch, qs, source = q.get_questions("Maler EFZ", "Firma", "")
    assert source == "vorlage" and check_questions(qs) == []


def test_tippfehler_url_fragt_nach(monkeypatch):
    monkeypatch.setattr("stellenschraube.extract.fetch", lambda u, timeout=8: (None, u))
    r = create_app().test_client().post("/api/preview", json={"input": "www.gibts-nicht.ch", "job_title": "Maler EFZ", "email": M})
    assert r.status_code == 422 and r.get_json()["field"] == "url"
    assert store.list_forms() == []  # keine Vorschau mit erfundenen Angaben


def test_nur_firmenseite_fragt_nach_stelle(monkeypatch):
    monkeypatch.setattr("stellenschraube.extract.fetch", fake_fetch)
    
    c = create_app().test_client()
    r = c.post("/api/preview", json={"input": "www.elektro-minder.ch", "email": M})
    assert r.status_code == 422 and r.get_json()["field"] == "job"
    r = c.post("/api/preview", json={"input": "www.elektro-minder.ch", "job_title": "Elektroinstallateur EFZ", "email": M})
    assert r.status_code == 200


def test_keine_doppelten_formulare(monkeypatch):
    monkeypatch.setattr("stellenschraube.extract.fetch", fake_fetch)
    c = create_app().test_client()
    for _ in range(3):
        assert c.post("/api/preview", json={"input": "www.elektro-minder.ch", "job_title": "Elektroinstallateur EFZ",
                                            "email": M}).status_code == 200
    c.post("/api/preview", json={"input": "www.elektro-minder.ch", "job_title": "Automatiker EFZ", "email": M})
    assert len(store.list_forms()) == 2  # gleiche Stelle nur einmal, andere Stelle neu
    r = c.post("/intern/neu?key=dev", data={"input": "www.elektro-minder.ch", "job_title": "Automatiker EFZ"})
    assert len(store.list_forms()) == 2 and r.headers["Location"].startswith("/intern/elektro-minder-")


def test_lesbare_schrift_auf_firmenfarbe():
    from stellenschraube.brand import contrast, on_color
    for farbe in ("#5dad48", "#d52b1e", "#0055a4", "#f28c00", "#DC2626", "#ffd400"):
        assert contrast(farbe, on_color(farbe)) >= 4.5 or farbe in ("#d52b1e", "#DC2626")
    assert on_color("#5dad48") == "#0A0A08" and on_color("#0055a4") == "#FFFFFF"
