// Ovael Privacy Monitor: background service worker.
//
// One "visit" per tab, from a top-level navigation to the next. While it lasts, every request the
// tab makes is folded into per-host counters (requests, bytes out, bytes in, cache hits, query
// parameters), the page's instrumentation snapshots arrive from content/bridge.js, and frame
// commits are counted. Five seconds after the page's load event (the crawler's settle window) a
// snapshot of the features is sent to the Ovael backend for the website model's verdict. When the
// visit ends, its totals are merged into the per-site history in chrome.storage.local.
//
// Privacy: history never leaves the browser. The backend receives only the registrable domain and
// numeric feature counts. No URLs, paths, page text or cookie values.

import { hostnameOf, loadPsl, registrableDomain } from './lib/domain.js';
import { computeFeatures, loadReference, matchTracker, summarize } from './lib/features.js';

const DEFAULTS = { backendUrl: 'http://localhost:8000', scoring: true, paused: false, excluded: [] };
const MODEL_WINDOW_MS = 5000; // crawler settle_s: features the model sees are taken at load + 5 s
const LOG_LIMIT = 2000;

let visits = {}; // tabId -> live visit
const pending = {}; // requestId -> { tabId, key, host }
const retired = {}; // tabId -> documentIds of the tab's previous visit (late requests from it are ignored)
let current = { ...DEFAULTS }; // settings, kept in memory so request handlers never wait on storage
const ready = (async () => {
  await Promise.all([loadPsl(), loadReference()]);
  const { live, settings: s } = await chrome.storage.session.get('live').then(async (x) => ({
    ...x, ...(await chrome.storage.local.get('settings')) }));
  current = { ...DEFAULTS, ...(s || {}) };
  if (live) visits = live; // the worker was stopped and restarted mid-visit
})();

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes.settings) current = { ...DEFAULTS, ...(changes.settings.newValue || {}) };
});

async function settings() {
  return current;
}

let persistTimer = null;
function persistLive() {
  if (persistTimer) return;
  persistTimer = setTimeout(() => {
    persistTimer = null;
    chrome.storage.session.set({ live: visits }).catch(() => {});
  }, 500);
}

// Storage writes are serialised so concurrent visit ends never overwrite each other.
let writeChain = Promise.resolve();
const serial = (fn) => (writeChain = writeChain.then(fn, fn));

function newVisit(tabId, url) {
  const host = hostnameOf(url);
  return {
    key: `${tabId}:${Date.now()}:${Math.random().toString(36).slice(2, 7)}`,
    tabId,
    startedAt: Date.now(),
    committedAt: null,
    loadedAt: null,
    initialDomain: registrableDomain(host),
    host,
    domain: registrableDomain(host),
    mainOrigin: null,
    redirects: 0,
    clientSideChanges: 0,
    hosts: {},
    docs: {},
    documentIds: {},
    frames: {},
    dom: null,
    modelFeatures: null,
    score: null,
  };
}

const isWeb = (url) => /^(https?|wss?):\/\//i.test(url || '');

function bodySize(body) {
  if (!body) return 0;
  let n = 0;
  for (const part of body.raw || []) n += part.bytes ? part.bytes.byteLength : 0;
  for (const [k, vals] of Object.entries(body.formData || {})) for (const v of vals) n += k.length + String(v).length + 2;
  return n;
}

function paramCount(url) {
  try {
    return [...new URL(url).searchParams.keys()].length;
  } catch {
    return 0;
  }
}

function hostStats(visit, host) {
  return (visit.hosts[host] ||= { n: 0, failed: 0, httpErr: 0, types: {}, sent: 0, recv: 0, cached: 0, cachedBytes: 0, params: 0, subframe: 0 });
}

// ------------------------------------------------------------------------------- requests
chrome.webRequest.onBeforeRequest.addListener(
  (d) => {
    if (d.tabId < 0 || !isWeb(d.url)) return;
    ready.then(() => {
      if (d.type === 'main_frame') {
        const prev = visits[d.tabId];
        if (!prev || prev.navRequestId !== d.requestId) {
          if (prev) endVisit(prev);
          const s = current;
          const v = newVisit(d.tabId, d.url);
          if (s.paused || s.excluded.includes(v.domain)) {
            delete visits[d.tabId];
            persistLive();
            return;
          }
          v.navRequestId = d.requestId;
          visits[d.tabId] = v;
        }
      }
      const v = visits[d.tabId];
      if (!v) return;
      // Beacons and in-flight fetches from the page being left belong to that page, not this one.
      if (d.type !== 'main_frame' && isRetired(d.tabId, d.documentId || d.parentDocumentId)) return;
      const host = hostnameOf(d.url);
      const h = hostStats(v, host);
      h.n += 1;
      h.types[d.type] = (h.types[d.type] || 0) + 1;
      h.sent += d.url.length + bodySize(d.requestBody);
      h.params += paramCount(d.url);
      if (d.frameId !== 0) h.subframe += 1;
      pending[d.requestId] = { tabId: d.tabId, key: v.key, host };
      persistLive();
    });
  },
  { urls: ['<all_urls>'] },
  ['requestBody'],
);

chrome.webRequest.onBeforeRedirect.addListener(
  (d) => {
    if (d.type !== 'main_frame' || d.tabId < 0) return;
    ready.then(() => {
      const v = visits[d.tabId];
      if (v && v.navRequestId === d.requestId) v.redirects += 1;
    });
  },
  { urls: ['<all_urls>'] },
);

function requestFor(d) {
  const p = pending[d.requestId];
  const v = p && visits[p.tabId];
  return v && v.key === p.key ? [v, v.hosts[p.host]] : [null, null];
}

chrome.webRequest.onCompleted.addListener(
  (d) => {
    ready.then(() => {
      const [v, h] = requestFor(d);
      delete pending[d.requestId];
      if (!h) return;
      const len = Number((d.responseHeaders || []).find((x) => x.name.toLowerCase() === 'content-length')?.value) || 0;
      if (d.statusCode >= 400) h.httpErr += 1;
      if (d.fromCache) {
        h.cached += 1;
        h.cachedBytes += len;
      } else {
        h.recv += len;
      }
      persistLive();
      updateBadge(v);
    });
  },
  { urls: ['<all_urls>'] },
  ['responseHeaders'],
);

chrome.webRequest.onErrorOccurred.addListener(
  (d) => {
    ready.then(() => {
      const [, h] = requestFor(d);
      delete pending[d.requestId];
      if (h) h.failed += 1;
    });
  },
  { urls: ['<all_urls>'] },
);

// ----------------------------------------------------------------------------- navigation
const isRetired = (tabId, documentId) => !!(documentId && retired[tabId]?.[documentId]);

chrome.webNavigation.onCommitted.addListener((d) => {
  if (!isWeb(d.url)) {
    // Leaving the web (about:blank, chrome://, a PDF viewer...) ends the visit.
    if (d.frameId === 0) ready.then(() => visits[d.tabId] && endVisit(visits[d.tabId]));
    return;
  }
  ready.then(() => {
    let v = visits[d.tabId];
    if (d.frameId === 0) {
      // A normal navigation already opened a visit in onBeforeRequest (not yet committed). A
      // commit without one is a back/forward-cache restore, which makes no network request.
      if (!v || v.committedAt) {
        if (v) endVisit(v);
        v = visits[d.tabId] = newVisit(d.tabId, d.url);
      }
      v.host = hostnameOf(d.url);
      v.domain = registrableDomain(v.host);
      v.mainOrigin = new URL(d.url).origin;
      v.committedAt = Date.now();
    } else if (v) {
      let origin = null;
      try {
        origin = new URL(d.url).origin;
      } catch {
        /* about:blank and friends count as frames but not as cross-origin */
      }
      v.frames[d.frameId] = origin === 'null' ? null : origin;
    }
    if (v && d.documentId) v.documentIds[d.documentId] = 1;
    persistLive();
  });
});

for (const ev of [chrome.webNavigation.onHistoryStateUpdated, chrome.webNavigation.onReferenceFragmentUpdated]) {
  ev.addListener((d) => {
    if (d.frameId !== 0) return;
    ready.then(() => {
      const v = visits[d.tabId];
      if (v) v.clientSideChanges += 1;
    });
  });
}

chrome.webNavigation.onCompleted.addListener((d) => {
  if (d.frameId !== 0) return;
  ready.then(() => {
    const v = visits[d.tabId];
    if (!v || v.loadedAt) return;
    v.loadedAt = Date.now();
    const key = v.key;
    setTimeout(() => modelSnapshot(d.tabId, key), MODEL_WINDOW_MS);
  });
});

chrome.tabs.onRemoved.addListener((tabId) => {
  ready.then(() => {
    const v = visits[tabId];
    if (v) endVisit(v);
  });
});

// Instrumentation snapshots from every frame of the page (content/bridge.js).
chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg?.type === 'instr' && sender.tab) {
    ready.then(() => {
      const v = visits[sender.tab.id];
      // Only documents committed during this visit: a page's last report on unload must not
      // land in the next page's visit.
      if (v && !isRetired(sender.tab.id, sender.documentId)) {
        v.docs[msg.snap.doc_id] = msg.snap.counts;
        persistLive();
      }
    });
    return false;
  }
  if (msg?.type === 'current') {
    ready.then(async () => reply(await currentView(msg.tabId)));
    return true;
  }
  if (msg?.type === 'rescore') {
    ready.then(async () => reply(await rescoreAll()));
    return true;
  }
  return false;
});

// --------------------------------------------------------------------------------- visits
async function cookiesFor(v) {
  const domains = new Set([v.domain]);
  for (const host of Object.keys(v.hosts)) domains.add(registrableDomain(host));
  const seen = new Map();
  for (const domain of domains) {
    try {
      for (const c of await chrome.cookies.getAll({ domain })) seen.set(`${c.domain}|${c.path}|${c.name}`, c);
    } catch {
      /* invalid domain for the cookies API: skip */
    }
  }
  // Values are never read beyond this point: only flags, domain and expiry are used.
  return [...seen.values()].map(({ domain, secure, httpOnly, session, sameSite, expirationDate }) =>
    ({ domain, secure, httpOnly, session, sameSite, expirationDate }));
}

async function readDom(tabId) {
  try {
    return await chrome.tabs.sendMessage(tabId, { type: 'dom' }, { frameId: 0 });
  } catch {
    return null;
  }
}

async function modelSnapshot(tabId, key) {
  await ready;
  const v = visits[tabId];
  if (!v || v.key !== key) return;
  v.dom = (await readDom(tabId)) || v.dom;
  v.modelFeatures = computeFeatures(v, await cookiesFor(v));
  persistLive();
  enqueueScore(v.domain, v.modelFeatures, v.key);
}

function endVisit(v) {
  if (visits[v.tabId]?.key === v.key) delete visits[v.tabId];
  retired[v.tabId] = v.documentIds;
  persistLive();
  if (!v.domain || !Object.keys(v.hosts).length) return;
  serial(async () => {
    const cookies = await cookiesFor(v);
    const sum = summarize(v, cookies);
    const features = v.modelFeatures || computeFeatures(v, cookies);
    if (!v.modelFeatures) enqueueScore(v.domain, features, v.key);
    await mergeIntoHistory(v, sum, features);
  });
}

async function mergeIntoHistory(v, sum, features) {
  const { sites = {}, log = [] } = await chrome.storage.local.get(['sites', 'log']);
  const s = (sites[v.domain] ||= {
    domain: v.domain, firstSeen: v.startedAt, lastSeen: 0, visits: 0,
    totals: { requests: 0, thirdRequests: 0, sent: 0, sentThird: 0, received: 0, cached: 0, cachedBytes: 0, paramsThird: 0 },
    companies: {}, trackers: {}, score: null,
  });
  s.visits += 1;
  s.lastSeen = Math.max(s.lastSeen, v.startedAt);
  for (const k of Object.keys(s.totals)) {
    s.totals[k] += { requests: sum.data.requests, thirdRequests: sum.data.thirdRequests, sent: sum.data.sent,
      sentThird: sum.data.sentThird, received: sum.data.received, cached: sum.data.cached,
      cachedBytes: sum.data.cachedBytes, paramsThird: sum.data.paramsThird }[k] || 0;
  }
  for (const c of sum.companies) {
    const t = (s.companies[c.name] ||= { name: c.name, requests: 0, sent: 0, tracker: false, categories: [] });
    t.requests += c.requests;
    t.sent += c.sent;
    t.tracker ||= c.tracker;
    for (const cat of c.categories) if (!t.categories.includes(cat)) t.categories.push(cat);
  }
  for (const tr of sum.trackers) {
    const t = (s.trackers[tr.domain] ||= { domain: tr.domain, owner: tr.owner, categories: tr.categories, requests: 0, sent: 0 });
    t.requests += tr.requests;
    t.sent += tr.sent;
  }
  s.last = { at: v.startedAt, storage: sum.storage, fingerprinting: sum.fingerprinting, fingerprints: sum.fingerprints, cookies: sum.cookies };
  s.features = features;
  if (v.score) s.score = v.score;
  log.push({ domain: v.domain, at: v.startedAt, thirdRequests: sum.data.thirdRequests, sentThird: sum.data.sentThird,
    trackers: sum.trackers.length, risk: s.score?.risk_level || null });
  await chrome.storage.local.set({ sites, log: log.slice(-LOG_LIMIT) });
}

// ------------------------------------------------------------------------------ scoring
let queue = [];
let flushTimer = null;

function enqueueScore(domain, features, key) {
  queue.push({ domain, features, key });
  if (!flushTimer) flushTimer = setTimeout(flushScores, 2000);
}

async function flushScores() {
  flushTimer = null;
  const batch = queue.splice(0, 50);
  if (!batch.length) return;
  const s = await settings();
  if (!s.scoring) return;
  let results;
  try {
    const r = await fetch(`${s.backendUrl.replace(/\/$/, '')}/api/extension/score`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ visits: batch.map(({ domain, features }) => ({ domain, features })) }),
    });
    if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 120)}`);
    results = await r.json();
    await chrome.storage.local.set({ backendStatus: { ok: true, at: Date.now(), model: results[0]?.model_version } });
  } catch (e) {
    await chrome.storage.local.set({ backendStatus: { ok: false, at: Date.now(), error: String(e.message || e) } });
    return;
  }
  const scored = {};
  batch.forEach((b, i) => {
    const res = { ...results[i], scoredAt: Date.now() };
    scored[b.domain] = res;
    for (const v of Object.values(visits)) {
      if (v.key === b.key) {
        v.score = res;
        updateBadge(v);
      }
    }
  });
  await serial(async () => {
    const { sites = {} } = await chrome.storage.local.get('sites');
    for (const [domain, res] of Object.entries(scored)) if (sites[domain]) sites[domain].score = res;
    await chrome.storage.local.set({ sites });
  });
  persistLive();
  if (queue.length) flushTimer = setTimeout(flushScores, 2000);
}

async function rescoreAll() {
  const { sites = {} } = await chrome.storage.local.get('sites');
  for (const s of Object.values(sites)) if (s.features) enqueueScore(s.domain, s.features, null);
  return { queued: queue.length };
}

// ------------------------------------------------------------------------------ popup / badge
const BADGE = { low: '#5B88B2', suspicious: '#8f7fd0', medium: '#c98f22', high: '#E4572E' };

function updateBadge(v) {
  if (!v) return;
  const trackers = new Set();
  for (const host of Object.keys(v.hosts)) {
    const m = registrableDomain(host) !== v.domain && matchTracker(host);
    if (m) trackers.add(m.domain);
  }
  const n = trackers.size;
  chrome.action.setBadgeText({ tabId: v.tabId, text: n ? String(n) : '' }).catch(() => {});
  chrome.action.setBadgeBackgroundColor({ tabId: v.tabId, color: BADGE[v.score?.risk_level] || '#3f6285' }).catch(() => {});
}

async function currentView(tabId) {
  const v = visits[tabId];
  const s = await settings();
  const { sites = {}, backendStatus = null } = await chrome.storage.local.get(['sites', 'backendStatus']);
  if (!v) return { visit: null, settings: s, backendStatus };
  const cookies = await cookiesFor(v);
  return {
    visit: { domain: v.domain, host: v.host, startedAt: v.startedAt, loaded: !!v.loadedAt, score: v.score },
    summary: summarize(v, cookies),
    history: sites[v.domain] ? { visits: sites[v.domain].visits, firstSeen: sites[v.domain].firstSeen } : null,
    settings: s,
    backendStatus,
  };
}
