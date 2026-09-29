"""Fragen für das Bewerbungsformular. Mit ANTHROPIC_API_KEY von Claude, sonst aus Branchenvorlagen."""

import json
import os
import re

# Reihenfolge zählt: spezifische Branchen vor allgemeinen
BRANCHES = [
    ("gastro", ["koch", "köchin", "küche", "restaurant", "servicefach", "kellner", "gastro", "hotel", "bäcker", "konditor", "metzger"]),
    ("sanitaer", ["sanitär", "sanitaer", "heizung", "lüftung", "klima", "haustechnik", "spengler"]),
    ("elektro", ["elektro", "elektriker", "automatiker", "montage-elektriker", "telematiker"]),
    ("holz", ["schreiner", "zimmer", "holzbau", "möbel", "innenausbau", "parkett"]),
    ("metall", ["polymechaniker", "mechaniker", "metallbau", "schlosser", "schweiss", "cnc", "konstrukteur"]),
    ("maler", ["maler", "gipser", "stuckateur", "fassade"]),
    ("bau", ["maurer", "bau", "polier", "vorarbeiter", "strassenbau", "dachdecker", "plattenleger", "gärtner"]),
    ("logistik", ["logistik", "lager", "chauffeur", "fahrer", "transport", "kommission"]),
]

# Frage 3 prüft Können, nicht Vorlieben: Selbständigkeit ist im Handwerk das stärkste Filterkriterium.
SPECIFIC = {
    "gastro": ("Wie selbständig arbeitest du in der Küche?",
               ["Führe schon ein Team", "Führe einen Posten allein", "Arbeite mit Anleitung", "Bin neu in der Küche"]),
    "sanitaer": ("Was machst du schon ganz allein?",
                 ["Ganze Baustellen", "Service beim Kunden", "Arbeite mit Vorarbeiter", "Noch mit Anleitung"]),
    "elektro": ("Was machst du schon ganz allein?",
                ["Ganze Objekte installieren", "Service und Störungen", "Arbeite mit Chefmonteur", "Noch mit Anleitung"]),
    "holz": ("Was machst du schon ganz allein?",
             ["Werkstatt und Montage", "Nur Montage", "Nur Werkstatt", "Noch mit Anleitung"]),
    "metall": ("Welche Maschinen beherrschst du?",
               ["CNC programmieren", "CNC bedienen", "Konventionell", "Schweissen und Montage"]),
    "maler": ("Wie selbständig arbeitest du auf der Baustelle?",
              ["Leite Baustellen allein", "Arbeite selbständig", "Arbeite mit Vorarbeiter", "Noch mit Anleitung"]),
    "bau": ("Wie selbständig arbeitest du auf der Baustelle?",
            ["Führe eine Gruppe", "Arbeite selbständig", "Arbeite im Team mit", "Noch mit Anleitung"]),
    "logistik": ("Welchen Führerausweis hast du?",
                 ["Kat. C / CE", "Kat. C1", "Nur Kat. B", "Keinen"]),
    "default": ("Wie selbständig arbeitest du?",
                ["Leite Aufträge allein", "Arbeite selbständig", "Arbeite im Team mit", "Noch mit Anleitung"]),
}

# Harte Anforderungen aus dem Inserat, nach Wichtigkeit. Die erste gefundene wird Frage 4.
REQUIREMENTS = [
    ("fuehrerschein", r"f(?:ü|ue)hrer(?:schein|ausweis)|\bkat\.?\s?b\b",
     {"eyebrow": "Führerausweis", "question": "Hast du den Führerausweis Kat. B?",
      "options": ["Ja, mit eigenem Auto", "Ja, ohne Auto", "Bin dran", "Nein"]}),
    ("pikett", r"pikett|bereitschaft",
     {"eyebrow": "Pikett", "question": "Bist du bereit für Pikett-Einsätze?",
      "options": ["Ja, kein Problem", "Ab und zu", "Lieber nicht", "Nein"]}),
    ("schicht", r"schicht",
     {"eyebrow": "Schicht", "question": "Kannst du im Schichtbetrieb arbeiten?",
      "options": ["Ja", "Nur Früh und Spät", "Nur Tagschicht", "Nein"]}),
    ("wochenende", r"wochenend|abenddienst|zimmerstunde|teildienst",
     {"eyebrow": "Arbeitszeiten", "question": "Passen Abend- und Wochenenddienste für dich?",
      "options": ["Ja", "Teilweise", "Nur unter der Woche", "Nein"]}),
]

START_Q = {"eyebrow": "Start", "question": "Ab wann könntest du starten?",
           "options": ["Sofort", "Innert 1 Monat", "Innert 3 Monaten", "Später / offen"]}


def requirement_question(text, branch):
    t = (text or "").lower()
    for key, pattern, q in REQUIREMENTS:
        if key == "fuehrerschein" and branch == "logistik":
            continue  # dort fragt schon Frage 3 nach dem Ausweis
        if re.search(pattern, t):
            return key, q
    m = re.search(r"\b(\d{2,3})\s?(?:[-–]|bis)\s?(\d{2,3})\s?%", t)
    if m and int(m.group(1)) < int(m.group(2)) <= 100:
        lo, hi = int(m.group(1)), int(m.group(2))
        mid = (lo + hi) // 2 // 10 * 10
        opts = [f"{hi}%", f"{mid}%" if lo < mid < hi else f"{lo}–{hi}%", f"{lo}%", f"Weniger als {lo}%"]
        return "pensum", {"eyebrow": "Pensum", "question": "Welches Pensum passt für dich?",
                          "options": list(dict.fromkeys(opts))}
    return "start", START_Q


FORBIDDEN = re.compile(
    r"\b(alter|wie alt|jahrgang|woher|muttersprache|geboren|nationalit|herkunft|religi|schwanger|kinder|familie|verheiratet|"
    r"gesundheit|krank|behinder|lohn|gehalt|salär|lohnvorstellung|aufenthalt|bewilligung)", re.I)


def check_questions(qs):
    """Liste von Problemen. Leer = Fragen sind brauchbar."""
    issues = []
    if not 3 <= len(qs) <= 5:
        issues.append(f"{len(qs)} Fragen statt 4")
    seen = set()
    for i, q in enumerate(qs, 1):
        text, opts = q.get("question", ""), q.get("options", [])
        if not text.endswith("?"):
            issues.append(f"Frage {i} endet nicht mit ?")
        if len(text) > 70:
            issues.append(f"Frage {i} zu lang ({len(text)} Zeichen)")
        if not 2 <= len(opts) <= 4 or len(set(o.lower() for o in opts)) != len(opts):
            issues.append(f"Frage {i}: Optionen fehlen oder doppelt")
        if any(len(o) > 32 for o in opts):
            issues.append(f"Frage {i}: Option zu lang")
        if "ß" in text + "".join(opts):
            issues.append(f"Frage {i}: ß statt ss")
        if FORBIDDEN.search(text + " " + " ".join(opts)):
            issues.append(f"Frage {i}: heikles Thema ({FORBIDDEN.search(text + ' ' + ' '.join(opts)).group(0)})")
        if text.lower() in seen:
            issues.append(f"Frage {i} doppelt")
        seen.add(text.lower())
    return issues


def detect_branch(text, title=""):
    """Stellenbezeichnung zuerst – der Inseratstext enthält oft Wörter anderer Branchen."""
    for t in ((title or "").lower(), (text or "").lower()):
        for key, words in BRANCHES:
            if any(w in t for w in words):
                return key
    return "default"


def _base_title(job_title):
    """"Sanitärinstallateur EFZ 100% (m/w/d)" -> "Sanitärinstallateur EFZ" """
    t = re.sub(r"\(?\b[mwd](?:\s?/\s?[mwd]){1,2}\)?", "", job_title, flags=re.I)
    t = re.sub(r"\d{2,3}\s?(?:[-–]\s?\d{2,3})?\s?%", "", t)
    return re.sub(r"\s+", " ", t).strip(" -/,") or job_title


def template_questions(job_title, text):
    branch = detect_branch(text, title=job_title)
    base = _base_title(job_title)
    has_efz = bool(re.search(r"\b(EFZ|EBA)\b", base))
    q_spec, o_spec = SPECIFIC[branch]
    q1 = (f"Hast du einen Abschluss als {base}?" if has_efz
          else f"Hast du eine Ausbildung in diesem Bereich?")
    return branch, [
        {"eyebrow": "Ausbildung", "question": q1,
         "options": ["Ja", "Ja, im Ausland", "Nein, aber Erfahrung", "Bin noch in der Lehre"]},
        {"eyebrow": "Erfahrung", "question": "Wie viele Jahre arbeitest du schon im Beruf?",
         "options": ["Unter 1 Jahr", "1 bis 3 Jahre", "3 bis 8 Jahre", "Über 8 Jahre"]},
        {"eyebrow": "Können", "question": q_spec, "options": o_spec},
        requirement_question(f"{job_title} {text}", branch)[1],
    ]


PROMPT = """Du erstellst ein kurzes Handy-Bewerbungsformular für einen Schweizer Handwerksbetrieb.
Ziel: Der Betrieb soll nach 4 Antworten wissen, ob sich ein Anruf lohnt. Die Bewerber sind
Fachleute, die gerade NICHT aktiv suchen und das Formular auf Instagram antippen. Jede Frage muss
in 2 Sekunden mit einem Tipp beantwortbar sein.

Stelle: {job_title}
Betrieb: {company_name}
Inserat (Auszug):
{text}

Gib GENAU 4 Fragen zurück, als JSON-Liste ohne weiteren Text:
[{{"eyebrow": "1-2 Wörter", "question": "...?", "options": ["...", "...", "...", "..."]}}]

Aufbau:
1. Abschluss (z.B. "Hast du einen Abschluss als Polymechaniker EFZ?") – leichter Einstieg
2. Berufserfahrung in Jahren
3. Konkretes Können aus dem Inserat, das Gute von Anfängern trennt (Selbständigkeit,
   bestimmte Maschinen, Arbeiten, die im Inserat genannt sind). KEINE Vorlieben wie "am liebsten".
4. Die wichtigste harte Anforderung aus dem Inserat (Führerausweis, Pikett, Schicht, Pensum,
   Wochenenddienst). Wenn keine genannt ist: Starttermin.

Regeln:
- Du-Form, Schweizer Hochdeutsch, "ss" statt "ß", Begriffe wie im Schweizer Handwerk (EFZ, Pikett, Baustelle)
- Frage max. 60 Zeichen, genau 4 Optionen, je max. 28 Zeichen, von stark nach schwach sortiert
- Optionen schliessen sich gegenseitig aus; die letzte ist die schwächste ehrliche Antwort (z.B. "Noch mit Anleitung")
- VERBOTEN (Diskriminierung / Datenschutz): Alter, Herkunft, Nationalität, Aufenthaltsbewilligung,
  Religion, Familie, Kinder, Gesundheit, Lohn
- Nichts erfinden, was nicht zur Stelle passt"""


def claude_questions(job_title, company_name, text, api_key):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"),
        max_tokens=900,
        messages=[{"role": "user", "content": PROMPT.format(
            job_title=job_title, company_name=company_name, text=text[:3000])}],
    )
    raw = msg.content[0].text
    data = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
    out = []
    for q in data[:4]:
        opts = [str(o).replace("ß", "ss")[:40] for o in q.get("options", [])][:4]
        if q.get("question") and len(opts) >= 2:
            out.append({"eyebrow": str(q.get("eyebrow", ""))[:24],
                        "question": str(q["question"]).replace("ß", "ss")[:90],
                        "options": opts})
    issues = check_questions(out)
    if issues:
        raise ValueError("Qualitätsprüfung: " + "; ".join(issues))
    return out


def get_questions(job_title, company_name, text):
    branch, qs = template_questions(job_title, text)
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if key and not key.startswith("sk-ant-..."):
        try:
            return branch, claude_questions(job_title, company_name, text, key), "claude"
        except Exception as e:  # Fallback ist bewusst: lieber Vorlage als kein Formular
            print(f"[claude] {e} – verwende Vorlage")
    return branch, qs, "vorlage"
