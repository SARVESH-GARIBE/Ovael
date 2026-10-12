import { useEffect, useState, type ReactNode } from 'react';
import {
  Ban,
  Bell,
  Binary,
  BrainCircuit,
  Inbox,
  Package,
  RotateCcw,
  ShieldCheck,
  Undo2,
  Workflow,
} from 'lucide-react';
import type { AttackFamily, DefenseAction, DetectionDetail, RiskLevel } from '../api/client';
import type { ModelSchema } from '../api/hooks';
import { RISK_COLOR, RISK_LABEL, num, pct, protocolName, titleCase } from '../lib/format';
import { RiskGauge } from './ui';

/**
 * The life of one detection, in five steps:
 *   packets -> flow (5-tuple) -> features (schema) -> two models -> decision + defense
 * Every number on screen comes from the stored detection, the active model's schema and its
 * baseline. It plays itself when a new attack arrives; each step can also be opened by hand.
 */

const STEPS = [
  { id: 'packets', label: 'Packets', icon: Package },
  { id: 'flow', label: 'Flow', icon: Workflow },
  { id: 'features', label: 'Features', icon: Binary },
  { id: 'models', label: 'Models', icon: BrainCircuit },
  { id: 'decision', label: 'Decision', icon: ShieldCheck },
] as const;

const STEP_MS = 2800;
const MAX_CHIPS = 18;

type Feats = Record<string, number | null | undefined>;

function StepTitle({ n, title, line }: { n: number; title: string; line: string }) {
  return (
    <div className="mb-5">
      <div className="label">Step {n} of 5</div>
      <h3 className="mt-1 text-lg font-semibold">{title}</h3>
      <p className="mt-0.5 text-sm text-pearl-dim">{line}</p>
    </div>
  );
}

/* ---------------------------------------------------------------- 1. packets */

function packetChips(f: Feats): Array<{ dir: 'out' | 'in'; flag: string }> {
  const fwd = Math.round(f.total_fwd_packets ?? 0);
  const bwd = Math.round(f.total_bwd_packets ?? 0);
  const flags: string[] = [];
  const add = (letter: string, n: number | null | undefined) => {
    for (let i = 0; i < Math.round(n ?? 0); i++) flags.push(letter);
  };
  add('S', f.syn_flag_count);
  add('P', f.psh_flag_count);
  add('F', f.fin_flag_count);
  add('R', f.rst_flag_count);
  const out = Array.from({ length: Math.min(fwd, MAX_CHIPS) }, (_, i) => ({
    dir: 'out' as const,
    flag: flags[i] ?? 'A',
  }));
  const back = Array.from({ length: Math.min(bwd, MAX_CHIPS) }, () => ({
    dir: 'in' as const,
    flag: '↩',
  }));
  // interleave roughly the way a conversation looks on the wire
  const merged: Array<{ dir: 'out' | 'in'; flag: string }> = [];
  for (let i = 0; i < Math.max(out.length, back.length); i++) {
    if (out[i]) merged.push(out[i]);
    if (back[i]) merged.push(back[i]);
  }
  return merged;
}

function PacketsStep({
  d,
  family,
  color,
}: {
  d: DetectionDetail;
  family?: AttackFamily;
  color: string;
}) {
  const f = d.features as Feats;
  const chips = packetChips(f);
  const fwd = Math.round(f.total_fwd_packets ?? 0);
  const bwd = Math.round(f.total_bwd_packets ?? 0);
  const hidden = fwd + bwd - chips.length;
  return (
    <>
      <StepTitle
        n={1}
        title="Packets hit the network"
        line={
          family?.is_benign
            ? 'A normal client talks to the server.'
            : (family?.how_it_works[0] ?? 'Traffic arrives at the victim.')
        }
      />
      <div className="flex flex-wrap items-center gap-1.5">
        {chips.map((c, i) => (
          <span
            key={i}
            className="flex h-8 w-8 items-center justify-center rounded-md font-mono text-xs font-semibold animate-slidein"
            style={{
              animationDelay: `${i * 70}ms`,
              backgroundColor: c.dir === 'out' ? `${color}26` : '#5B88B226',
              color: c.dir === 'out' ? color : '#7ea4cb',
              border: `1px solid ${c.dir === 'out' ? color : '#5B88B2'}55`,
            }}
            title={c.dir === 'out' ? 'sent by the source' : 'reply from the victim'}
          >
            {c.flag}
          </span>
        ))}
        {hidden > 0 && <span className="text-xs text-pearl-dim">+{num(hidden)} more</span>}
      </div>
      {(f.src_conn_rate_10s ?? 0) > 20 && (
        <div className="mt-5">
          <div className="flex items-baseline justify-between text-xs">
            <span className="text-pearl-muted">Same source, last 10 seconds</span>
            <span className="font-mono" style={{ color }}>
              {num(f.src_conn_rate_10s)} connections
            </span>
          </div>
          <div className="mt-2 flex flex-wrap gap-[3px]" aria-hidden>
            {Array.from({ length: Math.min(Math.round(f.src_conn_rate_10s ?? 0), 160) }, (_, i) => (
              <span
                key={i}
                className="h-1.5 w-1.5 rounded-full animate-pop"
                style={{
                  backgroundColor: color,
                  animationDelay: `${300 + i * 8}ms`,
                  opacity: 0.85,
                }}
              />
            ))}
          </div>
        </div>
      )}
      <div className="mt-5 grid grid-cols-3 gap-4 text-sm">
        <div>
          <div className="label">Sent</div>
          <div className="mt-1 font-mono text-lg">{num(fwd)}</div>
        </div>
        <div>
          <div className="label">Replies</div>
          <div className="mt-1 font-mono text-lg">{num(bwd)}</div>
        </div>
        <div>
          <div className="label">Avg size</div>
          <div className="mt-1 font-mono text-lg">{num(f.fwd_pkt_len_mean)} B</div>
        </div>
      </div>
      <p className="mt-5 text-[11px] text-pearl-dim">
        S = SYN (open) · A = ACK · P = data · F = FIN (close) · R = RST (refused) · ↩ = reply.
        Drawn from the flow's packet counters.
      </p>
    </>
  );
}

/* ---------------------------------------------------------------- 2. flow */

function FlowStep({ d }: { d: DetectionDetail }) {
  const f = d.features as Feats;
  const tuple = [
    ['Source', d.src_ip ?? '—'],
    ['Src port', d.src_port ?? '—'],
    ['Destination', d.dst_ip ?? '—'],
    ['Dst port', d.dst_port ?? f.dst_port ?? '—'],
    ['Protocol', protocolName(d.protocol ?? f.protocol) || '—'],
  ];
  return (
    <>
      <StepTitle
        n={2}
        title="Grouped into one flow"
        line="Packets that share the same 5-tuple are one conversation. It is summarised when it ends or gets too long."
      />
      <div className="flex flex-wrap items-stretch gap-2">
        {tuple.map(([k, v], i) => (
          <div
            key={k}
            className="min-w-[110px] flex-1 rounded-xl border border-midnight-700 bg-noir px-3 py-2.5 animate-rise"
            style={{ animationDelay: `${i * 90}ms` }}
          >
            <div className="text-[11px] text-pearl-dim">{k}</div>
            <div className="mt-0.5 font-mono text-sm">{String(v)}</div>
          </div>
        ))}
      </div>
      <div className="mt-5 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
        <div>
          <div className="label">Duration</div>
          <div className="mt-1 font-mono">{num(f.flow_duration)} s</div>
        </div>
        <div>
          <div className="label">Packets / s</div>
          <div className="mt-1 font-mono">{num(f.flow_pkts_per_s)}</div>
        </div>
        <div>
          <div className="label">Bytes</div>
          <div className="mt-1 font-mono">
            {num((f.total_fwd_bytes ?? 0) + (f.total_bwd_bytes ?? 0))}
          </div>
        </div>
        <div>
          <div className="label">Source, last 10 s</div>
          <div className="mt-1 font-mono">
            {num(f.src_conn_rate_10s)} conns · {num(f.src_distinct_dst_ports_10s)} ports
          </div>
        </div>
      </div>
    </>
  );
}

/* ---------------------------------------------------------------- 3. features */

function FeaturesStep({
  d,
  schema,
  color,
}: {
  d: DetectionDetail;
  schema?: ModelSchema;
  color: string;
}) {
  const f = d.features as Feats;
  const top = new Set(d.top_features.map((t) => t.feature));
  const rows = (
    schema?.features ??
    Object.keys(f).map((name) => ({ name, description: titleCase(name), baseline: null }))
  )
    .slice()
    .sort((a, b) => Number(top.has(b.name)) - Number(top.has(a.name)));
  return (
    <>
      <StepTitle
        n={3}
        title={`Turned into ${rows.length} numbers`}
        line="The flow becomes the feature schema the models were trained on. Highlighted ones mattered most."
      />
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {rows.map((r, i) => {
          const hot = top.has(r.name);
          const v = f[r.name];
          return (
            <div
              key={r.name}
              className={`rounded-lg border px-2.5 py-2 animate-rise ${hot ? '' : 'border-midnight-800 opacity-70'}`}
              style={{
                animationDelay: `${i * 25}ms`,
                borderColor: hot ? `${color}aa` : undefined,
                backgroundColor: hot ? `${color}12` : undefined,
              }}
            >
              <div className="truncate text-[11px] text-pearl-dim" title={r.description}>
                {r.description}
              </div>
              <div className="mt-0.5 flex items-baseline justify-between gap-2">
                <span className="font-mono text-sm">{num(v)}</span>
                {r.baseline != null && (
                  <span className="font-mono text-[10px] text-pearl-dim">
                    normal {num(r.baseline)}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

/* ---------------------------------------------------------------- 4. models */

function ModelsStep({
  d,
  schema,
  color,
}: {
  d: DetectionDetail;
  schema?: ModelSchema;
  color: string;
}) {
  const probs = Object.entries(d.probabilities as Record<string, number>)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4);
  const threshold = schema?.threshold ?? 0.99;
  return (
    <>
      <StepTitle
        n={4}
        title="Two models look at it"
        line="One knows the attacks it was taught. The other only knows what normal looks like."
      />
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-midnight-700 p-4 animate-rise">
          <div className="label">Random Forest · known attacks</div>
          <div className="mt-2 text-xl font-semibold">
            {d.is_attack
              ? titleCase(d.label)
              : d.label === 'benign'
                ? 'Normal'
                : `Unsure (${titleCase(d.label)}?)`}
          </div>
          <div className="text-sm text-pearl-dim">{pct(d.confidence)} sure</div>
          <div className="mt-4 space-y-2">
            {probs.map(([label, p], i) => (
              <div key={label} className="text-xs">
                <div className="flex justify-between">
                  <span className="text-pearl-muted">{titleCase(label)}</span>
                  <span className="font-mono">{pct(p)}</span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-midnight-800">
                  <div
                    className="h-full origin-left rounded-full animate-grow"
                    style={{
                      width: `${p * 100}%`,
                      backgroundColor: i === 0 ? color : '#5B88B2',
                      animationDelay: `${150 + i * 80}ms`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div
          className="rounded-xl border border-midnight-700 p-4 animate-rise"
          style={{ animationDelay: '120ms' }}
        >
          <div className="label">Isolation Forest · normal behaviour</div>
          <div className="mt-2 text-xl font-semibold">
            {d.is_unusual ? 'Unusual' : 'Looks normal'}
          </div>
          <div className="text-sm text-pearl-dim">
            More unusual than {pct(d.anomaly_score)} of normal traffic
          </div>
          <div className="relative mt-6 h-2 rounded-full bg-midnight-800">
            <div
              className="h-full origin-left rounded-full animate-grow"
              style={{
                width: `${d.anomaly_score * 100}%`,
                backgroundColor: d.is_unusual ? RISK_COLOR.suspicious : '#5B88B2',
                animationDelay: '250ms',
              }}
            />
            <div
              className="absolute -top-1.5 h-5 w-0.5 bg-pearl"
              style={{ left: `${threshold * 100}%` }}
            />
            <div
              className="absolute -top-6 -translate-x-full font-mono text-[10px] text-pearl-dim"
              style={{ left: `${threshold * 100}%` }}
            >
              line {threshold}
            </div>
          </div>
          <div className="mt-2 flex justify-between font-mono text-[10px] text-pearl-dim">
            <span>0 normal</span>
            <span>1 never seen</span>
          </div>
        </div>
      </div>
    </>
  );
}

/* ---------------------------------------------------------------- 5. decision */

const ROWS: Array<{ attack: boolean; unusual: boolean; level: RiskLevel; action: string }> = [
  { attack: true, unusual: true, level: 'high', action: 'Alert + auto-block' },
  { attack: true, unusual: false, level: 'medium', action: 'Alert' },
  { attack: false, unusual: true, level: 'suspicious', action: 'Alert + human review' },
  { attack: false, unusual: false, level: 'low', action: 'Nothing' },
];

function Outcome({
  d,
  action,
  onUndo,
  undoing,
}: {
  d: DetectionDetail;
  action?: DefenseAction;
  onUndo: (id: string) => void;
  undoing: boolean;
}) {
  const blocked = action && (action.status === 'applied' || action.status === 'simulated');
  const level = d.risk_level as RiskLevel;
  let icon: ReactNode, title: string, line: string;
  if (blocked) {
    icon = <Ban className="h-5 w-5" />;
    const persistent = action!.reason.includes('persistent');
    title = persistent
      ? `Blocked ${action!.target_ip} (persistence rule)`
      : `Blocked ${action!.target_ip}`;
    line =
      (persistent
        ? `No single flow was unusual, but the source kept attacking: ${action!.reason.split(': ').slice(1).join(': ')}. `
        : '') +
      (action!.mode === 'simulate'
        ? 'Firewall rule simulated in the sandbox.'
        : 'Firewall rule added in the victim container.');
  } else if (level === 'high' || level === 'medium') {
    icon = <Bell className="h-5 w-5" />;
    title = 'Alert raised';
    line =
      level === 'high'
        ? 'High risk. Blocking needs the source inside the sandbox.'
        : 'Known attack, but not unusual enough to block automatically.';
  } else if (level === 'suspicious') {
    icon = <Inbox className="h-5 w-5" />;
    title = 'Sent to the review queue';
    line = 'A person labels it, and the next model learns from it.';
  } else {
    icon = <ShieldCheck className="h-5 w-5" />;
    title = 'No action';
    line = 'Both models agree it is normal.';
  }
  return (
    <div
      className="rounded-xl border p-4 animate-rise"
      style={{ borderColor: `${RISK_COLOR[level]}66`, animationDelay: '200ms' }}
    >
      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 rounded-lg p-2"
          style={{ backgroundColor: `${RISK_COLOR[level]}22`, color: RISK_COLOR[level] }}
        >
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-semibold">{title}</div>
          <div className="text-sm text-pearl-dim">{line}</div>
        </div>
        {blocked && (
          <button
            className="btn-ghost shrink-0 px-2 py-1 text-xs"
            onClick={() => onUndo(action!.id)}
            disabled={undoing}
          >
            <Undo2 className="h-3.5 w-3.5" /> Undo
          </button>
        )}
      </div>
    </div>
  );
}

function DecisionStep(props: {
  d: DetectionDetail;
  family?: AttackFamily;
  action?: DefenseAction;
  onUndo: (id: string) => void;
  undoing: boolean;
}) {
  const { d, family } = props;
  const level = d.risk_level as RiskLevel;
  return (
    <>
      <StepTitle
        n={5}
        title="Decision and defense"
        line="Both answers go into one table. The row decides the risk and what happens next."
      />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_260px]">
        <div className="space-y-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="label text-left">
                <th className="pb-2 font-medium">Classifier</th>
                <th className="pb-2 font-medium">Anomaly</th>
                <th className="pb-2 font-medium">Risk</th>
                <th className="pb-2 font-medium">Then</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((r) => {
                const hit = r.attack === d.is_attack && r.unusual === d.is_unusual;
                return (
                  <tr
                    key={r.level}
                    className={`transition-colors duration-500 ${hit ? '' : 'opacity-35'}`}
                    style={hit ? { backgroundColor: `${RISK_COLOR[r.level]}1f` } : undefined}
                  >
                    <td className="rounded-l-lg px-2 py-2">{r.attack ? 'Attack' : 'Normal'}</td>
                    <td className="px-2 py-2">{r.unusual ? 'Unusual' : 'Normal'}</td>
                    <td className="px-2 py-2 font-semibold" style={{ color: RISK_COLOR[r.level] }}>
                      {RISK_LABEL[r.level]}
                    </td>
                    <td className="rounded-r-lg px-2 py-2 text-pearl-muted">{r.action}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="-mt-2 text-[11px] text-pearl-dim">
            Plus the persistence rule: a Medium attack repeated 20 times from one source within 60 s
            is escalated to High.
          </p>
          <Outcome d={d} action={props.action} onUndo={props.onUndo} undoing={props.undoing} />
          {family && family.mitigations.length > 0 && !family.is_benign && (
            <p className="text-xs text-pearl-dim">
              <span className="text-pearl-muted">Long-term fix: </span>
              {family.mitigations.slice(0, 3).join(' · ')}
            </p>
          )}
        </div>
        <div className="flex flex-col items-center justify-center">
          <RiskGauge score={d.risk_score} level={level} size={210} />
          {family && family.severity_weight > 0 && (
            <p className="mt-1 text-center text-[11px] text-pearl-dim">
              severity weight {family.severity_weight.toFixed(2)} × confidence {pct(d.confidence)}
            </p>
          )}
        </div>
      </div>
    </>
  );
}

/* ---------------------------------------------------------------- shell */

export function AttackJourney({
  detection: d,
  family,
  schema,
  action,
  playKey,
  onUndo,
  undoing = false,
}: {
  detection: DetectionDetail;
  family?: AttackFamily;
  schema?: ModelSchema;
  action?: DefenseAction;
  playKey: string; // a new key restarts the walk-through
  onUndo: (id: string) => void;
  undoing?: boolean;
}) {
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(true);

  useEffect(() => {
    setStep(0);
    setPlaying(true);
  }, [playKey]);

  useEffect(() => {
    if (!playing) return;
    if (step >= STEPS.length - 1) {
      setPlaying(false);
      return;
    }
    const t = setTimeout(() => setStep((s) => s + 1), STEP_MS);
    return () => clearTimeout(t);
  }, [playing, step]);

  const level = d.risk_level as RiskLevel;
  const color = RISK_COLOR[level];

  return (
    <section className="card p-5 sm:p-6" aria-label="How this detection was made">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="label">Attack journey</div>
          <div className="mt-1 truncate font-semibold">{family?.name ?? titleCase(d.label)}</div>
        </div>
        <button
          className="btn-ghost px-2.5 py-1 text-xs"
          onClick={() => {
            setStep(0);
            setPlaying(true);
          }}
        >
          <RotateCcw className="h-3.5 w-3.5" /> Replay
        </button>
      </div>

      {/* stepper */}
      <ol className="relative mt-6 grid grid-cols-5">
        <div
          className="absolute left-[10%] right-[10%] top-[18px] h-0.5 bg-midnight-800"
          aria-hidden
        />
        <div
          className="absolute left-[10%] top-[18px] h-0.5 transition-all duration-700 ease-out"
          style={{ width: `${(step / (STEPS.length - 1)) * 80}%`, backgroundColor: color }}
          aria-hidden
        />
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          const done = i < step;
          const active = i === step;
          return (
            <li key={s.id} className="relative flex flex-col items-center">
              <button
                onClick={() => {
                  setStep(i);
                  setPlaying(false);
                }}
                aria-current={active ? 'step' : undefined}
                aria-label={`Step ${i + 1}: ${s.label}`}
                className="relative flex h-9 w-9 items-center justify-center rounded-full border-2 transition-all duration-300"
                style={{
                  borderColor: done || active ? color : '#1b3e6e',
                  backgroundColor: active ? color : done ? `${color}33` : '#050c17',
                  color: active ? '#000' : done ? color : '#9c9a88',
                }}
              >
                {active && playing && (
                  <span
                    className="absolute inset-0 rounded-full animate-ping2"
                    style={{ backgroundColor: color }}
                    aria-hidden
                  />
                )}
                <Icon className="relative h-4 w-4" />
              </button>
              <span
                className={`mt-2 text-[11px] sm:text-xs ${active ? 'text-pearl' : done ? 'text-pearl-muted' : 'text-pearl-dim'}`}
              >
                {s.label}
              </span>
            </li>
          );
        })}
      </ol>

      <div key={`${playKey}-${step}`} className="mt-7 min-h-[260px] animate-fadein">
        {step === 0 && <PacketsStep d={d} family={family} color={color} />}
        {step === 1 && <FlowStep d={d} />}
        {step === 2 && <FeaturesStep d={d} schema={schema} color={color} />}
        {step === 3 && <ModelsStep d={d} schema={schema} color={color} />}
        {step === 4 && (
          <DecisionStep d={d} family={family} action={action} onUndo={onUndo} undoing={undoing} />
        )}
      </div>
    </section>
  );
}
