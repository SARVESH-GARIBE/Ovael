import { useState } from 'react';
import {
  ArrowRight,
  CheckCircle2,
  ChartLine,
  GraduationCap,
  Loader2,
  Play,
  Swords,
  Table2,
  Undo2,
  XCircle,
} from 'lucide-react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from 'recharts';
import type { RiskLevel } from '../api/client';
import {
  useEvasion,
  useEvasionOptions,
  useProbe,
  usePromote,
  useTeach,
  type EvasionPoint,
  type EvasionResult,
  type ProbeSummary,
} from '../api/hooks';
import { Victim } from '../characters/Victim';
import { RISK_COLOR, RISK_LABEL, pct, titleCase } from '../lib/format';

/* ================================================================ learning loop */

const LEVELS: RiskLevel[] = ['high', 'medium', 'suspicious', 'low'];

function OutcomeBar({ levels, total }: { levels: ProbeSummary['levels']; total: number }) {
  return (
    <div>
      <div className="flex h-2.5 gap-[2px] overflow-hidden rounded-full">
        {LEVELS.filter((l) => levels[l]).map((l) => (
          <div
            key={l}
            className="h-full origin-left animate-grow"
            style={{ width: `${(levels[l] / total) * 100}%`, backgroundColor: RISK_COLOR[l] }}
            title={`${RISK_LABEL[l]}: ${levels[l]}`}
          />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-pearl-dim">
        {LEVELS.filter((l) => levels[l]).map((l) => (
          <span key={l} className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm" style={{ backgroundColor: RISK_COLOR[l] }} />
            {RISK_LABEL[l]} {levels[l]}
          </span>
        ))}
      </div>
    </div>
  );
}

function ProbeView({ p }: { p: ProbeSummary }) {
  const top = Object.entries(p.labels)[0];
  return (
    <div className="mt-4 space-y-3 animate-rise">
      <div className="font-mono text-[11px] text-pearl-dim">model {p.model_version}</div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="label">Recognised</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">{pct(p.recognized)}</div>
        </div>
        <div>
          <div className="label">Unusual</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">{pct(p.unusual)}</div>
        </div>
      </div>
      <p className="text-sm text-pearl-muted">
        Most common answer: <span className="text-pearl">{top ? titleCase(top[0]) : '—'}</span>{' '}
        <span className="text-pearl-dim">
          ({top?.[1]} of {p.flows})
        </span>
      </p>
      <OutcomeBar levels={p.levels} total={p.flows} />
    </div>
  );
}

function StepCard({
  n,
  title,
  line,
  children,
  done,
}: {
  n: number;
  title: string;
  line: string;
  children: React.ReactNode;
  done?: boolean;
}) {
  return (
    <section
      className={`card flex flex-col p-5 transition-colors duration-300 ${done ? 'border-ocean/60' : ''}`}
    >
      <div className="flex items-center gap-2">
        <span
          className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
            done ? 'bg-ocean text-noir' : 'bg-midnight-800 text-pearl-muted'
          }`}
        >
          {done ? '✓' : n}
        </span>
        <h3 className="font-semibold">{title}</h3>
      </div>
      <p className="mt-2 text-sm text-pearl-dim">{line}</p>
      <div className="mt-4 flex-1">{children}</div>
    </section>
  );
}

function MiniVictim({ mood }: { mood: 'confused' | 'relieved' }) {
  return (
    <svg viewBox="-60 -200 120 205" className="h-24 w-16" aria-label={`victim, ${mood}`}>
      <Victim mood={mood} />
    </svg>
  );
}

function LearningLoop() {
  const [label, setLabel] = useState('exfiltration');
  const [before, setBefore] = useState<ProbeSummary>();
  const [after, setAfter] = useState<ProbeSummary>();
  const probe = useProbe();
  const teach = useTeach();
  const promote = usePromote();
  const taught = teach.data;

  const reset = () => {
    setBefore(undefined);
    setAfter(undefined);
    teach.reset();
    probe.reset();
  };

  return (
    <div className="space-y-5">
      <p className="max-w-3xl text-sm text-pearl-muted">
        The claim behind Ovael is that an unknown attack does not stay unknown. This runs that claim
        end to end on the real models: show the network model a behaviour it was never trained on,
        let an analyst name it, retrain, and show it the same behaviour again.
      </p>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-3">
        <StepCard
          n={1}
          title="Show it something new"
          line="Flows of data quietly leaving over UDP. No training class looks like this."
          done={Boolean(before)}
        >
          <button
            className="btn-primary"
            disabled={probe.isPending || Boolean(before)}
            onClick={() => probe.mutate(40, { onSuccess: setBefore })}
          >
            {probe.isPending && !before ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            Send 40 flows
          </button>
          {before && <ProbeView p={before} />}
        </StepCard>

        <StepCard
          n={2}
          title="Teach it"
          line="An analyst names the behaviour. Those 40 flows become training data and the model is retrained."
          done={Boolean(taught)}
        >
          <div className="flex gap-2">
            <input
              className="input min-w-0 flex-1 py-1.5"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              aria-label="Name of the new behaviour"
              disabled={!before || Boolean(taught)}
            />
            <button
              className="btn-primary"
              disabled={!before || teach.isPending || Boolean(taught) || label.trim().length < 2}
              onClick={() => before && teach.mutate({ probe_id: before.probe_id, label })}
            >
              {teach.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <GraduationCap className="h-4 w-4" />
              )}
              {teach.isPending ? 'Retraining…' : 'Label & retrain'}
            </button>
          </div>
          {teach.error && <p className="mt-3 text-sm text-risk-high">{teach.error.message}</p>}
          {taught && (
            <div className="mt-4 space-y-2 text-sm animate-rise">
              <div className="flex items-center gap-2">
                {taught.promoted ? (
                  <CheckCircle2 className="h-4 w-4 text-ocean" />
                ) : (
                  <XCircle className="h-4 w-4 text-risk-medium" />
                )}
                <span>
                  <span className="font-mono">{taught.version}</span>{' '}
                  {taught.promoted ? 'is now active' : 'was trained but not promoted'}
                </span>
              </div>
              <p className="text-pearl-dim">{taught.reason}</p>
              <p className="text-pearl-dim">
                Checked on the same held-out test set as {taught.previous_version ?? 'before'}.
              </p>
            </div>
          )}
        </StepCard>

        <StepCard
          n={3}
          title="Show it again"
          line="Fresh flows of the same behaviour, never seen in training."
          done={Boolean(after)}
        >
          <button
            className="btn-primary"
            disabled={!taught || probe.isPending || Boolean(after)}
            onClick={() => probe.mutate(40, { onSuccess: setAfter })}
          >
            {probe.isPending && before ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            Send 40 new flows
          </button>
          {after && <ProbeView p={after} />}
        </StepCard>
      </div>

      {before && after && (
        <section className="card p-6 animate-rise">
          <h3 className="label">Before and after</h3>
          <div className="mt-4 grid grid-cols-[auto_1fr_auto_1fr] items-center gap-x-4 gap-y-3 sm:gap-x-8">
            <MiniVictim mood="confused" />
            <div>
              <div className="font-mono text-xs text-pearl-dim">{before.model_version}</div>
              <div className="text-3xl font-semibold tabular-nums">{pct(before.recognized)}</div>
              <div className="text-sm text-pearl-dim">recognised as an attack</div>
            </div>
            <MiniVictim mood="relieved" />
            <div>
              <div className="font-mono text-xs text-pearl-dim">{after.model_version}</div>
              <div className="text-3xl font-semibold tabular-nums">{pct(after.recognized)}</div>
              <div className="text-sm text-pearl-dim">
                recognised, mostly as {titleCase(Object.keys(after.labels)[0] ?? '')}
              </div>
            </div>
          </div>
          <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-midnight-800 pt-4">
            <button className="btn-ghost" onClick={reset}>
              Run again
            </button>
            {taught?.promoted && taught.previous_version && (
              <button
                className="btn-ghost"
                disabled={promote.isPending || promote.isSuccess}
                onClick={() =>
                  promote.mutate({ module: 'network', version: taught.previous_version! })
                }
              >
                <Undo2 className="h-4 w-4" />
                {promote.isSuccess
                  ? `${taught.previous_version} is active again`
                  : `Undo: make ${taught.previous_version} active again`}
              </button>
            )}
          </div>
        </section>
      )}
    </div>
  );
}

/* ================================================================ evasion */

// Validated categorical slots (dark surface #050c17): see the dataviz palette check.
const SERIES = [
  { key: 'recognized', name: 'Classifier recognises it', color: '#3987e5' },
  { key: 'unusual', name: 'Anomaly detector flags it', color: '#d95926' },
  { key: 'caught', name: 'Ovael raises an alert', color: '#199e70' },
] as const;

const ATTACK_LABELS: Record<string, string> = {
  dos_flood: 'Flood',
  port_scan: 'Port scan',
  slow_dos: 'Slowloris',
  brute_force: 'Brute force',
  web_attack: 'Web attack',
};
const TECHNIQUE_LABELS: Record<string, string> = {
  slow_down: 'Slow down',
  pad_packets: 'Pad packets',
  spread_out: 'Spread out',
  mimic: 'Mimic normal',
};

function ChartTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-midnight-700 bg-noir px-3 py-2 text-xs shadow-xl">
      <div className="mb-1 text-pearl-dim">{Math.round(Number(label) * 100)}% modified</div>
      {payload.map((p) => (
        <div key={p.dataKey as string} className="flex items-center gap-2">
          <span className="h-0.5 w-3 rounded" style={{ backgroundColor: p.color }} />
          <span className="text-pearl-muted">{p.name}</span>
          <span className="ml-auto pl-3 font-mono text-pearl">{pct(p.value as number)}</span>
        </div>
      ))}
    </div>
  );
}

function verdict(r: EvasionResult): string[] {
  const s = r.summary;
  const out: string[] = [];
  if (s.classifier_breaks_at == null) {
    out.push('The classifier still recognises this attack even when fully modified this way.');
  } else {
    out.push(
      `The classifier stops recognising it at ${pct(s.classifier_breaks_at)} modification. ` +
        `At that point the anomaly detector flags ${pct(s.unusual_where_classifier_breaks)} of flows ` +
        `and Ovael still raises an alert on ${pct(s.caught_where_classifier_breaks)}.`
    );
  }
  out.push(
    s.fully_evades_at == null
      ? `Fully modified, Ovael still catches ${pct(s.caught_at_full_strength)}.`
      : `From ${pct(s.fully_evades_at)} modification almost everything gets through: neither model notices.`
  );
  return out;
}

function Evasion() {
  const { data: options } = useEvasionOptions();
  const [attack, setAttack] = useState('dos_flood');
  const [technique, setTechnique] = useState('mimic');
  const [table, setTable] = useState(false);
  const run = useEvasion();
  const r = run.data;
  const pts: EvasionPoint[] = r?.points ?? [];

  const pill = (on: boolean) =>
    `rounded-full border px-3 py-1.5 text-sm transition-colors duration-200 ${
      on
        ? 'border-pearl bg-pearl text-noir'
        : 'border-midnight-700 text-pearl-muted hover:border-ocean hover:text-pearl'
    }`;

  return (
    <div className="space-y-5">
      <p className="max-w-3xl text-sm text-pearl-muted">
        An attacker does not need a new attack, only a disguised one. Pick an attack and a disguise.
        Ovael modifies the attack's features from 0% to 100% and runs every step through both real
        models and the decision table. This tests the models; it sends no traffic.
      </p>

      <section className="card space-y-4 p-5">
        <div>
          <div className="label mb-2">Attack</div>
          <div className="flex flex-wrap gap-2">
            {(options?.attacks ?? Object.keys(ATTACK_LABELS)).map((a) => (
              <button key={a} className={pill(a === attack)} onClick={() => setAttack(a)}>
                {ATTACK_LABELS[a] ?? titleCase(a)}
              </button>
            ))}
          </div>
        </div>
        <div>
          <div className="label mb-2">Disguise</div>
          <div className="flex flex-wrap gap-2">
            {Object.keys(options?.techniques ?? TECHNIQUE_LABELS).map((t) => (
              <button key={t} className={pill(t === technique)} onClick={() => setTechnique(t)}>
                {TECHNIQUE_LABELS[t] ?? titleCase(t)}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-pearl-dim">{options?.techniques[technique]}</p>
        </div>
        <button
          className="btn-primary"
          disabled={run.isPending}
          onClick={() => run.mutate({ attack, technique, steps: 11, flows: 80 })}
        >
          {run.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Swords className="h-4 w-4" />
          )}
          Run the sweep
        </button>
        {run.error && <p className="text-sm text-risk-high">{run.error.message}</p>}
      </section>

      {r && (
        <section className="card p-5 animate-rise">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="font-semibold">
                {ATTACK_LABELS[r.attack]} · {TECHNIQUE_LABELS[r.technique]}
              </h3>
              <p className="text-xs text-pearl-dim">
                {r.flows_per_step} flows per step · model {r.model_version}
              </p>
            </div>
            <button className="btn-ghost px-2.5 py-1 text-xs" onClick={() => setTable(!table)}>
              {table ? <ChartLine className="h-3.5 w-3.5" /> : <Table2 className="h-3.5 w-3.5" />}
              {table ? 'Show chart' : 'Show table'}
            </button>
          </div>

          <ul className="mt-3 space-y-1 text-sm text-pearl-muted">
            {verdict(r).map((v) => (
              <li key={v} className="flex gap-2">
                <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-ocean" />
                {v}
              </li>
            ))}
          </ul>

          {/* legend: always present for 3 series, with each line's start and end value */}
          <div className="mt-5 flex flex-wrap gap-x-6 gap-y-1 text-xs text-pearl-muted">
            {SERIES.map((s) => (
              <span key={s.key} className="flex items-center gap-2">
                <span className="h-0.5 w-4 rounded" style={{ backgroundColor: s.color }} />
                {s.name}
                {pts.length > 0 && (
                  <span className="font-mono text-pearl-dim">
                    {pct(pts[0][s.key])} → {pct(pts[pts.length - 1][s.key])}
                  </span>
                )}
              </span>
            ))}
          </div>

          {table ? (
            <table className="mt-4 w-full text-sm">
              <thead>
                <tr className="label text-left">
                  <th className="pb-2 font-medium">Modified</th>
                  {SERIES.map((s) => (
                    <th key={s.key} className="pb-2 font-medium">
                      {s.name}
                    </th>
                  ))}
                  <th className="pb-2 font-medium">Classifier says</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-midnight-800 font-mono">
                {pts.map((p) => (
                  <tr key={p.strength}>
                    <td className="py-1.5">{pct(p.strength)}</td>
                    {SERIES.map((s) => (
                      <td key={s.key} className="py-1.5">
                        {pct(p[s.key])}
                      </td>
                    ))}
                    <td className="py-1.5 font-sans text-pearl-dim">
                      {Object.keys(p.top_labels).map(titleCase).join(', ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div
              className="mt-2 h-[320px]"
              role="img"
              aria-label="Detection rates as the attack is modified"
            >
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={pts} margin={{ top: 16, right: 24, bottom: 24, left: 0 }}>
                  <CartesianGrid stroke="#122C4F" strokeWidth={1} vertical={false} />
                  <XAxis
                    dataKey="strength"
                    type="number"
                    domain={[0, 1]}
                    ticks={[0, 0.25, 0.5, 0.75, 1]}
                    tickFormatter={(v) => `${Math.round(v * 100)}%`}
                    stroke="#1b3e6e"
                    tick={{ fill: '#9c9a88', fontSize: 11 }}
                    tickLine={false}
                    label={{
                      value: 'How much the attack is disguised',
                      position: 'insideBottom',
                      offset: -14,
                      fill: '#9c9a88',
                      fontSize: 11,
                    }}
                  />
                  <YAxis
                    domain={[0, 1]}
                    ticks={[0, 0.5, 1]}
                    tickFormatter={(v) => `${Math.round(v * 100)}%`}
                    stroke="#1b3e6e"
                    tick={{ fill: '#9c9a88', fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    width={44}
                  />
                  <Tooltip
                    content={<ChartTooltip />}
                    cursor={{ stroke: '#5B88B2', strokeWidth: 1 }}
                  />
                  {SERIES.map((s) => (
                    <Line
                      key={s.key}
                      dataKey={s.key}
                      name={s.name}
                      type="linear"
                      stroke={s.color}
                      strokeWidth={2}
                      strokeLinecap="round"
                      dot={{ r: 4, fill: s.color, stroke: '#050c17', strokeWidth: 2 }}
                      activeDot={{ r: 5, fill: s.color, stroke: '#050c17', strokeWidth: 2 }}
                      isAnimationActive={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

/* ================================================================ page */

export function LabPage() {
  const [tab, setTab] = useState<'learn' | 'evade'>('learn');
  return (
    <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-6 p-5 lg:p-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Research lab</h1>
        <p className="mt-1 text-sm text-pearl-dim">
          Two experiments behind Ovael's research questions, run on the live models.
        </p>
      </header>
      <div className="flex gap-1" role="tablist">
        {(
          [
            ['learn', 'Does it learn?', GraduationCap],
            ['evade', 'Can it be fooled?', Swords],
          ] as const
        ).map(([id, label, Icon]) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition-colors ${
              tab === id ? 'bg-midnight-800 text-pearl' : 'text-pearl-dim hover:text-pearl'
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>
      {tab === 'learn' ? <LearningLoop /> : <Evasion />}
    </div>
  );
}
