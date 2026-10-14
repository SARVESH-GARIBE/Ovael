import { RISK, ago, bytes, fullScanUrl, getSettings, h, num, riskBadge, saveSettings } from './ui/common.js';

const $ = (id) => document.getElementById(id);
const RISK_ORDER = { high: 3, medium: 2, suspicious: 1, low: 0 };

let state = { sites: {}, settings: null, selected: null, sort: 'lastSeen', dir: -1, query: '' };

const COLUMNS = [
  { id: 'domain', label: 'Site', get: (s) => s.domain },
  { id: 'risk', label: 'Model verdict', get: (s) => RISK_ORDER[s.score?.risk_level] ?? -1 },
  { id: 'visits', label: 'Visits', num: true, get: (s) => s.visits },
  { id: 'trackers', label: 'Trackers', num: true, get: (s) => Object.keys(s.trackers).length },
  { id: 'sentThird', label: 'Data out', num: true, get: (s) => s.totals.sentThird },
  { id: 'cookies', label: '3P cookies', num: true, get: (s) => s.last?.cookies?.third_party_cookies ?? 0 },
  { id: 'cache', label: 'Cache', num: true, get: (s) => (s.totals.requests ? s.totals.cached / s.totals.requests : 0) },
  { id: 'lastSeen', label: 'Last visit', num: true, get: (s) => s.lastSeen },
];

async function load() {
  const { sites = {}, backendStatus } = await chrome.storage.local.get(['sites', 'backendStatus']);
  state.sites = sites;
  state.settings = await getSettings();
  const st = $('status');
  if (!state.settings.scoring) st.textContent = 'Model scoring is off';
  else if (!backendStatus) st.textContent = '';
  else st.textContent = backendStatus.ok ? `Model ${backendStatus.model || ''} · scored ${ago(backendStatus.at)}`
    : `Backend unreachable: ${backendStatus.error}`;
  st.style.color = backendStatus && !backendStatus.ok ? RISK.high.color : '';
  render();
}

function render() {
  const sites = Object.values(state.sites);
  renderStats(sites);
  renderCompanies(sites);
  renderTable(sites);
  renderDetail();
}

function renderStats(sites) {
  const t = sites.reduce((a, s) => {
    for (const k of Object.keys(a)) a[k] += s.totals[k] || 0;
    return a;
  }, { requests: 0, thirdRequests: 0, sentThird: 0, cached: 0, cachedBytes: 0 });
  const companies = new Set(), trackers = new Set();
  for (const s of sites) {
    Object.keys(s.companies).forEach((c) => companies.add(c));
    Object.keys(s.trackers).forEach((c) => trackers.add(c));
  }
  const fp = sites.filter((s) => s.last?.fingerprints).length;
  const card = (v, k) => h('div', { class: 'card stat' }, h('div', { class: 'v' }, v), h('div', { class: 'k' }, k));
  $('stats').replaceChildren(
    card(num(sites.length), `sites · ${num(sites.reduce((a, s) => a + s.visits, 0))} visits`),
    card(bytes(t.sentThird), 'sent to third parties'),
    card(num(companies.size), 'companies received data'),
    card(num(trackers.size), 'distinct trackers'),
    card(num(fp), 'sites fingerprinted you'),
    card(`${t.requests ? Math.round((t.cached / t.requests) * 100) : 0}%`, `served from cache (${bytes(t.cachedBytes)})`),
  );
}

function renderCompanies(sites) {
  const agg = {};
  for (const s of sites) {
    for (const c of Object.values(s.companies)) {
      const a = (agg[c.name] ||= { name: c.name, requests: 0, sent: 0, sites: 0, tracker: false });
      a.requests += c.requests;
      a.sent += c.sent;
      a.sites += 1;
      a.tracker ||= c.tracker;
    }
  }
  const list = Object.values(agg).sort((a, b) => b.sites - a.sites || b.requests - a.requests).slice(0, 15);
  if (!list.length) {
    $('companies').replaceChildren(h('li', { class: 'empty' }, 'No third parties yet. Browse a few sites.'));
    return;
  }
  const max = list[0].sites;
  $('companies').replaceChildren(...list.map((c) => h('li', {},
    h('div', { class: 'row' },
      h('span', { class: 'grow trunc' }, c.name),
      c.tracker ? h('span', { class: 'chip warn' }, 'tracker') : null,
      h('span', { class: 'mono dim', style: { fontSize: '11px' } },
        `on ${c.sites} site${c.sites === 1 ? '' : 's'} · ${num(c.requests)} requests · ${bytes(c.sent)} sent`)),
    h('div', { class: 'bar', style: { marginTop: '4px' } },
      h('i', { class: c.tracker ? 'tracker' : '', style: { width: `${(c.sites / max) * 100}%` } })),
  )));
}

function renderTable(sites) {
  const q = state.query.toLowerCase();
  const col = COLUMNS.find((c) => c.id === state.sort);
  const rows = sites.filter((s) => s.domain.includes(q))
    .sort((a, b) => {
      const x = col.get(a), y = col.get(b);
      return (x > y ? 1 : x < y ? -1 : 0) * state.dir;
    });
  const head = h('tr', {}, COLUMNS.map((c) => h('th', {
    class: c.num ? 'num' : '',
    onclick: () => {
      state.dir = state.sort === c.id ? -state.dir : -1;
      state.sort = c.id;
      render();
    },
  }, c.label + (state.sort === c.id ? (state.dir < 0 ? ' ↓' : ' ↑') : ''))));
  const body = rows.map((s) => h('tr', {
    class: `site${state.selected === s.domain ? ' sel' : ''}`,
    onclick: () => {
      state.selected = s.domain;
      render();
    },
  },
  h('td', {}, h('span', { class: 'trunc', style: { display: 'block', maxWidth: '220px' } }, s.domain)),
  h('td', {}, riskBadge(s.score)),
  h('td', { class: 'num mono' }, num(s.visits)),
  h('td', { class: 'num mono' }, num(Object.keys(s.trackers).length)),
  h('td', { class: 'num mono' }, bytes(s.totals.sentThird)),
  h('td', { class: 'num mono' }, num(s.last?.cookies?.third_party_cookies)),
  h('td', { class: 'num mono' }, `${s.totals.requests ? Math.round((s.totals.cached / s.totals.requests) * 100) : 0}%`),
  h('td', { class: 'num dim' }, ago(s.lastSeen)),
  ));
  $('sites').replaceChildren(h('thead', {}, head), h('tbody', {},
    body.length ? body : h('tr', {}, h('td', { colspan: COLUMNS.length, class: 'empty' },
      sites.length ? 'No site matches the filter.' : 'Browse a few websites and they will appear here.'))));
}

function renderDetail() {
  const s = state.sites[state.selected];
  const el = $('detail');
  if (!s) {
    el.replaceChildren(h('p', { class: 'empty' }, 'Pick a site to see what it shared.'));
    return;
  }
  const sc = s.score;
  const fp = s.last?.fingerprinting || {};
  const st = s.last?.storage || {};
  const ck = s.last?.cookies || {};
  const trackers = Object.values(s.trackers).sort((a, b) => b.requests - a.requests);
  const parts = [
    h('div', { class: 'row' }, h('span', { class: 'grow', style: { fontWeight: 650, fontSize: '16px' } }, s.domain), riskBadge(sc)),
    h('div', { class: 'dim', style: { fontSize: '11px', marginTop: '2px' } },
      `${num(s.visits)} visit${s.visits === 1 ? '' : 's'} · first ${ago(s.firstSeen)} · last ${ago(s.lastSeen)}`),
    sc ? h('p', { class: 'muted' }, sc.summary,
      h('span', { class: 'dim' }, ` Model ${sc.model_version}: ${sc.label} (${Math.round(sc.confidence * 100)}% confident, risk ${Math.round(sc.risk_score)}/100).`))
      : h('p', { class: 'dim' }, state.settings?.scoring ? 'Not scored yet.' : 'Model scoring is off.'),
    sc?.top_features?.length ? h('div', {},
      h('div', { class: 'label', style: { margin: '10px 0 4px' } }, 'Why the model says so'),
      sc.top_features.slice(0, 5).map((f) => h('div', { class: 'feat' },
        h('span', { class: 'muted' }, f.description || f.feature),
        h('span', { class: 'mono dim' }, `${num(f.value)} vs ${num(f.baseline)}`)))) : null,
    h('div', { class: 'label', style: { margin: '12px 0 4px' } }, 'Data shared'),
    h('div', { class: 'muted' },
      `${num(s.totals.thirdRequests)} of ${num(s.totals.requests)} requests went to third parties, sending ` +
      `${bytes(s.totals.sentThird)} and ${num(s.totals.paramsThird)} URL parameters. ` +
      `${num(s.totals.cached)} responses (${bytes(s.totals.cachedBytes)}) came from your cache.`),
    h('div', { class: 'label', style: { margin: '12px 0 4px' } }, `Trackers (${trackers.length})`),
    trackers.length ? h('ul', { class: 'list' }, trackers.slice(0, 12).map((t) => h('li', {},
      h('div', { class: 'row' }, h('span', { class: 'mono grow trunc' }, t.domain), h('span', { class: 'dim mono' }, `${t.requests}×`)),
      h('div', { class: 'dim', style: { fontSize: '11px' } }, [t.owner, ...t.categories.slice(0, 2)].filter(Boolean).join(' · ')))))
      : h('p', { class: 'dim' }, 'No known trackers.'),
    h('div', { class: 'label', style: { margin: '12px 0 4px' } }, 'Stored on your device (last visit)'),
    h('div', { class: 'muted' },
      `${num(ck.total_cookies)} cookies, ${num(ck.third_party_cookies)} third-party` +
      (ck.max_cookie_lifetime_days ? `, longest lasts ${Math.round(ck.max_cookie_lifetime_days)} days` : '') +
      `. ${num(st.localStorageWrites)} localStorage and ${num(st.sessionStorageWrites)} sessionStorage writes, ` +
      `${num(st.cookieWrites)} script cookie writes, ${num(st.indexedDbOpens)} IndexedDB, ${num(st.cacheApiOpens)} Cache API.`),
    (fp.canvas || fp.gpu || fp.audio) ? h('p', {}, h('span', { class: 'chip warn' },
      `Fingerprinting: canvas ×${fp.canvas || 0}, GPU ×${fp.gpu || 0}, audio ×${fp.audio || 0}`)) : null,
    h('div', { class: 'row', style: { marginTop: '14px' } },
      h('a', { class: 'btn', href: fullScanUrl(state.settings, s.domain), target: '_blank' }, 'Full Ovael scan'),
      h('button', { class: 'btn danger', onclick: () => forget(s.domain) }, 'Forget this site')),
  ];
  el.replaceChildren(...parts.filter(Boolean)); // replaceChildren would print a null as text
}

async function forget(domain) {
  const { sites = {} } = await chrome.storage.local.get('sites');
  delete sites[domain];
  await chrome.storage.local.set({ sites });
  state.selected = null;
  load();
}

$('search').oninput = (e) => {
  state.query = e.target.value.trim();
  render();
};
$('toggleSettings').onclick = async () => {
  const s = await getSettings();
  $('backendUrl').value = s.backendUrl;
  $('frontendUrl').value = s.frontendUrl;
  $('excluded').value = s.excluded.join('\n');
  $('scoring').checked = s.scoring;
  $('paused').checked = s.paused;
  $('settings').hidden = !$('settings').hidden;
};
$('saveSettings').onclick = async () => {
  await saveSettings({
    backendUrl: $('backendUrl').value.trim() || 'http://localhost:8000',
    frontendUrl: $('frontendUrl').value.trim() || 'http://localhost:5173',
    excluded: $('excluded').value.split(/\s+/).map((d) => d.trim().toLowerCase()).filter(Boolean),
    scoring: $('scoring').checked,
    paused: $('paused').checked,
  });
  $('settings').hidden = true;
  load();
};
$('rescore').onclick = async () => {
  const r = await chrome.runtime.sendMessage({ type: 'rescore' });
  $('status').textContent = `Re-scoring ${r.queued} site${r.queued === 1 ? '' : 's'}…`;
  setTimeout(load, 4000);
};
$('export').onclick = async () => {
  const data = await chrome.storage.local.get(['sites', 'log']);
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 1)], { type: 'application/json' }));
  h('a', { href: url, download: `ovael-history-${new Date().toISOString().slice(0, 10)}.json` }).click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
$('clear').onclick = async () => {
  if (!confirm('Delete the whole browsing history Ovael recorded in this browser?')) return;
  await chrome.storage.local.remove(['sites', 'log']);
  state.selected = null;
  load();
};

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && (changes.sites || changes.backendStatus)) load();
});
load();
