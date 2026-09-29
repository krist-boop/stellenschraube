"""JPG der Kundenseite im Handyrahmen (für LinkedIn, Brief/Postkarte oder die zweite Mail).

Braucht Playwright: `pip install playwright` und entweder Google Chrome auf dem Rechner
oder einmalig `playwright install chromium` (auf dem VPS).
"""

import base64
import os

from . import store

OUT_DIR = os.path.join(os.path.dirname(store.DB_PATH), "vorschau-bilder")

FRAME = """<!DOCTYPE html><html><head><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:1080px;height:1350px;background:{bg};display:flex;align-items:center;justify-content:center;
     font-family:Arial,Helvetica,sans-serif}}
.phone{{width:470px;height:1010px;background:#0A0A08;border-radius:64px;padding:16px;
        box-shadow:0 40px 80px rgba(0,0,0,.25)}}
.screen{{width:100%;height:100%;border-radius:50px;overflow:hidden;background:#fff}}
.screen img{{width:100%;display:block}}
</style></head><body><div class="phone"><div class="screen"><img src="data:image/png;base64,{img}"></div></div></body></html>"""


def _launch(p):
    channel = os.getenv("PLAYWRIGHT_CHANNEL", "chrome")
    try:
        return p.chromium.launch(channel=channel or None, headless=True)
    except Exception:
        return p.chromium.launch(headless=True)  # mitgeliefertes Chromium (playwright install chromium)


def render_jpg(url, slug):
    from playwright.sync_api import sync_playwright
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{slug}.jpg")
    with sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)
        page.goto(url, wait_until="networkidle")
        png = page.screenshot()
        frame = browser.new_page(viewport={"width": 1080, "height": 1350})
        accent = (store.get(slug) or {}).get("data", {}).get("brand", {}).get("accent", "#DC2626")
        frame.set_content(FRAME.format(img=base64.b64encode(png).decode(), bg=accent + "22"))
        frame.screenshot(path=path, type="jpeg", quality=85)
        browser.close()
    return path
