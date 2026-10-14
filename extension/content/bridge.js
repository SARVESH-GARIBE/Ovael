// Isolated-world half of the instrumentation. instrument.js (page world) posts count snapshots to
// this frame's window; this script forwards them to the background worker, and answers the
// worker's request for top-document DOM statistics (the same ones the crawler reads).
(() => {
  'use strict';

  window.addEventListener('message', (e) => {
    if (e.source !== window || !e.data || e.data.__ovaelExt !== 1) return;
    const snap = e.data.snap;
    if (!snap || typeof snap.doc_id !== 'string') return;
    try {
      chrome.runtime.sendMessage({ type: 'instr', snap: { doc_id: snap.doc_id, counts: snap.counts } });
    } catch {
      /* extension reloaded: this page keeps the old script until it is reloaded */
    }
  });

  if (window.top !== window) return;

  // Same definitions as DOM_STATS_JS and DOM_IFRAMES_JS in the crawler.
  function domStats() {
    const iframes = Array.from(document.querySelectorAll('iframe')).map((el) => {
      const r = el.getBoundingClientRect();
      let rendered = true;
      try {
        rendered = el.checkVisibility({ opacityProperty: true, visibilityProperty: true });
      } catch {
        const cs = getComputedStyle(el);
        rendered = !(cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0);
      }
      const tiny = el.clientWidth <= 1 || el.clientHeight <= 1;
      const offscreen = r.right <= 0 || r.bottom <= 0;
      return !rendered || tiny || offscreen;
    });
    return {
      dom_element_count: document.getElementsByTagName('*').length,
      visible_text_length: document.body ? document.body.innerText.length : 0,
      dom_iframe_count: iframes.length,
      hidden_iframe_count: iframes.filter(Boolean).length,
      title_present: !!document.title,
    };
  }

  chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
    if (msg && msg.type === 'dom') {
      try {
        reply(domStats());
      } catch {
        reply(null);
      }
    }
  });
})();
