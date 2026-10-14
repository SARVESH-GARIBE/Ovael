// Small helpers shared by the popup and the dashboard. Everything that came from the network
// (domains, company names) is inserted as text, never as HTML.

export const RISK = {
  low: { color: '#5b88b2', label: 'Low' },
  suspicious: { color: '#b9a9e8', label: 'Suspicious' },
  medium: { color: '#e8b04b', label: 'Medium' },
  high: { color: '#e4572e', label: 'High' },
};

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function bytes(n) {
  if (!n) return '0 B';
  const u = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n >= 100 || i === 0 ? Math.round(n) : n.toFixed(1)} ${u[i]}`;
}

export const num = (n) => (n == null ? '–' : Number(n).toLocaleString());

export function ago(ts) {
  const s = Math.max(0, (Date.now() - ts) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export function riskBadge(score) {
  if (!score) return h('span', { class: 'badge', style: { color: '#9c9a88', background: '#9c9a8822' } }, 'Not scored');
  const r = RISK[score.risk_level] || RISK.low;
  return h('span', { class: 'badge', style: { color: r.color, background: `${r.color}22` } },
    score.family_name || r.label);
}

export async function getSettings() {
  const { settings } = await chrome.storage.local.get('settings');
  return { backendUrl: 'http://localhost:8000', frontendUrl: 'http://localhost:5173', scoring: true, paused: false,
    excluded: [], ...(settings || {}) };
}

export async function saveSettings(patch) {
  const s = { ...(await getSettings()), ...patch };
  await chrome.storage.local.set({ settings: s });
  return s;
}

export function fullScanUrl(settings, domain) {
  return `${settings.frontendUrl.replace(/\/$/, '')}/website?url=${encodeURIComponent(domain)}`;
}
