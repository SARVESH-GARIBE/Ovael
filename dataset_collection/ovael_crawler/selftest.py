"""Offline self-test of the instrumentation and DOM iframe measurements.

A page with a known, fixed number of API calls is served by Playwright's route.fulfill (no
network access) and the counters read back are compared with the expected values."""

from __future__ import annotations

import asyncio

from playwright.async_api import async_playwright

from .config import CrawlConfig
from .crawler import DOM_IFRAMES_JS, Crawler

PAGE = """<!doctype html><html><head><title>selftest</title></head><body>
<iframe id="hidden1" srcdoc="<p>x</p>" style="display:none"></iframe>
<iframe id="tiny" srcdoc="<p>x</p>" width="1" height="1"></iframe>
<iframe id="visible" srcdoc="<p>x</p>" width="300" height="150"></iframe>
<script>
const c = document.createElement('canvas'); c.width = 200; c.height = 50;
const x = c.getContext('2d'); x.fillText('abc', 2, 10); x.measureText('abc');
c.toDataURL(); x.getImageData(0, 0, 10, 10);
const g = document.createElement('canvas').getContext('webgl');
if (g) { g.getParameter(37445); g.getParameter(37446); g.getSupportedExtensions(); g.getExtension('WEBGL_debug_renderer_info'); }
const oac = new OfflineAudioContext(1, 44100, 44100); oac.createOscillator(); oac.createDynamicsCompressor();
localStorage.setItem('k', 'v'); localStorage.getItem('k'); localStorage.removeItem('k');
sessionStorage.setItem('k', 'v');
document.cookie = 'a=b'; document.cookie;
indexedDB.open('t'); document.fonts.check('12px Arial');
</script></body></html>"""

EXPECTED = {
    "canvas.getContext.2d": 1, "canvas.fillText": 1, "canvas.measureText": 1, "canvas.toDataURL": 1,
    "canvas.getImageData": 1, "canvas.getContext.webgl": 1, "webgl.getParameter": 2,
    "webgl.unmaskedInfoQuery": 2, "webgl.getSupportedExtensions": 1, "webgl.getExtension": 1,
    "OfflineAudioContext()": 1, "audio.createOscillator": 1, "audio.createDynamicsCompressor": 1,
    "storage.localStorage.write": 2, "storage.localStorage.read": 1, "storage.sessionStorage.write": 1,
    "document.cookie.write": 1, "document.cookie.read": 1, "storageapi.indexedDB.open": 1, "other.fonts.check": 1,
}


async def _run() -> dict:
    cr = Crawler(CrawlConfig(), ref=None, store=None)
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        ctx = await b.new_context()
        await ctx.add_init_script(script=cr.instr_src)
        await ctx.route("https://ovael-selftest.invalid/**",
                        lambda r: r.fulfill(status=200, content_type="text/html", body=PAGE))
        page = await ctx.new_page()
        await page.goto("https://ovael-selftest.invalid/")
        await asyncio.sleep(0.5)
        snap = await page.evaluate(f"() => window['{cr.key}']()")
        dom = await page.evaluate(DOM_IFRAMES_JS)
        await b.close()
    counts = snap["counts"]
    mismatches = {k: (v, counts.get(k, 0)) for k, v in EXPECTED.items() if counts.get(k, 0) != v}
    hidden = sum(el["hidden"] for el in dom)
    return {"ok": not mismatches and hidden == 2 and len(dom) == 3 and not snap["failed"],
            "mismatches_expected_vs_observed": mismatches, "dom_iframes": len(dom), "hidden_iframes": hidden,
            "hooked_apis": len(snap["hooked"]), "unavailable_apis": snap["failed"], "counts": counts}


def run_selftest() -> bool:
    res = asyncio.run(_run())
    print("\nInstrumentation self-test (offline page with known API calls):")
    print(f"  hooked APIs: {res['hooked_apis']}, unavailable: {res['unavailable_apis']}")
    print(f"  DOM iframes: {res['dom_iframes']} (expected 3), hidden: {res['hidden_iframes']} (expected 2)")
    print(f"  counter mismatches (expected, observed): {res['mismatches_expected_vs_observed'] or 'none'}")
    print("  RESULT:", "PASS" if res["ok"] else "FAIL")
    return res["ok"]
