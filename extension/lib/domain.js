// Registrable domain (eTLD+1) from the Public Suffix List, matching the crawler's
// registrable_or_host(): an IP literal or a bare suffix is returned unchanged.

let RULES = null;

export async function loadPsl() {
  if (RULES) return;
  const list = await (await fetch(chrome.runtime.getURL('data/psl.json'))).json();
  RULES = new Set(list);
}

const IP = /^(\d{1,3}\.){3}\d{1,3}$|^\[?[0-9a-f:]+\]?$/i;

export function registrableDomain(host) {
  host = (host || '').toLowerCase().replace(/\.$/, '');
  if (!host || IP.test(host) || !RULES) return host;
  const labels = host.split('.');
  let suffixLen = 1; // default rule "*": the last label
  for (let i = 0; i < labels.length; i++) {
    const cand = labels.slice(i).join('.');
    if (RULES.has('!' + cand)) {
      suffixLen = labels.length - i - 1;
      break;
    }
    if (RULES.has(cand)) {
      suffixLen = labels.length - i;
      break;
    }
    if (i + 1 < labels.length && RULES.has('*.' + labels.slice(i + 1).join('.'))) {
      suffixLen = labels.length - i;
      break;
    }
  }
  if (labels.length <= suffixLen) return host;
  return labels.slice(labels.length - suffixLen - 1).join('.');
}

export function hostnameOf(url) {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return '';
  }
}
