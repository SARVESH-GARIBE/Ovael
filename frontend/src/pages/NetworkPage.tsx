import { useEffect, useMemo, useRef, useState } from 'react';
import { Play, Square, Undo2 } from 'lucide-react';
import type { LiveDetection, RiskLevel } from '../api/client';
import {
  useActions,
  useIncidents,
  useSimulator,
  useStartSimulation,
  useStats,
  useStopSimulation,
  useTaxonomy,
  useUndoAction,
} from '../api/hooks';
import { useLiveEvents } from '../api/live';
import { Stage } from '../characters/Stage';
import { Dossier } from '../components/Dossier';
import { Empty, RiskBadge, Section, Stat } from '../components/ui';
import { useReducedMotion } from '../hooks/useReducedMotion';
import { RISK_COLOR, num, timeAgo, titleCase } from '../lib/format';
import { CALM, deriveStage, type StageState } from '../lib/mood';

const SCENARIO_LABELS: Record<string, string> = {
  full_demo: 'Full demo',
  normal: 'Normal traffic',
  dos_flood: 'Flood (DoS)',
  slow_dos: 'Slowloris',
  port_scan: 'Port scan',
  brute_force: 'Brute force',
  web_attack: 'Web attack',
  novel: 'Unknown attack',
};

export function NetworkPage() {
  const reducedMotion = useReducedMotion();
  const recent = useRef<Array<{ at: number; d: LiveDetection }>>([]);
  // First detection seen per incident: it carries the SHAP reasons, and keeping it stable stops
  // the side panel from refetching on every event of a flood.
  const firstOfIncident = useRef(new Map<string, string>());
  const [stage, setStage] = useState<StageState>(CALM);
  const [selected, setSelected] = useState<string | undefined>();
  const [scenario, setScenario] = useState('full_demo');

  const incidents = useIncidents('network');
  const actions = useActions();
  const stats = useStats('network', 30);
  const sim = useSimulator();
  const start = useStartSimulation();
  const stop = useStopSimulation();
  const undo = useUndoAction();
  const { data: taxonomy } = useTaxonomy();

  const blockedIps = useMemo(
    () =>
      new Set(
        (actions.data ?? [])
          .filter((a) => a.status === 'applied' || a.status === 'simulated')
          .map((a) => a.target_ip)
      ),
    [actions.data]
  );

  useLiveEvents(['new_detection'], (e) => {
    const d = e.data as LiveDetection;
    if (d.module !== 'network') return;
    const now = Date.now();
    if (d.incident_id && !firstOfIncident.current.has(d.incident_id))
      firstOfIncident.current.set(d.incident_id, d.id);
    recent.current = [
      ...recent.current.filter((r) => now - r.at < 10_000).slice(-300),
      { at: now, d },
    ];
  });

  useEffect(() => {
    const t = setInterval(() => setStage(deriveStage(recent.current, blockedIps, Date.now())), 400);
    return () => clearInterval(t);
  }, [blockedIps]);

  // Follow the live attack unless the user picked an alert.
  const focus = stage.focus;
  const followId = focus
    ? (focus.incident_id && firstOfIncident.current.get(focus.incident_id)) || focus.id
    : undefined;
  const shownIncident = incidents.data?.find((i) => i.id === selected);
  const detectionId = selected
    ? (shownIncident?.last_detection_id ?? undefined)
    : (followId ?? incidents.data?.[0]?.last_detection_id ?? undefined);
  const shownSrc = selected
    ? shownIncident?.src_ip
    : (stage.focus?.src_ip ?? incidents.data?.[0]?.src_ip);
  const shownAction = (actions.data ?? []).find(
    (a) => a.target_ip === shownSrc && a.status !== 'undone'
  );

  const familyName = (id: string) =>
    taxonomy?.families.find((f) => f.module === 'network' && f.id === id)?.name ?? titleCase(id);
  const running = sim.data?.running;
  const by = stats.data?.by_risk_level ?? {};
  const alerts = (by.suspicious ?? 0) + (by.medium ?? 0) + (by.high ?? 0);

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-5 p-5 lg:p-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Network protection</h1>
          <p className="mt-1 text-sm text-pearl-dim">
            Flows from the sandbox, scored by both models. High risk where both agree is blocked
            automatically.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="input py-1.5"
            value={scenario}
            onChange={(e) => setScenario(e.target.value)}
            aria-label="Simulation scenario"
          >
            {(sim.data?.scenarios ?? Object.keys(SCENARIO_LABELS)).map((s) => (
              <option key={s} value={s}>
                {SCENARIO_LABELS[s] ?? titleCase(s)}
              </option>
            ))}
          </select>
          {running ? (
            <button className="btn-ghost" onClick={() => stop.mutate()}>
              <Square className="h-4 w-4" /> Stop
            </button>
          ) : (
            <button
              className="btn-primary"
              onClick={() =>
                start.mutate({ scenario, duration_s: scenario === 'full_demo' ? 45 : 20 })
              }
              disabled={start.isPending || sim.isError}
              title={
                sim.isError
                  ? 'Simulator unavailable'
                  : 'Push simulated sandbox traffic through the real pipeline'
              }
            >
              <Play className="h-4 w-4" /> Simulate
            </button>
          )}
        </div>
      </header>
      {start.error && <p className="text-sm text-risk-high">{start.error.message}</p>}

      <div className="grid grid-cols-2 gap-5 sm:grid-cols-4">
        <Stat label="Flows · 30 min" value={num(stats.data?.total ?? 0)} />
        <Stat label="Alerts" value={num(alerts)} tone={alerts ? RISK_COLOR.medium : undefined} />
        <Stat label="Open incidents" value={num(stats.data?.open_incidents ?? 0)} />
        <Stat
          label="Active blocks"
          value={num(stats.data?.active_blocks ?? 0)}
          tone={stats.data?.active_blocks ? RISK_COLOR.low : undefined}
        />
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="flex min-w-0 flex-col gap-5">
          <section className="card relative overflow-hidden">
            <div className="absolute left-5 top-4 z-10 flex items-center gap-2">
              <span className="label">Live</span>
              {stage.focus && <RiskBadge level={stage.level} />}
              {stage.family && stage.attacker !== 'idle' && (
                <span className="text-sm text-pearl-muted">{familyName(stage.family)}</span>
              )}
              {running && (
                <span className="text-xs text-risk-medium">
                  simulation · {SCENARIO_LABELS[sim.data?.phase ?? ''] ?? sim.data?.phase}
                </span>
              )}
            </div>
            <div className="h-[340px] sm:h-[380px]">
              <Stage state={stage} reducedMotion={reducedMotion} />
            </div>
            <p className="border-t border-midnight-800 px-5 py-2 text-[11px] text-pearl-dim">
              A picture of analyzed flows, not a packet capture. Unusual means unfamiliar, not
              proven malicious. Drag either character.
            </p>
          </section>

          <div className="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-2">
            <Section title="Alerts">
              {incidents.data?.length ? (
                <ul className="-mx-2 max-h-80 overflow-y-auto">
                  {incidents.data.map((i) => (
                    <li key={i.id}>
                      <button
                        onClick={() => setSelected(selected === i.id ? undefined : i.id)}
                        className={`flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-midnight-900 ${
                          selected === i.id ? 'bg-midnight-900' : ''
                        }`}
                      >
                        <span
                          className="h-2 w-2 shrink-0 rounded-full"
                          style={{ backgroundColor: RISK_COLOR[i.risk_level as RiskLevel] }}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm">{familyName(i.family)}</span>
                          <span className="block font-mono text-[11px] text-pearl-dim">
                            {i.src_ip} · {i.detection_count}× · {timeAgo(i.last_seen)}
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
                <Empty>No alerts yet.</Empty>
              )}
            </Section>

            <Section title="Defense actions">
              {actions.data?.length ? (
                <ul className="max-h-80 space-y-3 overflow-y-auto">
                  {actions.data.map((a) => (
                    <li key={a.id} className="flex items-center gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="text-sm">
                          {a.status === 'undone' ? 'Unblocked' : 'Blocked'}{' '}
                          <span className="font-mono">{a.target_ip}</span>
                        </div>
                        <div className="truncate text-[11px] text-pearl-dim">
                          {a.reason} · {timeAgo(a.created_at)}
                        </div>
                      </div>
                      {(a.status === 'applied' || a.status === 'simulated') && (
                        <button
                          className="btn-ghost px-2 py-1 text-xs"
                          onClick={() => undo.mutate(a.id)}
                          aria-label={`Undo block of ${a.target_ip}`}
                        >
                          <Undo2 className="h-3.5 w-3.5" /> Undo
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty>
                  No blocks. Auto-defense fires only on high risk where both models agree.
                </Empty>
              )}
            </Section>
          </div>
        </div>

        <div className="xl:sticky xl:top-6 xl:h-[calc(100vh-3rem)]">
          <Dossier
            detectionId={detectionId}
            module="network"
            live={!selected && stage.attacker === 'attacking'}
            action={shownAction}
          />
        </div>
      </div>
    </div>
  );
}
