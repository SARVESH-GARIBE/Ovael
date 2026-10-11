import type { RiskLevel } from '../api/client';

export const RISK_COLOR: Record<RiskLevel, string> = {
  low: '#5B88B2',
  suspicious: '#B9A9E8',
  medium: '#E8B04B',
  high: '#E4572E',
};

export const RISK_LABEL: Record<RiskLevel, string> = {
  low: 'Low',
  suspicious: 'Suspicious',
  medium: 'Medium',
  high: 'High',
};

export function pct(x: number | null | undefined, digits = 0): string {
  return x == null ? '—' : `${(x * 100).toFixed(digits)}%`;
}

export function num(x: number | null | undefined): string {
  if (x == null) return '—';
  if (Math.abs(x) >= 1e6) return `${(x / 1e6).toFixed(1)}M`;
  if (Math.abs(x) >= 1e4) return `${(x / 1e3).toFixed(1)}k`;
  if (Number.isInteger(x)) return x.toLocaleString();
  return Math.abs(x) < 10 ? x.toFixed(2) : x.toFixed(0);
}

export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return '';
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 5) return 'just now';
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}

export function titleCase(s: string): string {
  return s.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

const PROTOCOLS: Record<number, string> = { 1: 'ICMP', 6: 'TCP', 17: 'UDP' };
export function protocolName(p: number | null | undefined): string {
  return p == null ? '' : (PROTOCOLS[p] ?? `proto ${p}`);
}
