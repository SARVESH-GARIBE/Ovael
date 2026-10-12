import { useState } from 'react';
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Copy,
  Eye,
  FileText,
  Info,
  Lock,
  MousePointerClick,
  ShieldAlert,
  ShieldCheck,
  XOctagon,
  type LucideIcon,
} from 'lucide-react';
import type { RiskLevel } from '../api/client';
import { RISK_COLOR } from '../lib/format';
import { RiskGauge, Section } from './ui';

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info' | 'good';
type Status = 'good' | 'ok' | 'caution' | 'danger' | 'unknown';

export interface Smart {
  score: number;
  privacy_score: number;
  risk_level: RiskLevel;
  verdict: string;
  summary: string;
  categories: Array<{ id: string; status: Status; headline: string }>;
  findings: Array<{
    category: string;
    severity: Severity;
    title: string;
    detail: string;
    advice?: string | null;
  }>;
  advice: string[];
  facts: Array<{ label: string; value: string | number }>;
  limited: boolean;
  adult?: boolean;
  offline?: boolean; // the page could not be loaded: reputation-only report
}

const MUTED = '#9c9a88';

const STATUS_COLOR: Record<Status, string> = {
  good: RISK_COLOR.low,
  ok: MUTED,
  caution: RISK_COLOR.medium,
  danger: RISK_COLOR.high,
  unknown: MUTED,
};

const SEVERITY: Record<Severity, { color: string; label: string; icon: LucideIcon }> = {
  critical: { color: RISK_COLOR.high, label: 'Critical', icon: XOctagon },
  high: { color: RISK_COLOR.high, label: 'High', icon: ShieldAlert },
  medium: { color: RISK_COLOR.medium, label: 'Medium', icon: AlertTriangle },
  low: { color: RISK_COLOR.suspicious, label: 'Low', icon: AlertTriangle },
  info: { color: MUTED, label: 'Note', icon: Info },
  good: { color: RISK_COLOR.low, label: 'Good', icon: CheckCircle2 },
};

const CATEGORY: Record<string, { label: string; icon: LucideIcon }> = {
  reputation: { label: 'Reputation', icon: ShieldCheck },
  connection: { label: 'Connection', icon: Lock },
  content: { label: 'Content', icon: FileText },
  behaviour: { label: 'Behaviour', icon: MousePointerClick },
  privacy: { label: 'Privacy', icon: Eye },
};

function asText(domain: string, s: Smart): string {
  const lines = [
    `Ovael smart report: ${domain}`,
    `Verdict: ${s.verdict} (risk ${Math.round(s.score)}/100)`,
    '',
    s.summary,
    '',
    'Findings:',
    ...s.findings.map((f) => `- [${SEVERITY[f.severity].label}] ${f.title}: ${f.detail}`),
  ];
  if (s.advice.length) lines.push('', 'How to stay safe:', ...s.advice.map((a) => `- ${a}`));
  return lines.join('\n');
}

/** The plain-language answer to "is it safe to open this website?", shown above the technical detail. */
export function SmartReport({ smart: s, domain }: { smart: Smart; domain: string }) {
  const [copied, setCopied] = useState(false);
  const color = RISK_COLOR[s.risk_level];
  const concerns = s.findings.filter((f) => f.severity !== 'good');
  const positives = s.findings.filter((f) => f.severity === 'good');

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(asText(domain, s));
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked: nothing to do */
    }
  };

  return (
    <div className="flex flex-col gap-5 animate-fadein">
      <section
        className="card flex flex-col gap-6 p-6 md:flex-row md:items-center"
        style={{ borderColor: `${color}55` }}
      >
        <div className="flex shrink-0 flex-col items-center">
          <RiskGauge score={s.score} level={s.risk_level} size={190} />
          <span className="label -mt-1">Risk of opening</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2">
              <span className="label">Smart report · {domain}</span>
              {s.adult && (
                <span
                  className="rounded px-1.5 py-0.5 text-[11px] font-bold"
                  style={{ color: RISK_COLOR.high, backgroundColor: `${RISK_COLOR.high}22` }}
                >
                  18+
                </span>
              )}
            </span>
            <button className="btn-ghost py-1 text-xs" onClick={copy}>
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? 'Copied' : 'Copy report'}
            </button>
          </div>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight" style={{ color }}>
            {s.verdict}
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-pearl-muted">{s.summary}</p>
          {s.limited && (
            <p className="mt-2 text-[11px] text-pearl-dim">
              This result was cached before the full checks existed. Scan again later for
              reputation, connection and content checks.
            </p>
          )}
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {s.categories.map((c) => {
          const meta = CATEGORY[c.id] ?? { label: c.id, icon: Info };
          const Icon = meta.icon;
          return (
            <div key={c.id} className="card p-4">
              <div className="flex items-center gap-2">
                <Icon className="h-4 w-4" style={{ color: STATUS_COLOR[c.status] }} />
                <span className="label">{meta.label}</span>
                <span
                  className="ml-auto h-2 w-2 rounded-full"
                  style={{ backgroundColor: STATUS_COLOR[c.status] }}
                  aria-label={c.status}
                />
              </div>
              <p className="mt-2 text-sm leading-snug">{c.headline}</p>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Section title="What we found">
          <ul className="space-y-3">
            {[...concerns, ...positives].map((f, i) => {
              const sev = SEVERITY[f.severity];
              const Icon = sev.icon;
              return (
                <li key={i} className="flex gap-3">
                  <Icon className="mt-0.5 h-4 w-4 shrink-0" style={{ color: sev.color }} />
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      <span className="text-sm font-medium">{f.title}</span>
                      <span className="text-[11px] font-semibold" style={{ color: sev.color }}>
                        {sev.label}
                      </span>
                      <span className="text-[11px] text-pearl-dim">
                        {CATEGORY[f.category]?.label}
                      </span>
                    </div>
                    <p className="mt-0.5 text-sm text-pearl-muted">{f.detail}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        </Section>

        <div className="flex flex-col gap-5">
          {s.advice.length > 0 && (
            <Section title="How to stay safe">
              <ul className="space-y-2">
                {s.advice.map((a) => (
                  <li key={a} className="flex gap-2 text-sm text-pearl-muted">
                    <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-ocean" />
                    {a}
                  </li>
                ))}
              </ul>
            </Section>
          )}
          {s.facts.length > 0 && (
            <Section title="Key facts">
              <dl className="space-y-2.5">
                {s.facts.map((f) => (
                  <div key={f.label}>
                    <dt className="text-[11px] text-pearl-dim">{f.label}</dt>
                    <dd className="break-words text-sm">{f.value}</dd>
                  </div>
                ))}
              </dl>
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}
