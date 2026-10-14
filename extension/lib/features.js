// Turns one measured visit into (a) the crawler's feature row, column for column, so the website
// model sees the same inputs it was trained on (dataset_collection/ovael_crawler/schema.py), and
// (b) the plain-language totals the popup and dashboard show: data shared, companies, cache,
// storage, cookies, fingerprinting.

import { registrableDomain } from './domain.js';

let TRACKERS = null; // tracker domain -> [owner, categories]
let ENTITIES = null; // domain -> company

export async function loadReference() {
  if (TRACKERS) return;
  const get = async (p) => (await fetch(chrome.runtime.getURL(p))).json();
  [TRACKERS, ENTITIES] = await Promise.all([get('data/trackers.json'), get('data/entities.json')]);
}

const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');

/** Same walk as TrackerReference.match(): the host, then each parent domain above the TLD. */
export function matchTracker(host) {
  const labels = host.split('.');
  for (let i = 0; i < labels.length - 1; i++) {
    const cand = labels.slice(i).join('.');
    if (TRACKERS[cand]) return { domain: cand, owner: TRACKERS[cand][0], categories: TRACKERS[cand][1] };
  }
  return null;
}

function companyOf(host, tracker) {
  if (tracker && tracker.owner) return tracker.owner;
  const labels = host.split('.');
  for (let i = 0; i < labels.length - 1; i++) {
    const e = ENTITIES[labels.slice(i).join('.')];
    if (e) return e;
  }
  return registrableDomain(host);
}

function sumKeys(counts, pred) {
  let n = 0;
  for (const [k, v] of Object.entries(counts)) if (pred(k)) n += v;
  return n;
}

/** Sums the per-document instrumentation snapshots (main frame + iframes). */
function instrumentationCounts(visit) {
  const all = {};
  for (const counts of Object.values(visit.docs || {})) {
    for (const [k, v] of Object.entries(counts || {})) all[k] = (all[k] || 0) + v;
  }
  return all;
}

export function cookieSummary(cookies, site) {
  const now = Date.now() / 1000;
  const lifetimes = cookies.filter((c) => !c.session && c.expirationDate).map((c) => (c.expirationDate - now) / 86400);
  const party = (c) => (registrableDomain(c.domain.replace(/^\./, '')) === site ? 'first' : 'third');
  const third = cookies.filter((c) => party(c) === 'third');
  return {
    total_cookies: cookies.length,
    first_party_cookies: cookies.length - third.length,
    third_party_cookies: third.length,
    unattributed_cookies: 0,
    secure_cookies: cookies.filter((c) => c.secure).length,
    httponly_cookies: cookies.filter((c) => c.httpOnly).length,
    session_cookies: cookies.filter((c) => c.session).length,
    samesite_none_cookies: cookies.filter((c) => c.sameSite === 'no_restriction').length,
    max_cookie_lifetime_days: lifetimes.length ? Math.round(Math.max(...lifetimes) * 1000) / 1000 : null,
    third_party_cookie_domains: [...new Set(third.map((c) => registrableDomain(c.domain.replace(/^\./, ''))))].sort(),
  };
}

export function computeFeatures(visit, cookies) {
  const site = visit.domain;
  const f = {};
  let total = 0, failed = 0, httpErr = 0, first = 0, third = 0, subframe = 0;
  const types = {};
  const domains = new Set(), thirdDomains = new Set(), trackerDomains = new Set(), unknownThird = new Set();
  let trackerReqs = 0;
  const byCat = {};
  for (const [host, h] of Object.entries(visit.hosts || {})) {
    total += h.n;
    failed += h.failed;
    httpErr += h.httpErr;
    subframe += h.subframe;
    for (const [t, n] of Object.entries(h.types)) types[t] = (types[t] || 0) + n;
    const reg = registrableDomain(host);
    domains.add(reg);
    if (reg === site) {
      first += h.n;
      continue;
    }
    third += h.n;
    thirdDomains.add(reg);
    const m = matchTracker(host);
    if (m) {
      trackerReqs += h.n;
      trackerDomains.add(m.domain);
      for (const c of m.categories) byCat[c] = (byCat[c] || 0) + h.n;
    } else {
      unknownThird.add(host);
    }
  }
  const t = (k) => types[k] || 0;
  Object.assign(f, {
    total_requests: total,
    successful_requests: total - failed - httpErr,
    failed_requests: failed,
    http_error_requests: httpErr,
    first_party_requests: first,
    third_party_requests: third,
    unique_request_hostnames: Object.keys(visit.hosts || {}).length,
    unique_request_domains: domains.size,
    unique_third_party_domains: thirdDomains.size,
    document_requests: t('main_frame') + t('sub_frame'),
    script_requests: t('script'),
    image_requests: t('image'),
    stylesheet_requests: t('stylesheet'),
    xhr_fetch_requests: t('xmlhttprequest'),
    font_requests: t('font'),
    media_requests: t('media'),
    websocket_requests: t('websocket'),
    other_requests: sumKeys(types, (k) =>
      !['main_frame', 'sub_frame', 'script', 'image', 'stylesheet', 'xmlhttprequest', 'font', 'media', 'websocket'].includes(k)),
    iframe_requests: t('sub_frame'),
    subframe_requests: subframe,
    tracker_matched_requests: trackerReqs,
    unique_tracker_domains: trackerDomains.size,
    tracker_request_ratio: total ? Math.round((trackerReqs / total) * 1e6) / 1e6 : null,
    third_party_hostnames_not_in_reference: unknownThird.size,
  });
  for (const [cat, n] of Object.entries(byCat)) f[`tracker_requests_cat_${slug(cat)}`] = n;

  const { third_party_cookie_domains, ...ck } = cookieSummary(cookies, site);
  Object.assign(f, ck);

  const c = instrumentationCounts(visit);
  const g = (k) => c[k] || 0;
  const readback = ['canvas.toDataURL', 'canvas.toBlob', 'canvas.getImageData', 'canvas.offscreen.convertToBlob'].reduce((a, k) => a + g(k), 0);
  const text = ['canvas.fillText', 'canvas.strokeText', 'canvas.measureText'].reduce((a, k) => a + g(k), 0);
  Object.assign(f, {
    localstorage_write_count: g('storage.localStorage.write'),
    sessionstorage_write_count: g('storage.sessionStorage.write'),
    localstorage_read_count: g('storage.localStorage.read'),
    sessionstorage_read_count: g('storage.sessionStorage.read'),
    document_cookie_writes: g('document.cookie.write'),
    storage_api_calls: sumKeys(c, (k) => k.startsWith('storageapi.')),
    canvas_readback_calls: readback,
    canvas_text_calls: text,
    canvas_api_calls: readback + text + g('canvas.isPointInPath'),
    webgl_unmasked_info_queries: g('webgl.unmaskedInfoQuery'),
    webgl_api_calls:
      sumKeys(c, (k) => k.startsWith('webgl.') && k !== 'webgl.unmaskedInfoQuery') +
      sumKeys(c, (k) => k.startsWith('canvas.getContext.') && k.includes('webgl')),
    offline_audio_contexts: g('OfflineAudioContext()'),
    audio_api_calls: sumKeys(c, (k) => k.startsWith('audio.')) + g('AudioContext()') + g('OfflineAudioContext()') + g('webkitAudioContext()'),
    other_fingerprinting_api_calls: sumKeys(c, (k) => k.startsWith('other.')) + g('RTCPeerConnection()'),
    instrumented_documents: Object.keys(visit.docs || {}).length,
  });
  f.storage_accessed = Number(sumKeys(c, (k) => k.startsWith('storage.') || k.startsWith('storageapi.')) > 0);
  f.storage_modified = Number(f.localstorage_write_count + f.sessionstorage_write_count + f.document_cookie_writes > 0);

  const frames = Object.values(visit.frames || {});
  Object.assign(f, {
    redirect_count: visit.redirects || 0,
    client_side_url_changes: visit.clientSideChanges || 0,
    cross_domain_redirect: Number(!!visit.initialDomain && visit.initialDomain !== site),
    iframe_count: frames.length,
    cross_origin_iframe_count: frames.filter((o) => o && o !== visit.mainOrigin).length,
    load_event_fired: Number(!!visit.loadedAt),
  });
  if (visit.dom) {
    f.dom_element_count = visit.dom.dom_element_count;
    f.visible_text_length = visit.dom.visible_text_length;
    f.dom_iframe_count = visit.dom.dom_iframe_count;
    f.hidden_iframe_count = visit.dom.hidden_iframe_count;
  }
  return f;
}

/** What the visit shared, in terms people care about. Bytes are what the browser could see:
 *  request URLs and bodies going out, Content-Length coming back (absent for some responses). */
export function summarize(visit, cookies) {
  const site = visit.domain;
  const companies = {};
  const trackers = {};
  const d = { sent: 0, sentThird: 0, received: 0, receivedThird: 0, cached: 0, cachedBytes: 0, paramsThird: 0, requests: 0, thirdRequests: 0 };
  for (const [host, h] of Object.entries(visit.hosts || {})) {
    d.requests += h.n;
    d.sent += h.sent;
    d.received += h.recv;
    d.cached += h.cached;
    d.cachedBytes += h.cachedBytes;
    if (registrableDomain(host) === site) continue;
    d.thirdRequests += h.n;
    d.sentThird += h.sent;
    d.receivedThird += h.recv;
    d.paramsThird += h.params;
    const m = matchTracker(host);
    const company = companyOf(host, m);
    const co = (companies[company] ||= { name: company, requests: 0, sent: 0, tracker: false, categories: [] });
    co.requests += h.n;
    co.sent += h.sent;
    if (m) {
      co.tracker = true;
      for (const cat of m.categories) if (!co.categories.includes(cat)) co.categories.push(cat);
      const tr = (trackers[m.domain] ||= { domain: m.domain, owner: m.owner, categories: m.categories, requests: 0, sent: 0 });
      tr.requests += h.n;
      tr.sent += h.sent;
    }
  }
  const c = instrumentationCounts(visit);
  const g = (k) => c[k] || 0;
  const fp = {
    canvas: ['canvas.toDataURL', 'canvas.toBlob', 'canvas.getImageData', 'canvas.offscreen.convertToBlob'].reduce((a, k) => a + g(k), 0),
    gpu: g('webgl.unmaskedInfoQuery'),
    audio: g('OfflineAudioContext()'),
    other: sumKeys(c, (k) => k.startsWith('other.')) + g('RTCPeerConnection()'),
  };
  return {
    data: d,
    companies: Object.values(companies).sort((a, b) => b.requests - a.requests),
    trackers: Object.values(trackers).sort((a, b) => b.requests - a.requests),
    storage: {
      localStorageWrites: g('storage.localStorage.write'),
      sessionStorageWrites: g('storage.sessionStorage.write'),
      cookieWrites: g('document.cookie.write'),
      indexedDbOpens: g('storageapi.indexedDB.open'),
      cacheApiOpens: g('storageapi.caches.open'),
    },
    fingerprinting: fp,
    fingerprints: fp.canvas + fp.gpu + fp.audio > 0,
    cookies: cookieSummary(cookies, site),
  };
}
