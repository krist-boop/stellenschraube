"""SQLite-Speicher für Formulare (mit Status und Lead) und Bewerbungen."""

import json
import os
import re
import secrets
import sqlite3
import time
import unicodedata
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data.sqlite3"))

# Status eines Formulars:
#   wartet      – Anfrage über /vorschau, Seite noch gesperrt, wartet auf unsere Freigabe (Fall A)
#   freigegeben – Link wurde dem Betrieb geschickt
#   akquise     – von uns aus einem Inserat erstellt, als Vorschlag an einen potenziellen Kunden (Fall B)
#   live        – Kunde, Werbung läuft: erst ab hier zählen Bewerbungen als echt
STATUSES = ("wartet", "freigegeben", "akquise", "live")

SCHEMA = """
CREATE TABLE IF NOT EXISTS forms (
  slug TEXT PRIMARY KEY, created INTEGER, data TEXT, requester_email TEXT, source TEXT
);
CREATE TABLE IF NOT EXISTS applications (
  id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT, created INTEGER, data TEXT
);
"""
MIGRATIONS = [
    ("status", "ALTER TABLE forms ADD COLUMN status TEXT DEFAULT 'freigegeben'"),
    ("lead", "ALTER TABLE forms ADD COLUMN lead TEXT DEFAULT '{}'"),
    ("approved", "ALTER TABLE forms ADD COLUMN approved INTEGER"),
]


@contextmanager
def _conn():
    """Verbindung öffnen, bei Erfolg committen und immer schliessen."""
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        c.executescript(SCHEMA)
        cols = {r["name"] for r in c.execute("PRAGMA table_info(forms)")}
        for col, sql in MIGRATIONS:
            if col not in cols:
                c.execute(sql)
        yield c
        c.commit()
    finally:
        c.close()


def slugify(name):
    s = unicodedata.normalize("NFKD", name.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue"))
    s = s.encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(ag|gmbh|sa|sarl|klg|kg)\b", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return "-".join(s.split("-")[:4])[:40] or "betrieb"


def new_slug(company_name):
    # 6 Zeichen (16 Mio. Möglichkeiten): Links lassen sich nicht durchprobieren
    return f"{slugify(company_name)}-{secrets.token_hex(3)}"


def save_form(form, status="wartet", lead=None, source=None):
    assert status in STATUSES
    lead = lead or {}
    with _conn() as c:
        slug = new_slug(form["company_name"])
        while c.execute("SELECT 1 FROM forms WHERE slug=?", (slug,)).fetchone():
            slug = new_slug(form["company_name"])
        form["slug"] = slug
        c.execute("INSERT INTO forms (slug, created, data, requester_email, source, status, lead) "
                  "VALUES (?,?,?,?,?,?,?)",
                  (slug, int(time.time()), json.dumps(form, ensure_ascii=False), lead.get("email"), source,
                   status, json.dumps(lead, ensure_ascii=False)))
    return slug


def find_duplicate(source, job_title, days=14):
    """Gleiche Quelle + gleiche Stelle in den letzten Tagen -> bestehendes Formular statt eines neuen."""
    since = int(time.time()) - days * 86400
    with _conn() as c:
        for r in c.execute("SELECT * FROM forms WHERE source=? AND created>=? ORDER BY created DESC",
                           (source, since)):
            if json.loads(r["data"])["job_title"].lower() == job_title.lower():
                return _row(r)
    return None


def _row(r):
    return dict(slug=r["slug"], created=r["created"], data=json.loads(r["data"]), source=r["source"],
                status=r["status"], lead=json.loads(r["lead"] or "{}"), approved=r["approved"])


def get(slug):
    with _conn() as c:
        r = c.execute("SELECT * FROM forms WHERE slug=?", (slug,)).fetchone()
    return _row(r) if r else None


def get_form(slug):
    row = get(slug)
    return row["data"] if row else None


def set_status(slug, status):
    assert status in STATUSES
    with _conn() as c:
        c.execute("UPDATE forms SET status=?, approved=? WHERE slug=?",
                  (status, int(time.time()) if status == "freigegeben" else None, slug))


def list_forms(limit=200):
    with _conn() as c:
        rows = c.execute(
            "SELECT f.*, (SELECT COUNT(*) FROM applications a WHERE a.slug=f.slug) AS n "
            "FROM forms f ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
    return [dict(_row(r), n=r["n"]) for r in rows]


def save_application(slug, data):
    with _conn() as c:
        c.execute("INSERT INTO applications (slug, created, data) VALUES (?,?,?)",
                  (slug, int(time.time()), json.dumps(data, ensure_ascii=False)))


def list_applications(slug):
    with _conn() as c:
        rows = c.execute("SELECT created, data FROM applications WHERE slug=? ORDER BY created DESC",
                         (slug,)).fetchall()
    return [dict(created=r["created"], **json.loads(r["data"])) for r in rows]
