"""SQLite-Speicher für Formulare, Vorschau-Anfragen und Bewerbungen."""

import json
import os
import re
import secrets
import sqlite3
import time
import unicodedata
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data.sqlite3"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS forms (
  slug TEXT PRIMARY KEY, created INTEGER, data TEXT, requester_email TEXT, source TEXT
);
CREATE TABLE IF NOT EXISTS applications (
  id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT, created INTEGER, data TEXT
);
"""


@contextmanager
def _conn():
    """Verbindung öffnen, bei Erfolg committen und immer schliessen."""
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        c.executescript(SCHEMA)
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


def save_form(form, requester_email=None, source=None):
    with _conn() as c:
        slug = new_slug(form["company_name"])
        while c.execute("SELECT 1 FROM forms WHERE slug=?", (slug,)).fetchone():
            slug = new_slug(form["company_name"])
        form["slug"] = slug
        c.execute("INSERT INTO forms VALUES (?,?,?,?,?)",
                  (slug, int(time.time()), json.dumps(form, ensure_ascii=False), requester_email, source))
    return slug


def get_form(slug):
    with _conn() as c:
        row = c.execute("SELECT data FROM forms WHERE slug=?", (slug,)).fetchone()
    return json.loads(row["data"]) if row else None


def list_forms(limit=50):
    with _conn() as c:
        rows = c.execute(
            "SELECT f.slug, f.created, f.data, f.requester_email, f.source, "
            "(SELECT COUNT(*) FROM applications a WHERE a.slug=f.slug) AS n "
            "FROM forms f ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r, data=json.loads(r["data"])) for r in rows]


def save_application(slug, data):
    with _conn() as c:
        c.execute("INSERT INTO applications (slug, created, data) VALUES (?,?,?)",
                  (slug, int(time.time()), json.dumps(data, ensure_ascii=False)))


def list_applications(slug):
    with _conn() as c:
        rows = c.execute("SELECT created, data FROM applications WHERE slug=? ORDER BY created DESC",
                         (slug,)).fetchall()
    return [dict(created=r["created"], **json.loads(r["data"])) for r in rows]
