import { bytes, fullScanUrl, getSettings, h, num, riskBadge, saveSettings } from './ui/common.js';

const $ = (id) => document.getElementById(id);

function stat(value, label) {
  return h('div', { class: 'stat' }, h('div', { class: 'v' }, value), h('div', { class: 'k' }, label));
}

async function render() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const view = await chrome.runtime.sendMessage({ type: 'current', tabId: tab?.id });
  const settings = await getSettings();
  const main = $('main');
  main.replaceChildren();
  $('pause').textContent = settings.paused ? 'Resume' : 'Pause';

  if (settings.paused) {
    main.append(h('p', { class: 'empty' }, 'Monitoring is paused. Nothing is being recorded.'));
  }
  if (!view?.visit) {
    $('domain').textContent = tab?.url ? new URL(tab.url).hostname || 'This page' : 'This page';
    const web = /^https?:/.test(tab?.url || '');
    if (!settings.paused) {
      main.append(h('p', { class: 'empty' }, web
        ? 'This tab was opened before Ovael was watching it, so nothing was measured. Reload it to measure.'
        : 'Ovael measures websites (http/https pages). Open a site to see what it shares.'));
      if (web) main.append(h('div', { style: { textAlign: 'center' } },
        h('button', { class: 'btn primary', onclick: async () => { await chrome.tabs.reload(tab.id); window.close(); } }, 'Reload & measure')));
    }
    $('scan').disabled = true;
    return;
  }
  const { visit, summary: s } = view;
  $('domain').textContent = visit.domain;
  $('badge').replaceChildren(riskBadge(visit.score));

  if (visit.score?.summary) {
    main.append(h('p', { class: 'muted', style: { margin: '0 0 10px' } }, visit.score.summary));
  } else if (view.backendStatus && !view.backendStatus.ok && settings.scoring) {
    main.append(h('p', { class: 'dim', style: { margin: '0 0 10px', fontSize: '11px' } },
      `Model verdict unavailable: can't reach the Ovael backend (${view.backendStatus.error}).`));
  } else if (!visit.loaded || !visit.score) {
    main.append(h('p', { class: 'dim', style: { margin: '0 0 10px', fontSize: '11px' } }, 'Measuring… the model verdict follows a few seconds after the page loads.'));
  }

  const companies = s.companies;
  main.append(h('div', { class: 'card grid' },
    stat(bytes(s.data.sentThird), 'sent to third parties'),
    stat(num(companies.length), 'companies contacted'),
    stat(num(s.trackers.length), 'trackers'),
    stat(num(s.cookies.third_party_cookies), 'third-party cookies'),
    stat(`${num(s.data.cached)}`, `served from cache (${bytes(s.data.cachedBytes)})`),
    stat(s.fingerprints ? 'Yes' : 'No', 'fingerprinting'),
  ));

  if (companies.length) {
    const max = companies[0].requests;
    main.append(h('section', {},
      h('div', { class: 'label', style: { marginBottom: '4px' } }, 'Who receives your data'),
      h('ul', { class: 'list' }, companies.slice(0, 6).map((c) => h('li', {},
        h('div', { class: 'row' },
          h('span', { class: 'grow trunc' }, c.name),
          c.tracker ? h('span', { class: 'chip warn' }, 'tracker') : null,
          h('span', { class: 'mono dim', style: { fontSize: '11px' } }, `${c.requests}× · ${bytes(c.sent)}`)),
        h('div', { class: 'bar', style: { marginTop: '4px' } },
          h('i', { class: c.tracker ? 'tracker' : '', style: { width: `${(c.requests / max) * 100}%` } })),
      ))),
    ));
  }

  const st = s.storage;
  const fp = s.fingerprinting;
  const fpParts = [fp.canvas && `canvas ×${fp.canvas}`, fp.gpu && `GPU identity ×${fp.gpu}`, fp.audio && `audio ×${fp.audio}`].filter(Boolean);
  main.append(h('section', { class: 'card' },
    h('div', { class: 'label', style: { marginBottom: '6px' } }, 'Stored on your device'),
    h('div', { class: 'muted' },
      `${num(s.cookies.total_cookies)} cookies (${num(s.cookies.third_party_cookies)} third-party), ` +
      `${num(st.localStorageWrites)} localStorage writes, ${num(st.cookieWrites)} cookie writes by scripts, ` +
      `${num(st.indexedDbOpens)} IndexedDB and ${num(st.cacheApiOpens)} Cache API opens.`),
    fpParts.length ? h('div', { style: { marginTop: '6px' } }, h('span', { class: 'chip warn' }, `Fingerprinting: ${fpParts.join(', ')}`)) : null,
    h('div', { class: 'dim', style: { marginTop: '6px', fontSize: '11px' } },
      `${num(s.data.requests)} requests, ${num(s.data.thirdRequests)} to third parties carrying ${num(s.data.paramsThird)} URL parameters.`),
  ));

  $('scan').onclick = () => chrome.tabs.create({ url: fullScanUrl(settings, visit.domain) });
}

$('dashboard').onclick = () => chrome.runtime.openOptionsPage();
$('pause').onclick = async () => {
  const s = await getSettings();
  await saveSettings({ paused: !s.paused });
  render();
};

render();
setInterval(render, 2000);
