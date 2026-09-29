"""Aus einer URL oder einem eingefügten Inserat die Eckdaten der Stelle lesen."""

import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126 Safari/537.36"}

PORTALS = ("jobs.ch", "jobup.ch", "indeed.", "linkedin.", "xing.", "jobscout24",
           "jobwinner", "handwerker-job", "stepstone", "monster.", "gastrojob")

LEGAL_FORMS = r"(?:AG|GmbH|SA|Sàrl|Sarl|KLG|KG|Genossenschaft|& Co\.?)"
COMPANY_RE = re.compile(
    rf"\b((?:[A-ZÄÖÜ][\w&\-äöüéè]*\s){{0,4}}[A-ZÄÖÜ][\w&\-äöüéè]*\s{LEGAL_FORMS})(?=\W|$)")
# Betriebe ohne Rechtsform: "Gasthof Ochsen", "Bäckerei Wüthrich", "Garage Frei"
TRADE_RE = re.compile(
    r"\b((?:Gasthof|Gasthaus|Restaurant|Hotel|Bäckerei|Konditorei|Metzgerei|Schreinerei|Malerei|"
    r"Zimmerei|Spenglerei|Garage|Carrosserie|Gärtnerei|Druckerei|Elektro|Sanitär|Holzbau|Metallbau)"
    r"(?:\s[A-ZÄÖÜ][\wäöüéè\-]+){1,2})")

# Häufige Berufsbezeichnungen – dient als Anker für die Titelsuche im Freitext
JOB_WORDS = (
    "schreiner|zimmer(?:mann|frau)|maler|gipser|maurer|elektro\w*|elektriker\w*|"
    "sanitär\w*|heizung\w*|polymechaniker\w*|mechaniker\w*|metallbauer\w*|schlosser\w*|"
    "monteur\w*|installateur\w*|koch|köchin|kellner\w*|servicefachangestellte\w*|"
    "logistiker\w*|chauffeur\w*|lagerist\w*|konstrukteur\w*|automatiker\w*|"
    "spengler\w*|dachdecker\w*|bodenleger\w*|plattenleger\w*|landschaftsgärtner\w*|"
    "gärtner\w*|bäcker\w*|metzger\w*|coiffeu\w*|fachmann\w*|fachfrau\w*|techniker\w*|"
    "projektleiter\w*|bauführer\w*|vorarbeiter\w*|polier\w*|kauffrau|kaufmann\s(?:EFZ|EBA)|"
    "fräser\w*|dreher\w*|schweisser\w*|mitarbeiter(?:in)?|trockenbauer\w*|konditor\w*"
)
TITLE_RE = re.compile(
    rf"(\b(?:[A-ZÄÖÜ][\wäöü]*-)?(?:{JOB_WORDS})\b(?:-[A-ZÄÖÜ][\wäöü]+)?(?:/\w+)?"
    rf"(?:\s(?:Elektro|Hochbau|Tiefbau|Produktion|Haustechnik|Sanitär|Heizung|Logistik|Montage|Service|Lager))?(?:\s(?:EFZ|EBA|HF|FH|FA)\b)?"
    rf"(?:\s?/\s?-?in)?(?:\s\(?[mwd](?:\s?/\s?[mwd]){{1,2}}\)?)?(?:\s\d{{2,3}}(?:\s?[-–]\s?\d{{2,3}})?\s?%)?)",
    re.IGNORECASE)


def _clean(s):
    return re.sub(r"\s+", " ", s or "").strip(" -–|:,.")


def is_public_url(url):
    """Schutz vor SSRF: Das Formular ist öffentlich, also keine internen Adressen abrufen."""
    import ipaddress
    import socket
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        infos = socket.getaddrinfo(p.hostname, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def fetch(url, timeout=8):
    """HTML einer Seite holen. Gibt (html, final_url) oder (None, url) zurück."""
    try:
        for _ in range(4):  # Weiterleitungen selbst folgen, damit jede Station geprüft wird
            if not is_public_url(url):
                return None, url
            r = requests.get(url, headers=UA, timeout=timeout, verify=False, allow_redirects=False)
            if r.is_redirect and r.headers.get("location"):
                url = requests.compat.urljoin(url, r.headers["location"])
                continue
            if r.status_code >= 400:
                return None, url
            r.encoding = r.apparent_encoding or r.encoding
            return r.text, url
    except requests.RequestException:
        pass
    return None, url


def _job_posting_ld(soup):
    """schema.org JobPosting aus JSON-LD lesen (jobs.ch, indeed, viele Firmen-Karriereseiten)."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data])
        for it in items:
            if isinstance(it, dict) and it.get("@type") == "JobPosting":
                org = it.get("hiringOrganization") or {}
                loc = it.get("jobLocation") or {}
                if isinstance(loc, list):
                    loc = loc[0] if loc else {}
                addr = loc.get("address", {}) if isinstance(loc, dict) else {}
                return {
                    "job_title": _clean(it.get("title")),
                    "company_name": _clean(org.get("name") if isinstance(org, dict) else org),
                    "company_url": org.get("sameAs") or org.get("url") if isinstance(org, dict) else None,
                    "location": _clean(addr.get("addressLocality") if isinstance(addr, dict) else ""),
                    "text": BeautifulSoup(it.get("description", ""), "html.parser").get_text(" "),
                }
    return None


def _company_from_title(soup, host):
    for meta in ("og:site_name", "application-name"):
        m = soup.find("meta", property=meta) or soup.find("meta", attrs={"name": meta})
        if m and m.get("content"):
            return _clean(m["content"])
    title = _clean(soup.title.string if soup.title else "")
    if title:
        parts = [p for p in re.split(r"\s[|–—\-·:]\s", title) if p.strip()]
        # Der Teil mit Rechtsform gewinnt, sonst der kürzeste Teil (meist der Firmenname)
        for p in parts:
            if re.search(LEGAL_FORMS, p):
                return _clean(p)
        if parts:
            candidate = min(parts, key=len)
            if 2 < len(candidate) <= 50 and candidate.lower() not in ("home", "startseite", "willkommen"):
                return candidate
    # Fallback: aus der Domain  (elektro-minder.ch -> Elektro Minder)
    name = host.split(".")[-2] if host.count(".") >= 1 else host
    return " ".join(w.capitalize() for w in re.split(r"[-_]", name))


def find_title(text):
    """Bester Treffer: mit Abschluss, Pensum oder (m/w/d) schlägt ein nacktes Berufswort."""
    best, best_score = "", -1
    for m in TITLE_RE.finditer((text or "")[:4000]):
        t = _clean(m.group(1))
        score = 3 * bool(re.search(r"\b(EFZ|EBA|HF|FH|FA)\b", t)) + 2 * ("%" in t) + bool(re.search(r"[mwd]/", t))
        if score > best_score:
            best, best_score = t, score
    return best


def find_company(text):
    m = COMPANY_RE.search(text or "") or TRADE_RE.search(text or "")
    if not m:
        return ""
    name = _clean(m.group(1))
    # "Wir suchen ... bei Firma AG" – Füllwörter vorne abschneiden
    name = re.sub(r"^(?:Die|Der|Das|Bei|Für|Wir|Unser|Unsere)\s+", "", name)
    return name


def parse_input(raw, job_title=None, company_name=None, fetcher=None):
    """Hauptfunktion. Gibt ein dict mit job_title, company_name, company_url, location, text."""
    fetcher = fetcher or fetch
    raw = (raw or "").strip()
    info = {"job_title": "", "company_name": "", "company_url": None, "location": "",
            "text": raw, "source_url": None, "warnings": []}

    url_m = re.search(r"https?://\S+|(?:www\.)[\w\-.]+\.[a-z]{2,}\S*", raw)
    if url_m:
        url = url_m.group(0).rstrip(").,")
        if not url.startswith("http"):
            url = "https://" + url
        info["source_url"] = url
        host = urlparse(url).netloc.lower().removeprefix("www.")
        is_portal = any(p in host for p in PORTALS)
        if not is_portal:
            info["company_url"] = f"https://{urlparse(url).netloc}"

        html, final = fetcher(url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            ld = _job_posting_ld(soup)
            if ld:
                for k in ("job_title", "company_name", "location"):
                    info[k] = info[k] or ld[k]
                if ld.get("company_url") and not info["company_url"]:
                    info["company_url"] = ld["company_url"]
                info["text"] += "\n" + ld["text"]
            else:
                for s in soup(["script", "style", "noscript"]):
                    s.decompose()
                h1 = soup.find("h1")
                h1_title = find_title(h1.get_text(" ")) if h1 else ""
                is_subpage = urlparse(final).path.strip("/") != ""
                if is_portal or is_subpage:
                    # Inserats- oder Karriereseite: Überschrift und Text gehören zur Stelle
                    info["job_title"] = info["job_title"] or h1_title or (_clean(h1.get_text()) if is_portal and h1 else "")
                    info["text"] += "\n" + soup.get_text(" ")[:6000]
                else:
                    # Startseite: Werbetext ("Ihr Elektriker in Zürich") ist keine offene Stelle
                    info["page_text"] = soup.get_text(" ")[:6000]
                if not is_portal:
                    info["company_name"] = info["company_name"] or _company_from_title(soup, host)
        else:
            info["warnings"].append("Seite konnte nicht geladen werden")
            if not is_portal:
                info["company_name"] = _company_from_title(BeautifulSoup("", "html.parser"), host)

    # URLs selbst nicht auswerten: "elektro-minder.ch" ist keine Stellenbezeichnung
    text = re.sub(r"https?://\S+|www\.\S+", " ", info["text"])
    info["company_name"] = info["company_name"] or find_company(text)
    info["job_title"] = info["job_title"] or find_title(text)

    if job_title:
        info["job_title"] = _clean(job_title)
    if company_name:
        info["company_name"] = _clean(company_name)

    if not info["job_title"]:
        info["job_title"] = "Fachkraft"
        info["warnings"].append("Stelle nicht erkannt")
    if not info["company_name"]:
        info["company_name"] = "Ihr Betrieb"
        info["warnings"].append("Firma nicht erkannt")
    return info
