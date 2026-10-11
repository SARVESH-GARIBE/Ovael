export type StyleFamily =
  | 'benign'
  | 'flood'
  | 'scan'
  | 'slow-connection'
  | 'credential'
  | 'web'
  | 'stealth'
  | 'unrecognized'
  | 'stub';

export interface StyleConfig {
  family: StyleFamily;
  label: string;
  primaryColor: string;
  glowColor: string;
  packetShape: 'sphere' | 'box' | 'cone' | 'ring' | 'shard' | 'thread';
  description: string;
}

export function normalizeClass(input: string): string {
  if (!input) return '';
  return input
    .toLowerCase()
    .trim()
    .replace(/[\u2013\u2014]/g, '-') // replace en/em dashes with hyphen
    .replace(/\s+/g, ' '); // collapse whitespace
}

export const CLASS_TO_FAMILY_MAP: Record<string, StyleFamily> = {
  // Benign
  benign: 'benign',
  normal: 'benign',

  // Flood / DDoS
  'dns flood': 'flood',
  'icmp flood': 'flood',
  'syn flood': 'flood',
  'udp flood': 'flood',
  ddos: 'flood',
  'dos hulk': 'flood',
  'dos goldeneye': 'flood',

  // Scan
  'port scan': 'scan',
  portscan: 'scan',
  'os scan': 'scan',
  'ping sweep': 'scan',
  'vulnerability scan': 'scan',

  // Slow-connection
  slowloris: 'slow-connection',
  'dos slowloris': 'slow-connection',
  'dos slowhttptest': 'slow-connection',

  // Credential
  'dictionary attack': 'credential',
  'ftp-patator': 'credential',
  'ssh-patator': 'credential',

  // Web
  'web attack brute force': 'web',
  'web attack xss': 'web',
  'web attack sql injection': 'web',

  // Stealth
  bot: 'stealth',
  infiltration: 'stealth',
  heartbleed: 'stealth',
};

export const STYLE_CONFIGS: Record<StyleFamily, StyleConfig> = {
  benign: {
    family: 'benign',
    label: 'Benign Flow',
    primaryColor: '#00f2fe',
    glowColor: '#4facfe',
    packetShape: 'sphere',
    description: 'Small calm blue packets; victim state remains neutral.',
  },
  flood: {
    family: 'flood',
    label: 'Volumetric Flood',
    primaryColor: '#ff0055',
    glowColor: '#ff4d88',
    packetShape: 'cone',
    description: 'Dense swarm; shield ripples, load ring climbs, brief impact shake.',
  },
  scan: {
    family: 'scan',
    label: 'Reconnaissance Scan',
    primaryColor: '#ffb703',
    glowColor: '#ffd166',
    packetShape: 'ring',
    description: 'Thin probe beams sweep port lights sequentially with expanding ping rings.',
  },
  'slow-connection': {
    family: 'slow-connection',
    label: 'Slow Exhaustion',
    primaryColor: '#fb8500',
    glowColor: '#ffb703',
    packetShape: 'thread',
    description: 'Slow threads attach to victim, gradually filling connection slots.',
  },
  credential: {
    family: 'credential',
    label: 'Credential Probe',
    primaryColor: '#e0aaff',
    glowColor: '#c77dff',
    packetShape: 'box',
    description: 'Rapid key-glyph sparks hit lock on the victim with lock rattle feedback.',
  },
  web: {
    family: 'web',
    label: 'Application Web Attack',
    primaryColor: '#06d6a0',
    glowColor: '#48cae4',
    packetShape: 'shard',
    description: 'Payload shards (symbols like </>) strike a small web panel on the victim.',
  },
  stealth: {
    family: 'stealth',
    label: 'Stealth Infiltration',
    primaryColor: '#4a4e69',
    glowColor: '#9a8c98',
    packetShape: 'sphere',
    description: 'Faint slow packets with thin return stream of leak particles to attacker.',
  },
  unrecognized: {
    family: 'unrecognized',
    label: 'Unrecognized Pattern',
    primaryColor: '#f4a261',
    glowColor: '#e76f51',
    packetShape: 'sphere',
    description: 'Amber-grey packets with fallback marker.',
  },
  stub: {
    family: 'stub',
    label: 'Stub / Placeholder',
    primaryColor: '#6c757d',
    glowColor: '#adb5bd',
    packetShape: 'sphere',
    description: 'Neutral grey stream with no attack styling or severity colors.',
  },
};

export function resolveStyleFamily(predictedClass: string, isStub: boolean = false): StyleFamily {
  if (isStub) {
    return 'stub';
  }
  const normalized = normalizeClass(predictedClass);
  return CLASS_TO_FAMILY_MAP[normalized] || 'unrecognized';
}
