import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  CircleHelp,
  CodeXml,
  Eraser,
  Hourglass,
  KeyRound,
  Radar,
  Sparkles,
  Square,
  Undo2,
  Waves,
  type LucideIcon,
} from 'lucide-react';
import type { LiveDetection, RiskLevel } from '../api/client';
import {
  useActions,
  useDetection,
  useFamily,
  useIncidents,
  useModelSchema,
  useSimulator,
  useStartSimulation,
  useStats,
  useStopSimulation,
  useTaxonomy,
  useUndoAction,
} from '../api/hooks';
import { useLiveEvents } from '../api/live';
import { Stage } from '../characters/Stage';
import { AttackJourney } from '../components/AttackJourney';
import { Empty, RiskBadge } from '../components/ui';
import { useReducedMotion } from '../hooks/useReducedMotion';
import { RISK_COLOR, num, timeAgo, titleCase } from '../lib/format';
import { CALM, deriveStage, type StageState } from '../lib/mood';

const SCENARIOS: Array<{ id: string; label: string; icon: LucideIcon; seconds: number }> = [
  { id: 'full_demo', label: 'Full demo', icon: Sparkles, seconds: 45 },
  { id: 'dos_flood', label: 'Flood', icon: Waves, seconds: 20 },
  { id: 'port_scan', label: 'Port scan', icon: Radar, seconds: 20 },
  { id: 'slow_dos', label: 'Slowloris', icon: Hourglass, seconds: 20 },
  { id: 'brute_force', label: 'Brute force', icon: KeyRound, seconds: 20 },
  { id: 'web_attack', label: 'Web attack', icon: CodeXml, seconds: 20 },
  { id: 'novel', label: 'Unknown', icon: CircleHelp, seconds: 20 },
  { id: 'normal', label: 'Normal', icon: Activity, seconds: 20 },
];

const RECENT_MS = 30 * 60 * 1000; // older alerts are history, not "what is happening"
const PIN_MS = 16_000; // a full walk-through is 5 steps x 2.8 s
const LEVEL_ORDER: Record<RiskLevel, number> = { low: 0, suspicious: 1, medium: 2, high: 3 };

function caption(
  state: StageState,
  familyName: string | undefined,
  summary: string | undefined
): string {
  if (state.blocked)
    return `Blocked. Packets from ${state.focus?.src_ip ?? 'the attacker'} are now dropped.`;
  if (state.attacker === 'attacking') return `${familyName ?? 'Attack'}: ${summary ?? ''}`;
  if (state.attacker === 'sneaky') return 'Something unfamiliar. Saved for a person to review.';
  return 'Normal traffic. Both models agree it looks fine.';
}

export function NetworkPage() {
  const reducedMotion = useReducedMotion();
  const recent = useRef<Array<{ at: number; d: LiveDetection }>>([]);
  // First detection per incident: it carries the SHAP reasons, and keeping it stable stops the
  // journey from restarting on every event of a flood.
  const firstOfIncident = useRef(new Map<string, string>());
  const [stage, setStage] = useState<StageState>(CALM);
  const [selected, setSelected] = useState<string | undefined>();
  const [now, setNow] = useState(Date.now());

  const incidents = useIncidents('network');
  const actions = useActions();
  const stats = useStats('network', 30);
  const sim = useSimulator();
  const start = useStartSimulation();
  const stop = useStopSimulation();
  const undo = useUndoAction();
  const schema = useModelSchema('network');
  const { data: taxonomy } = useTaxonomy();

  const activeBlocks = useMemo(
    () => (actions.data ?? []).filter((a) => a.status === 'applied' || a.status === 'simulated'),
    [actions.data]
  );
  const blockedIps = useMemo(() => new Set(activeBlocks.map((a) => a.target_ip)), [activeBlocks]);

  useLiveEvents(['new_detection'], (e) => {
    const d = e.data as LiveDetection;
    if (d.module !== 'network') return;
    const t = Date.now();
    if (d.incident_id && !firstOfIncident.current.has(d.incident_id))
      firstOfIncident.current.set(d.incident_id, d.id);
    recent.current = [...recent.current.filter((r) => t - r.at < 10_000).slice(-300), { at: t, d }];
  });

  useEffect(() => {
    const t = setInterval(() => {
      const n = Date.now();
      setNow(n);
      setStage(deriveStage(recent.current, blockedIps, n));
    }, 400);
    return () => clearInterval(t);
  }, [blockedIps]);

  const recentIncidents = (incidents.data ?? []).filter(
    (i) => now - new Date(i.last_seen).getTime() < RECENT_MS
  );
  const selectedIncident = recentIncidents.find((i) => i.id === selected);

  // What the journey explains: the incident the user picked, else the attack it is pinned to.
  // The pin only moves to a more serious attack, or after the current one has played out, so a
  // stray "unusual" flow never interrupts a flood's walk-through.
  const focus = stage.focus;
  const [pin, setPin] = useState<{
    incident: string;
    detection: string;
    level: number;
    at: number;
  }>();
  useEffect(() => {
    if (!focus) return;
    const level = LEVEL_ORDER[focus.risk_level as RiskLevel];
    const incident = focus.incident_id ?? focus.id;
    const detection = firstOfIncident.current.get(incident) ?? focus.id;
    setPin((p) =>
      !p || level > p.level || (incident !== p.incident && Date.now() - p.at > PIN_MS)
        ? { incident, detection, level, at: Date.now() }
        : p
    );
  }, [focus]);
  const journeyId = selectedIncident
    ? (selectedIncident.last_detection_id ?? undefined)
    : (pin?.detection ?? recentIncidents[0]?.last_detection_id ?? undefined);
  const journeyKey = selectedIncident?.id ?? pin?.incident ?? journeyId ?? 'none';
  const detection = useDetection(journeyId);
  const journeyFamily = useFamily('network', detection.data?.family);
  const journeyAction = (actions.data ?? []).find(
    (a) => a.target_ip === detection.data?.src_ip && a.status !== 'undone'
  );

  const stageFamily = taxonomy?.families.find(
    (f) => f.module === 'network' && f.id === stage.family
  );
  const familyName = (id: string) =>
    taxonomy?.families.find((f) => f.module === 'network' && f.id === id)?.name ?? titleCase(id);
  const running = Boolean(sim.data?.running);
  const by = stats.data?.by_risk_level ?? {};
  const alerts = (by.suspicious ?? 0) + (by.medium ?? 0) + (by.high ?? 0);

  const run = (id: string, seconds: number) => {
    setSelected(undefined);
    setPin(undefined);
    start.mutate({ scenario: id, duration_s: seconds });
  };
  const clearBlocks = async () => {
    for (const a of activeBlocks) await undo.mutateAsync(a.id).catch(() => undefined);
  };

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-5 p-5 lg:p-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Network protection</h1>
        <p className="mt-1 text-sm text-pearl-dim">
          Pick an attack. Watch it arrive, get measured, judged by two models, and stopped.
        </p>
      </header>

      {/* one-click scenarios */}
      <div
        className="flex flex-wrap items-center gap-2"
        role="toolbar"
        aria-label="Simulate traffic"
      >
        {SCENARIOS.map(({ id, label, icon: Icon, seconds }) => {
          const on = running && sim.data?.scenario === id;
          return (
            <button
              key={id}
              onClick={() => run(id, seconds)}
              disabled={start.isPending || sim.isError}
              className={`flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-sm transition-all duration-200 disabled:opacity-40 ${
                on
                  ? 'border-pearl bg-pearl text-noir'
                  : id === 'full_demo'
                    ? 'border-ocean text-pearl hover:bg-ocean/15'
                    : 'border-midnight-700 text-pearl-muted hover:border-ocean hover:text-pearl'
              }`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          );
        })}
        {running && (
          <button className="btn-ghost rounded-full" onClick={() => stop.mutate()}>
            <Square className="h-3.5 w-3.5" /> Stop
          </button>
        )}
        {sim.isError && <span className="text-xs text-risk-high">Simulator unavailable</span>}
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-5">
          {/* stage */}
          <section className="card overflow-hidden">
            <div className="flex items-center gap-2 px-5 pt-4">
              <span className="relative flex h-2 w-2">
                {running && (
                  <span className="absolute inset-0 rounded-full bg-risk-high animate-ping2" />
                )}
                <span
                  className={`relative h-2 w-2 rounded-full ${running ? 'bg-risk-high' : 'bg-ocean'}`}
                />
              </span>
              <span className="label">{running ? 'Simulation running' : 'Live'}</span>
              {stage.focus && <RiskBadge level={stage.level} />}
            </div>
            <div className="h-[220px] sm:h-[370px]">
              <Stage state={stage} reducedMotion={reducedMotion} />
            </div>
            <p className="border-t border-midnight-800 px-5 py-3 text-sm text-pearl-muted transition-all duration-300">
              {caption(stage, stageFamily?.name, stageFamily?.summary)}
            </p>
          </section>

          {/* journey */}
          {detection.data ? (
            <AttackJourney
              detection={detection.data}
              family={journeyFamily}
              schema={schema.data}
              action={journeyAction}
              playKey={journeyKey}
              onUndo={(id) => undo.mutate(id)}
              undoing={undo.isPending}
            />
          ) : (
            <section className="card flex flex-col items-center p-10 text-center">
              <Sparkles className="h-6 w-6 text-ocean" />
              <p className="mt-3 font-medium">See an attack end to end</p>
              <p className="mt-1 max-w-md text-sm text-pearl-dim">
                Start with <span className="text-pearl">Full demo</span>. Each attack is walked
                through packets, flow, features, models and the final decision.
              </p>
              <button
                className="btn-primary mt-5"
                onClick={() => run('full_demo', 45)}
                disabled={start.isPending}
              >
                <Sparkles className="h-4 w-4" /> Run full demo
              </button>
            </section>
          )}
        </div>

        {/* side column */}
        <aside className="flex min-w-0 flex-col gap-5">
          <div className="card grid grid-cols-2 gap-4 p-5">
            {[
              ['Flows · 30 min', num(stats.data?.total ?? 0), undefined],
              ['Alerts', num(alerts), alerts ? RISK_COLOR.medium : undefined],
              ['Open incidents', num(stats.data?.open_incidents ?? 0), undefined],
              [
                'Blocked now',
                num(activeBlocks.length),
                activeBlocks.length ? RISK_COLOR.low : undefined,
              ],
            ].map(([label, value, tone]) => (
              <div key={label}>
                <div className="label">{label}</div>
                <div
                  className="mt-1 text-2xl font-semibold tabular-nums"
                  style={tone ? { color: tone } : undefined}
                >
                  {value}
                </div>
              </div>
            ))}
          </div>

          <section className="card p-5">
            <h2 className="label mb-3">Alerts · last 30 min</h2>
            {recentIncidents.length ? (
              <ul className="-mx-2 max-h-[340px] space-y-0.5 overflow-y-auto">
                {recentIncidents.map((i) => (
                  <li key={i.id}>
                    <button
                      onClick={() => setSelected(selected === i.id ? undefined : i.id)}
                      className={`flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors duration-200 hover:bg-midnight-900 ${
                        selected === i.id ? 'bg-midnight-900 ring-1 ring-ocean/50' : ''
                      }`}
                    >
                      <span
                        className="h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: RISK_COLOR[i.risk_level as RiskLevel] }}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm">{familyName(i.family)}</span>
                        <span className="block font-mono text-[11px] text-pearl-dim">
                          {i.src_ip} · {i.detection_count}× · {timeAgo(i.last_seen, now)}
                        </span>
                      </span>
                      {i.status === 'mitigated' && (
                        <span className="text-[11px] text-ocean">blocked</span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>Quiet. Run a scenario above.</Empty>
            )}
            {selected && (
              <button
                className="mt-3 text-xs text-ocean hover:underline"
                onClick={() => setSelected(undefined)}
              >
                Back to live
              </button>
            )}
          </section>

          <section className="card p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="label">Blocked sources</h2>
              {activeBlocks.length > 1 && (
                <button
                  className="text-xs text-pearl-dim hover:text-pearl"
                  onClick={clearBlocks}
                  disabled={undo.isPending}
                >
                  <Eraser className="mr-1 inline h-3.5 w-3.5" />
                  Unblock all
                </button>
              )}
            </div>
            {activeBlocks.length ? (
              <ul className="space-y-2.5">
                {activeBlocks.map((a) => (
                  <li key={a.id} className="flex items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="font-mono text-sm">{a.target_ip}</div>
                      <div className="truncate text-[11px] text-pearl-dim">
                        {a.reason.split(':')[0]} · {timeAgo(a.created_at, now)}
                      </div>
                    </div>
                    <button
                      className="btn-ghost px-2 py-1 text-xs"
                      onClick={() => undo.mutate(a.id)}
                      aria-label={`Unblock ${a.target_ip}`}
                    >
                      <Undo2 className="h-3.5 w-3.5" /> Undo
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>Nothing blocked.</Empty>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
