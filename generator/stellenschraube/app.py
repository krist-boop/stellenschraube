"""stellenschraube – Vorschau-Generator für Bewerbungsformulare."""

import os
import time
from collections import defaultdict, deque
from datetime import datetime

import urllib3
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request

from . import store
from .brand import on_color, scrape_brand
from .extract import parse_input
from .questions import _base_title, get_questions

load_dotenv()
urllib3.disable_warnings()

MAX_PER_HOUR = int(os.getenv("PREVIEWS_PER_HOUR", "20"))


def build_form(raw, job_title=None, company_name=None, fetcher=None):
    """Kompletter Ablauf ohne Web-Schicht: Eingabe -> fertiges Formular-dict (noch nicht gespeichert)."""
    kw = {"fetcher": fetcher} if fetcher else {}
    info = parse_input(raw, job_title=job_title, company_name=company_name, **kw)
    brand = scrape_brand(info["company_url"], **kw)
    brand["on_accent"] = on_color(brand["accent"])
    branch, questions, q_source = get_questions(info["job_title"], info["company_name"], info["text"])
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


def create_app():
    app = Flask(__name__)
    app.jinja_env.filters["dt"] = lambda ts: datetime.fromtimestamp(ts).strftime("%d.%m. %H:%M")
    hits = defaultdict(deque)

    def rate_limited(ip):
        q, now = hits[ip], time.time()
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= MAX_PER_HOUR:
            return True
        q.append(now)
        return False

    def require_intern():
        token = os.getenv("INTERN_TOKEN")
        if token and request.args.get("key") != token:
            abort(404)

    @app.get("/")
    @app.get("/vorschau")
    def index():
        return render_template("index.html")

    @app.post("/api/preview")
    def preview():
        d = request.get_json(silent=True) or {}
        raw = str(d.get("input", "")).strip()[:20000]
        if len(raw) < 4:
            return jsonify(error="Bitte gib deine Website oder den Link zum Inserat ein."), 400
        if rate_limited(request.headers.get("X-Forwarded-For", request.remote_addr)):
            return jsonify(error="Zu viele Anfragen in kurzer Zeit."), 429
        form = build_form(raw, job_title=str(d.get("job_title") or "")[:120] or None,
                          company_name=str(d.get("company_name") or "")[:120] or None)
        # Lieber nachfragen als eine Vorschau mit erfundenen Angaben zeigen
        if "Seite konnte nicht geladen werden" in form["warnings"] and len(raw) < 200:
            return jsonify(error=f"Wir konnten {form['source_url'] or raw} nicht öffnen. Stimmt die Adresse?",
                           field="url"), 422
        if "Stelle nicht erkannt" in form["warnings"]:
            return jsonify(error="Welche Stelle willst du besetzen? Trag sie unten ein.", field="job"), 422
        email = str(d.get("email") or "").strip()[:200] or None
        slug = store.save_form(form, requester_email=email, source=form["source_url"] or "text")
        # TODO: Mail mit dem Link an `email` schicken, sobald ein Mail-Dienst gewählt ist
        return jsonify(path=f"/employer/{slug}", slug=slug, company_name=form["company_name"],
                       job_title=form["base_title"], warnings=form["warnings"])

    @app.get("/employer/<slug>")
    @app.get("/employer/<slug>/")
    def employer(slug):
        f = store.get_form(slug)
        if not f:
            abort(404)
        return render_template("employer.html", f=f)

    @app.post("/api/apply/<slug>")
    def apply(slug):
        if not store.get_form(slug):
            abort(404)
        d = request.get_json(silent=True) or {}
        name, tel = str(d.get("name", "")).strip()[:120], str(d.get("telefon", "")).strip()[:40]
        if len(name) < 2 or len(tel) < 9:
            return jsonify(error="Name und Telefon fehlen."), 400
        answers = [{"frage": str(a.get("frage", ""))[:200], "antwort": str(a.get("antwort") or "")[:500]}
                   for a in (d.get("antworten") or [])[:10] if isinstance(a, dict)]
        store.save_application(slug, {"name": name, "telefon": tel,
                                      "email": str(d.get("email", "")).strip()[:200], "antworten": answers})
        # TODO: Betrieb benachrichtigen (Mail/SMS) – siehe offene Fragen
        return jsonify(ok=True)

    @app.get("/intern")
    def intern():
        require_intern()
        return render_template("intern.html", rows=store.list_forms())

    @app.get("/intern/<slug>")
    def intern_apps(slug):
        require_intern()
        return jsonify(form=store.get_form(slug), bewerbungen=store.list_applications(slug))

    @app.get("/health")
    def health():
        return jsonify(ok=True)

    return app
