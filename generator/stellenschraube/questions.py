"""Fragen für das Bewerbungsformular. Mit ANTHROPIC_API_KEY von Claude, sonst aus Branchenvorlagen.

Leitlinie: jede Frage in einem Tipp beantwortbar, aber jede Antwort muss dem Betrieb etwas sagen,
das er vor dem ersten Anruf wissen will. Aufbau (5 Fragen):
  1. Abschluss                         – leichter Einstieg
  2. Erfahrung                         – Einstufung
  3. Was schon selbständig gemacht     – Mehrfachauswahl, konkrete Arbeiten aus Branche/Inserat
  4. Harte Anforderung oder Arbeitsweg – Ausschlusskriterium
  5. Aktuelle Situation                – wie schnell verfügbar, wie wechselbereit
"""

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

# Frage 3: konkrete Arbeiten als (Antwort, Stichwörter). Arbeiten, die im Inserat vorkommen, rücken nach vorne.
TASKS = {
    "gastro": [("À-la-carte allein gekocht", ["à la carte", "a la carte"]), ("Einen Posten geführt", ["posten", "chef de partie"]),
               ("Menüs und Einkauf geplant", ["menü", "einkauf", "kalkulation"]), ("Bankette ab 50 Personen", ["bankett", "anlass", "catering"]),
               ("Lernende angeleitet", ["lernende", "ausbildung"])],
    "sanitaer": [("Installationen im Neubau", ["neubau"]), ("Badumbau von A bis Z", ["umbau", "renovation", "sanierung"]),
                 ("Service und Störungen", ["service", "störung", "unterhalt", "wartung"]), ("Wärmepumpen installiert", ["wärmepumpe", "heizung"]),
                 ("Baustelle selbst geführt", ["selbständig", "selbstständig", "baustellenleitung"])],
    "elektro": [("Installationen im Neubau", ["neubau", "wohnbau"]), ("Umbau und Sanierung", ["umbau", "sanierung", "renovation"]),
                ("Störungen gesucht und behoben", ["störung", "service", "pikett"]), ("Photovoltaik montiert", ["photovoltaik", "solar"]),
                ("Messungen / Sicherheitsnachweis", ["sina", "sicherheitsnachweis", "messung"])],
    "holz": [("Möbel nach Plan gefertigt", ["möbel", "innenausbau", "werkstatt"]), ("Montage beim Kunden allein", ["montage", "kunde"]),
             ("CNC programmiert", ["cnc"]), ("Fenster und Türen eingebaut", ["fenster", "türen"]),
             ("Aufmass beim Kunden", ["aufmass", "ausmessen"])],
    "metall": [("CNC programmiert", ["programm"]), ("CNC eingerichtet und bedient", ["cnc", "einricht"]),
               ("Konventionell gedreht / gefräst", ["konventionell", "drehen", "fräsen"]), ("Geschweisst (MIG/MAG/WIG)", ["schweiss", "wig"]),
               ("Nach Zeichnung montiert", ["montage", "zeichnung"])],
    "maler": [("Innenräume gestrichen", ["innen"]), ("Fassaden gemacht", ["fassade", "aussen"]), ("Tapeziert", ["tapez"]),
              ("Spachtel- und Dekortechniken", ["spachtel", "dekor", "abrieb"]), ("Kleine Baustellen allein geleitet", ["selbständig", "selbstständig"])],
    "bau": [("Mauerwerk erstellt", ["mauer", "backstein"]), ("Schalung und Beton", ["schalung", "beton"]),
            ("Pläne gelesen und abgesteckt", ["plan", "pläne", "abstecken"]), ("Umbau und Sanierung", ["umbau", "sanierung"]),
            ("Eine Gruppe geführt", ["gruppe", "vorarbeiter", "polier"])],
    "logistik": [("Kat. C / CE gefahren", ["kat. c", "lastwagen", "lkw"]), ("Stapler gefahren", ["stapler"]),
                 ("Mit Scanner kommissioniert", ["kommission", "scanner"]), ("Touren selbst geplant", ["tour", "disposition"]),
                 ("Kranausweis", ["kran"])],
    "default": [("Aufträge allein erledigt", ["selbständig", "selbstständig"]), ("Direkt mit Kunden gearbeitet", ["kunde"]),
                ("Nach Plänen gearbeitet", ["plan", "zeichnung"]), ("Maschinen bedient", ["maschine"]),
                ("Andere angeleitet", ["führung", "lernende"])],
}

# Frage 4: harte Anforderungen aus dem Inserat, nach Wichtigkeit, mit abgestuften Antworten.
REQUIREMENTS = [
    ("fuehrerschein", r"f(?:ü|ue)hrer(?:schein|ausweis)|\bkat\.?\s?b\b",
     {"eyebrow": "Führerausweis", "question": "Hast du den Führerausweis Kat. B?",
      "options": ["Ja, mit eigenem Auto", "Ja, ohne eigenes Auto", "Mache ihn gerade", "Nein"]}),
    ("pikett", r"pikett|bereitschaft",
     {"eyebrow": "Pikett", "question": "Wie oft könntest du Pikett machen?",
      "options": ["Regelmässig, kein Problem", "Etwa jede 4. Woche", "Nur im Notfall", "Gar nicht"]}),
    ("schicht", r"schicht",
     {"eyebrow": "Schicht", "question": "Welche Schichten gehen bei dir?",
      "options": ["Alle, auch Nacht", "Früh- und Spätschicht", "Nur Tagschicht", "Keine Schichtarbeit"]}),
    ("wochenende", r"wochenend|abenddienst|zimmerstunde|teildienst",
     {"eyebrow": "Arbeitszeiten", "question": "Wie passen Abend- und Wochenenddienste?",
      "options": ["Passt immer", "Jedes 2. Wochenende", "Nur unter der Woche", "Gar nicht"]}),
]

SITUATION_Q = {"eyebrow": "Situation", "question": "Wie sieht es bei dir gerade aus?",
               "options": ["Kann sofort anfangen", "Gekündigt, bald frei", "Angestellt, 1–3 Mt. Kündigung",
                           "Angestellt, schaue mich nur um"]}


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


def task_question(branch, text):
    t = (text or "").lower()
    ranked = sorted(TASKS[branch], key=lambda x: not any(k in t for k in x[1]))  # stabil: Treffer zuerst
    return {"eyebrow": "Können", "question": "Was hast du schon selbständig gemacht?",
            "hint": "Mehrere Antworten möglich", "multi": True, "options": [a for a, _ in ranked]}


def requirement_question(text, branch, location=""):
    t = (text or "").lower()
    for key, pattern, q in REQUIREMENTS:
        if key == "fuehrerschein" and branch == "logistik":
            continue  # dort fragt schon Frage 3 nach Kat. C
        if re.search(pattern, t):
            return key, q
    m = re.search(r"\b(\d{2,3})\s?(?:[-–]|bis)\s?(\d{2,3})\s?%", t)
    if m and int(m.group(1)) < int(m.group(2)) <= 100:
        lo, hi = int(m.group(1)), int(m.group(2))
        mid = (lo + hi) // 2 // 10 * 10
        opts = [f"{hi}%", f"{mid}%" if lo < mid < hi else f"{lo}–{hi}%", f"{lo}%", f"Weniger als {lo}%"]
        return "pensum", {"eyebrow": "Pensum", "question": "Welches Pensum möchtest du arbeiten?",
                          "options": list(dict.fromkeys(opts))}
    ziel = f"nach {location}" if location else "zu uns"
    return "arbeitsweg", {"eyebrow": "Arbeitsweg", "question": f"Wie lange wäre dein Arbeitsweg {ziel}?",
                          "options": ["Unter 20 Minuten", "20 bis 40 Minuten", "Über 40 Minuten", "Würde umziehen"]}


def template_questions(job_title, text, location=""):
    branch = detect_branch(text, title=job_title)
    base = _base_title(job_title)
    if re.search(r"\b(EFZ|EBA)\b", base):
        q1 = {"eyebrow": "Abschluss", "question": f"Hast du einen Abschluss als {base}?",
              "options": ["Ja, EFZ", "Ja, Abschluss im Ausland", "Nein, aber angelernt", "Bin noch in der Lehre"]}
    else:
        q1 = {"eyebrow": "Abschluss", "question": "Welche Ausbildung hast du in diesem Beruf?",
              "options": ["Lehre (EFZ / EBA)", "Abschluss im Ausland", "Angelernt", "Weiterbildung (HF, FA)"]}
    return branch, [
        q1,
        {"eyebrow": "Erfahrung", "question": "Wie viele Jahre Berufserfahrung hast du?",
         "options": ["Weniger als 2", "2 bis 5", "5 bis 10", "Mehr als 10"]},
        task_question(branch, f"{job_title} {text}"),
        requirement_question(f"{job_title} {text}", branch, location)[1],
        SITUATION_Q,
    ]


FORBIDDEN = re.compile(
    r"\b(alter|wie alt|jahrgang|woher|muttersprache|geboren|nationalit|herkunft|religi|schwanger|kinder|"
    r"familie|verheiratet|gesundheit|krank|behinder|lohn|gehalt|salär|lohnvorstellung|aufenthalt|bewilligung)", re.I)


def check_questions(qs):
    """Liste von Problemen. Leer = Fragen sind brauchbar."""
    issues = []
    if not 4 <= len(qs) <= 6:
        issues.append(f"{len(qs)} Fragen statt 5")
    seen = set()
    for i, q in enumerate(qs, 1):
        text, opts = q.get("question", ""), q.get("options", [])
        max_opts = 6 if q.get("multi") else 4
        if not text.endswith("?"):
            issues.append(f"Frage {i} endet nicht mit ?")
        if len(text) > 70:
            issues.append(f"Frage {i} zu lang ({len(text)} Zeichen)")
        if not 2 <= len(opts) <= max_opts or len(set(o.lower() for o in opts)) != len(opts):
            issues.append(f"Frage {i}: Optionen fehlen, zu viele oder doppelt")
        if any(len(o) > 34 for o in opts):
            issues.append(f"Frage {i}: Option zu lang")
        if len(opts) <= 2 and not q.get("multi"):
            issues.append(f"Frage {i}: nur zwei Antworten, zu wenig Aussagekraft")
        if "ß" in text + "".join(opts):
            issues.append(f"Frage {i}: ß statt ss")
        hit = FORBIDDEN.search(text + " " + " ".join(opts))
        if hit:
            issues.append(f"Frage {i}: heikles Thema ({hit.group(0)})")
        if text.lower() in seen:
            issues.append(f"Frage {i} doppelt")
        seen.add(text.lower())
    return issues


PROMPT = """Du erstellst ein kurzes Handy-Bewerbungsformular für einen Schweizer Handwerksbetrieb.
Die Bewerber sind Fachleute, die gerade NICHT aktiv suchen und das Formular über Instagram öffnen.
Jede Frage muss mit einem Tipp beantwortbar sein. Gleichzeitig soll der Betrieb nach den 5 Antworten
wissen, ob sich ein Anruf lohnt und worüber er im Gespräch reden kann.

Stelle: {job_title}
Betrieb: {company_name}
Ort: {location}
Inserat (Auszug):
{text}

Gib GENAU 5 Fragen zurück, als JSON-Liste ohne weiteren Text:
[{{"eyebrow": "1-2 Wörter", "question": "...?", "options": ["..."], "multi": false}}]

Aufbau:
1. Abschluss (z.B. "Hast du einen Abschluss als Polymechaniker EFZ?"), 4 Optionen
2. Berufserfahrung in Jahren, 4 Optionen
3. "Was hast du schon selbständig gemacht?" – multi: true, 5 KONKRETE Arbeiten aus diesem Inserat
   (Maschinen, Arbeitsschritte, Objekte). Nicht "Teamfähigkeit", sondern z.B. "Wärmepumpen installiert".
4. Die wichtigste harte Anforderung aus dem Inserat (Führerausweis, Pikett, Schicht, Pensum,
   Wochenenddienst) mit abgestuften Antworten; wenn keine genannt: Arbeitsweg in Minuten.
5. Aktuelle Situation / Verfügbarkeit (sofort frei, gekündigt, Kündigungsfrist, schaue mich nur um)

Regeln:
- Du-Form, Schweizer Hochdeutsch, "ss" statt "ß", Begriffe aus dem Schweizer Handwerk (EFZ, Pikett, Baustelle)
- Frage max. 60 Zeichen, Optionen je max. 32 Zeichen
- Einzelauswahl: genau 4 Optionen, abgestuft von stark nach schwach, keine blossen Ja/Nein-Paare
- VERBOTEN (Diskriminierung / Datenschutz): Alter, Herkunft, Nationalität, Aufenthaltsbewilligung,
  Religion, Familie, Kinder, Gesundheit, Lohn
- Nichts erfinden, was nicht zur Stelle passt"""


def claude_questions(job_title, company_name, text, api_key, location=""):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"),
        max_tokens=1200,
        messages=[{"role": "user", "content": PROMPT.format(
            job_title=job_title, company_name=company_name, location=location or "unbekannt", text=text[:3000])}],
    )
    raw = msg.content[0].text
    data = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
    out = []
    for q in data[:5]:
        multi = bool(q.get("multi"))
        opts = [str(o).replace("ß", "ss")[:40] for o in q.get("options", [])][:6 if multi else 4]
        if q.get("question") and len(opts) >= 2:
            item = {"eyebrow": str(q.get("eyebrow", ""))[:24],
                    "question": str(q["question"]).replace("ß", "ss")[:90], "options": opts}
            if multi:
                item.update(multi=True, hint="Mehrere Antworten möglich")
            out.append(item)
    issues = check_questions(out)
    if issues:
        raise ValueError("Qualitätsprüfung: " + "; ".join(issues))
    return out


def get_questions(job_title, company_name, text, location=""):
    branch, qs = template_questions(job_title, text, location)
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if key and not key.startswith("sk-ant-..."):
        try:
            return branch, claude_questions(job_title, company_name, text, key, location), "claude"
        except Exception as e:  # Fallback ist bewusst: lieber Vorlage als kein Formular
            print(f"[claude] {e} – verwende Vorlage")
    return branch, qs, "vorlage"
