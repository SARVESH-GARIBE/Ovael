import type { ReactNode } from 'react';
import type { RiskLevel, TopFeature } from '../api/client';
import { RISK_COLOR, RISK_LABEL, num } from '../lib/format';

export function RiskBadge({ level, score }: { level: RiskLevel; score?: number }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold"
      style={{ color: RISK_COLOR[level], backgroundColor: `${RISK_COLOR[level]}1f` }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: RISK_COLOR[level] }} />
      {RISK_LABEL[level]}
      {score != null && <span className="font-mono opacity-80">{Math.round(score)}</span>}
    </span>
  );
}

/** Half-circle 0-100 gauge, with the four risk bands drawn faintly behind the value. */
export function RiskGauge({
  score,
  level,
  size = 160,
}: {
  score: number;
  level: RiskLevel;
  size?: number;
}) {
  const r = 70;
  const arc = (from: number, to: number) => {
    const a0 = Math.PI * (1 - from / 100);
    const a1 = Math.PI * (1 - to / 100);
    const p = (a: number) => `${80 + r * Math.cos(a)},${80 - r * Math.sin(a)}`;
    return `M${p(a0)} A${r},${r} 0 0 1 ${p(a1)}`;
  };
  const bands: Array<[number, number, RiskLevel]> = [
    [0, 24.5, 'low'],
    [25.5, 49.5, 'suspicious'],
    [50.5, 74.5, 'medium'],
    [75.5, 100, 'high'],
  ];
  return (
    <svg
      viewBox="0 0 160 92"
      width={size}
      role="img"
      aria-label={`Risk score ${Math.round(score)} of 100, ${level}`}
    >
      {bands.map(([a, b, l]) => (
        <path
          key={l}
          d={arc(a, b)}
          stroke={RISK_COLOR[l]}
          strokeOpacity={0.18}
          strokeWidth={10}
          fill="none"
        />
      ))}
      <path
        d={arc(0, Math.max(0.5, Math.min(100, score)))}
        stroke={RISK_COLOR[level]}
        strokeWidth={10}
        strokeLinecap="round"
        fill="none"
        style={{ transition: 'all 400ms ease' }}
      />
      <text x={80} y={74} textAnchor="middle" fontSize={30} fontWeight={700} fill="#FBF9E4">
        {Math.round(score)}
      </text>
      <text x={80} y={89} textAnchor="middle" fontSize={10} fill="#9c9a88" letterSpacing={1}>
        RISK / 100
      </text>
    </svg>
  );
}

/** "Why it was flagged": SHAP contributions with the value next to the normal baseline. */
export function FeatureReasons({
  features,
  limit = 5,
}: {
  features: TopFeature[];
  limit?: number;
}) {
  const top = features.slice(0, limit);
  if (!top.length) return <p className="text-sm text-pearl-dim">No reasons computed yet.</p>;
  const max = Math.max(...top.map((f) => Math.abs(f.contribution)), 1e-9);
  return (
    <ul className="space-y-2.5">
      {top.map((f) => (
        <li key={f.feature}>
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="text-pearl">{f.description}</span>
            <span className="shrink-0 font-mono text-xs text-pearl-dim">
              {num(f.value)} <span className="opacity-60">vs {num(f.baseline)} normal</span>
            </span>
          </div>
          <div className="mt-1 h-1 rounded-full bg-midnight-800">
            <div
              className="h-1 rounded-full"
              style={{
                width: `${(Math.abs(f.contribution) / max) * 100}%`,
                backgroundColor: f.contribution >= 0 ? '#FBF9E4' : '#5B88B2',
              }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function Section({
  title,
  action,
  children,
  className = '',
}: {
  title: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card p-5 ${className}`}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="label">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: string }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div
        className="mt-1 text-2xl font-semibold tabular-nums"
        style={tone ? { color: tone } : undefined}
      >
        {value}
      </div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-pearl-dim">{children}</p>;
}

export function Chip({
  children,
  tone = 'default',
}: {
  children: ReactNode;
  tone?: 'default' | 'warn';
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-mono text-[11px] ${
        tone === 'warn' ? 'bg-risk-medium/15 text-risk-medium' : 'bg-midnight-800 text-pearl-muted'
      }`}
    >
      {children}
    </span>
  );
}

export function Steps({ steps, active }: { steps: string[]; active?: number }) {
  return (
    <ol className="space-y-2">
      {steps.map((s, i) => (
        <li key={i} className="flex gap-3 text-sm">
          <span
            className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold transition-colors ${
              active === i ? 'bg-pearl text-noir' : 'bg-midnight-800 text-pearl-muted'
            }`}
          >
            {i + 1}
          </span>
          <span className={active === i ? 'text-pearl' : 'text-pearl-muted'}>{s}</span>
        </li>
      ))}
    </ol>
  );
}
