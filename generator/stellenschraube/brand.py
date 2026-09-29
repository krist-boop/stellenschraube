"""Hauptfarbe und Logo einer Firmenwebsite bestimmen."""

import colorsys
import re
from collections import Counter
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import extract

FALLBACK_ACCENT = "#DC2626"  # stellenschraube-Rot, falls nichts Brauchbares gefunden wird
HEX_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
VAR_RE = re.compile(r"--[\w-]*(?:primary|brand|accent|main|theme)[\w-]*\s*:\s*(#[0-9a-fA-F]{3,6})\b", re.I)


def _norm(h):
    h = h.lstrip("#").lower()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h


def _hls(h):
    h = _norm(h)[1:]
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)


def usable(h):
    """Farbe muss gesättigt und weder fast weiss noch fast schwarz sein."""
    _, l, s = _hls(h)
    return s > 0.35 and 0.18 < l < 0.72


def luminance(h):
    h = _norm(h)[1:]
    def lin(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(h[i:i + 2]) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def on_color(h):
    """Schwarz oder Weiss – je nachdem, was auf dieser Farbe den höheren Kontrast hat."""
    return "#0A0A08" if contrast(h, "#0A0A08") >= contrast(h, "#FFFFFF") else "#FFFFFF"


def pick_accent(css_chunks, theme_color=None):
    for chunk in css_chunks:
        m = VAR_RE.search(chunk)
        if m and usable(m.group(1)):
            return _norm(m.group(1)), "css-variable"
    if theme_color and HEX_RE.fullmatch(theme_color.strip()) and usable(theme_color.strip()):
        return _norm(theme_color.strip()), "theme-color"
    counts = Counter(_norm(m.group(0)) for chunk in css_chunks for m in HEX_RE.finditer(chunk))
    for color, _ in counts.most_common():
        if usable(color):
            return color, "häufigste Farbe"
    return FALLBACK_ACCENT, "fallback"


def scrape_brand(company_url, fetcher=None):
    fetcher = fetcher or extract.fetch
    brand = {"accent": FALLBACK_ACCENT, "accent_source": "fallback", "logo_url": None}
    if not company_url:
        return brand
    html, final = fetcher(company_url)
    if not html:
        return brand
    soup = BeautifulSoup(html, "html.parser")

    chunks = [s.string or "" for s in soup.find_all("style")]
    chunks += [t.get("style", "") for t in soup.find_all(style=True)][:200]
    for link in soup.find_all("link", rel="stylesheet")[:3]:
        href = link.get("href")
        if href and "fonts.googleapis" not in href:
            css, _ = fetcher(urljoin(final, href), timeout=5)
            if css:
                chunks.append(css[:300_000])

    tc = soup.find("meta", attrs={"name": "theme-color"})
    brand["accent"], brand["accent_source"] = pick_accent(chunks, tc.get("content") if tc else None)

    for img in soup.find_all("img"):
        hay = " ".join([img.get("alt", ""), " ".join(img.get("class", [])), img.get("src", ""), img.get("id", "")]).lower()
        src = img.get("src") or img.get("data-src")
        if src and "logo" in hay and not src.startswith("data:"):
            brand["logo_url"] = urljoin(final, src)
            break
    return brand
