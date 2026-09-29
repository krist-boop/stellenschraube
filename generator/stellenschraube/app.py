"""stellenschraube – Vorschau-Generator für Bewerbungsformulare.

Fall A (Anfrage): Betrieb gibt auf /vorschau Website + E-Mail ein -> Formular wird gebaut, bleibt gesperrt
                  (Status «wartet») -> wir prüfen und geben in der Angebotsübersicht frei -> Mail mit Link.
Fall B (Akquise): Wir erstellen in der Angebotsübersicht aus einem Inserat ein Formular (Status «akquise»)
                  und schicken es dem Betrieb als Vorschlag.
Bewerbungen zählen nur als echt, wenn das Formular «live» ist; alles davor ist Test/Vorschau.
"""

import os
import time
from collections import defaultdict, deque
from datetime import datetime
from urllib.parse import quote

import urllib3
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, redirect, render_template, request, send_file

from . import store
from .brand import on_color, scrape_brand
from .extract import parse_input
from .questions import _base_title, get_questions

load_dotenv()
urllib3.disable_warnings()

MAX_PER_HOUR = int(os.getenv("PREVIEWS_PER_HOUR", "20"))
STATUS_LABEL = {"wartet": "Wartet auf Freigabe", "freigegeben": "Vorschau verschickt",
                "akquise": "Akquise-Vorschlag", "live": "Live"}


def build_form(raw, job_title=None, company_name=None, fetcher=None):
    """Kompletter Ablauf ohne Web-Schicht: Eingabe -> fertiges Formular-dict (noch nicht gespeichert)."""
    kw = {"fetcher": fetcher} if fetcher else {}
    info = parse_input(raw, job_title=job_title, company_name=company_name, **kw)
    brand = scrape_brand(info["company_url"], **kw)
    brand["on_accent"] = on_color(brand["accent"])
    branch, questions, q_source = get_questions(info["job_title"], info["company_name"], info["text"],
                                                info["location"])
    return {
        "company_name": info["company_name"],
        "job_title": info["job_title"],
        "base_title": _base_title(info["job_title"]),
        "location": info["location"],
        "company_url": info["company_url"],
        "source_url": info["source_url"],
        "brand": brand,
        "branch": branch,
        "questions": questions,
        "question_source": q_source,
        "warnings": info["warnings"],
    }


def mail_text(row, link, sender="Krist"):
    """Betreff und Text für die Mail an den Betrieb – bewusst schlicht: kein HTML, ein Link, klare Absage-Option."""
    f, lead = row["data"], row["lead"]
    anrede = f"Grüezi {lead['name']}," if lead.get("name") else "Grüezi,"
    if row["status"] == "akquise":
        subject = f"Euer Inserat «{f['base_title']}»"
        body = (f"{anrede}\n\n"
                f"ich habe gesehen, dass {f['company_name']} einen {f['base_title']} sucht. Wir haben dafür eine "
                f"Bewerbungsseite in eurem Design gebaut, auf der sich Fachleute in 2 Minuten vom Handy aus "
                f"bewerben, ohne Lebenslauf:\n\n{link}\n\n"
                f"Die Seite ist nicht öffentlich auffindbar und kostet euch nichts. Wenn sie euch gefällt, spielen wir die Stelle "
                f"gezielt in eurer Region auf Instagram und Facebook aus, bei den Fachleuten, die gerade nicht "
                f"auf Jobportalen suchen.\n\n"
                f"Kein Interesse? Eine kurze Antwort genügt, dann melde ich mich nicht mehr.\n\n"
                f"Freundliche Grüsse\n{sender}\nstellenschraube · stellenschraube.ch")
    else:
        subject = f"Deine Vorschau: {f['base_title']}"
        body = (f"{anrede}\n\n"
                f"danke für deine Anfrage. Hier ist die Vorschau für die Stelle {f['base_title']} bei "
                f"{f['company_name']}:\n\n{link}\n\n"
                f"Klick dich ruhig selbst durch, genau so sehen es später die Bewerber auf dem Handy. "
                f"Wenn es dir gefällt, rufe ich dich kurz an und wir besprechen, wie wir die Stelle ausspielen.\n\n"
                f"Freundliche Grüsse\n{sender}\nstellenschraube · stellenschraube.ch")
    mailto = f"mailto:{quote(lead.get('email', ''))}?subject={quote(subject)}&body={quote(body)}"
    return subject, body, mailto


def create_app():
    app = Flask(__name__)
    app.jinja_env.filters["dt"] = lambda ts: datetime.fromtimestamp(ts).strftime("%d.%m. %H:%M") if ts else ""
    app.jinja_env.globals["STATUS_LABEL"] = STATUS_LABEL
    hits = defaultdict(deque)

    def token():
        return os.getenv("INTERN_TOKEN") or "dev"  # lokal: /intern?key=dev

    def is_intern():
        return token() in (request.args.get("key"), request.cookies.get("intern"))

    def require_intern():
        if not is_intern():
            abort(404)

    @app.after_request
    def remember_intern(resp):
        # Wer einmal mit ?key= kommt, bleibt 30 Tage angemeldet (Cookie nur für uns, nicht für Kunden)
        if request.args.get("key") == token():
            resp.set_cookie("intern", token(), httponly=True, samesite="Lax", max_age=60 * 60 * 24 * 30)
        return resp

    def base_url():
        return os.getenv("PUBLIC_URL", request.host_url.rstrip("/"))

    def rate_limited(ip):
        q, now = hits[ip], time.time()
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= MAX_PER_HOUR:
            return True
        q.append(now)
        return False

    # ---------- Fall A: öffentliche Anfrage ----------

    @app.get("/")
    @app.get("/vorschau")
    def index():
        return render_template("index.html")

    @app.post("/api/preview")
    def preview():
        d = request.get_json(silent=True) or {}
        raw = str(d.get("input", "")).strip()[:20000]
        email = str(d.get("email") or "").strip()[:200]
        if len(raw) < 4:
            return jsonify(error="Bitte gib deine Website oder den Link zum Inserat ein.", field="url"), 400
        if "@" not in email or "." not in email.split("@")[-1]:
            return jsonify(error="Wir brauchen deine E-Mail, um dir die Vorschau zu schicken.", field="email"), 400
        if rate_limited(request.headers.get("X-Forwarded-For", request.remote_addr)):
            return jsonify(error="Zu viele Anfragen in kurzer Zeit."), 429
        form = build_form(raw, job_title=str(d.get("job_title") or "")[:120] or None)
        # Lieber nachfragen als eine Vorschau mit erfundenen Angaben bauen
        if "Seite konnte nicht geladen werden" in form["warnings"] and len(raw) < 200:
            return jsonify(error=f"Wir konnten {form['source_url'] or raw} nicht öffnen. Stimmt die Adresse?",
                           field="url"), 422
        if "Stelle nicht erkannt" in form["warnings"]:
            return jsonify(error="Welche Stelle willst du besetzen? Trag sie bei «Offene Stelle» ein.", field="job"), 422
        lead = {"email": email, "name": str(d.get("name") or "").strip()[:120],
                "telefon": str(d.get("telefon") or "").strip()[:40]}
        source = form["source_url"] or "text"
        if not (source != "text" and store.find_duplicate(source, form["job_title"])):
            store.save_form(form, status="wartet", lead=lead, source=source)
        return jsonify(ok=True, email=email, company_name=form["company_name"], job_title=form["base_title"])

    # ---------- Kundenseite ----------

    @app.get("/employer/<slug>")
    @app.get("/employer/<slug>/")
    def employer(slug):
        row = store.get(slug)
        if not row or (row["status"] == "wartet" and not is_intern()):
            abort(404)  # vor der Freigabe nur für uns sichtbar
        resp = app.make_response(render_template("employer.html", f=row["data"]))
        # Doppelt abgesichert: meta robots im HTML und Header
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        return resp

    @app.post("/api/apply/<slug>")
    def apply(slug):
        row = store.get(slug)
        if not row or (row["status"] == "wartet" and not is_intern()):
            abort(404)
        d = request.get_json(silent=True) or {}
        name, tel = str(d.get("name", "")).strip()[:120], str(d.get("telefon", "")).strip()[:40]
        if len(name) < 2 or len(tel) < 9:
            return jsonify(error="Name und Telefon fehlen."), 400
        answers = [{"frage": str(a.get("frage", ""))[:200], "antwort": str(a.get("antwort") or "")[:500]}
                   for a in (d.get("antworten") or [])[:10] if isinstance(a, dict)]
        store.save_application(slug, {
            "name": name, "telefon": tel, "email": str(d.get("email", "")).strip()[:200],
            "antworten": answers,
            # Nur Bewerbungen auf live geschalteten Seiten sind echt – vorher klickt der Betrieb oder wir
            "test": row["status"] != "live" or is_intern(),
        })
        # TODO: Betrieb benachrichtigen (Mail/SMS), sobald ein Versanddienst gewählt ist
        return jsonify(ok=True)

    # ---------- Angebotsübersicht (intern) ----------

    @app.get("/intern")
    def intern():
        require_intern()
        return render_template("intern.html", rows=store.list_forms(), msg=request.args.get("msg"))

    @app.post("/intern/neu")
    def intern_new():
        """Fall B: Akquise-Vorschlag aus einem Inserat."""
        require_intern()
        raw = request.form.get("input", "").strip()
        if len(raw) < 4:
            return redirect("/intern?msg=" + quote("Bitte Inserat-Link oder Text einfügen"))
        form = build_form(raw, job_title=request.form.get("job_title") or None,
                          company_name=request.form.get("company_name") or None)
        problems = [w for w in form["warnings"] if w in ("Stelle nicht erkannt", "Seite konnte nicht geladen werden")]
        if problems:
            return redirect("/intern?msg=" + quote(" / ".join(problems) + " – bitte Stelle von Hand angeben"))
        source = form["source_url"] or "text"
        dup = source != "text" and store.find_duplicate(source, form["job_title"])
        if dup:
            return redirect(f"/intern/{dup['slug']}")  # gibt es schon: kein zweites Formular
        lead = {"email": request.form.get("email", "").strip(), "name": request.form.get("name", "").strip()}
        slug = store.save_form(form, status="akquise", lead=lead, source=source)
        return redirect(f"/intern/{slug}")

    @app.get("/intern/<slug>")
    def intern_detail(slug):
        require_intern()
        row = store.get(slug)
        if not row:
            abort(404)
        link = f"{base_url()}/employer/{slug}"
        subject, body, mailto = mail_text(row, link)
        return render_template("intern_detail.html", r=row, link=link, subject=subject, body=body,
                               mailto=mailto, apps=store.list_applications(slug))

    @app.post("/intern/<slug>/status")
    def intern_status(slug):
        require_intern()
        status = request.form.get("status")
        if not store.get(slug) or status not in store.STATUSES:
            abort(400)
        store.set_status(slug, status)
        return redirect(f"/intern/{slug}")

    @app.get("/intern/<slug>/vorschau.jpg")
    def intern_jpg(slug):
        """Bild der Kundenseite im Handyrahmen – für LinkedIn, Brief/Postkarte oder die zweite Mail."""
        require_intern()
        if not store.get(slug):
            abort(404)
        from .preview_image import render_jpg
        path = render_jpg(f"{request.host_url.rstrip('/')}/employer/{slug}?key={token()}", slug)
        return send_file(path, mimetype="image/jpeg", download_name=f"vorschau-{slug}.jpg")

    @app.errorhandler(404)
    def not_found(_):
        # Neutral, ohne stellenschraube: auch Bewerber mit einem alten Link landen hier
        return render_template("404.html"), 404

    @app.get("/health")
    def health():
        return jsonify(ok=True)

    return app
