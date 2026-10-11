import { useEffect, useState } from 'react';
import { ShieldCheck, Undo2 } from 'lucide-react';
import type { DefenseAction, Module, RiskLevel } from '../api/client';
import { useDetection, useFamily, useUndoAction } from '../api/hooks';
import { pct, protocolName, titleCase } from '../lib/format';
import { Chip, Empty, FeatureReasons, RiskBadge, RiskGauge, Steps } from './ui';

/**
 * Side panel explaining one detection: what the attack is, how it works step by step, how the
 * score was reached, which features gave it away, and what stops it.
 */
export function Dossier({
  detectionId,
  module,
  live,
  action,
}: {
  detectionId: string | undefined;
  module: Module;
  live: boolean; // attack still in progress: animate the "how it works" steps
  action?: DefenseAction;
}) {
  const { data: d, isLoading } = useDetection(detectionId);
  const family = useFamily(module, d?.family);
  const undo = useUndoAction();
  const [step, setStep] = useState(0);
  const steps = family?.how_it_works ?? [];

  useEffect(() => {
    if (!live || steps.length < 2) return;
    const t = setInterval(() => setStep((s) => (s + 1) % steps.length), 1600);
    return () => clearInterval(t);
  }, [live, steps.length]);

  if (!detectionId) {
    return (
      <div className="card flex h-full flex-col items-center justify-center p-8 text-center">
        <ShieldCheck className="mb-3 h-8 w-8 text-ocean" />
        <p className="font-medium">All quiet</p>
        <p className="mt-1 text-sm text-pearl-dim">
          Pick an alert, or run a scenario, to see how an attack works.
        </p>
      </div>
    );
  }
  if (isLoading || !d)
    return (
      <div className="card h-full p-6">
        <Empty>Loading…</Empty>
      </div>
    );

  const level = d.risk_level as RiskLevel;
  const b = d.breakdown as Record<string, string | number>;
  const blocked = action && ['applied', 'simulated'].includes(action.status);

  return (
    <aside
      className="card flex h-full flex-col gap-6 overflow-y-auto p-6 animate-fadein"
      aria-label="Attack details"
    >
      <header>
        <div className="flex items-center justify-between gap-2">
          <RiskBadge level={level} />
          <span className="font-mono text-[11px] text-pearl-dim">{d.model_version}</span>
        </div>
        <h2 className="mt-3 text-xl font-semibold leading-tight">
          {family?.name ?? titleCase(d.label)}
        </h2>
        {family?.summary && <p className="mt-1 text-sm text-pearl-muted">{family.summary}</p>}
        <div className="mt-3 flex flex-wrap gap-1.5">
          {family?.kill_chain && <Chip>{family.kill_chain}</Chip>}
          {family?.mitre.map((m) => <Chip key={m}>{m}</Chip>)}
          {d.origin === 'simulated' && <Chip tone="warn">simulated traffic</Chip>}
        </div>
      </header>

      <div className="flex items-center gap-5">
        <RiskGauge score={d.risk_score} level={level} size={150} />
        <dl className="space-y-1.5 text-sm">
          <div>
            <dt className="label">Classifier</dt>
            <dd>
              {b.classifier_says === 'attack' ? titleCase(d.label) : 'Normal'}{' '}
              <span className="text-pearl-dim">· {pct(d.confidence)}</span>
            </dd>
          </div>
          <div>
            <dt className="label">Anomaly detector</dt>
            <dd>
              {b.anomaly_detector_says === 'unusual' ? 'Unusual' : 'Normal'}{' '}
              <span className="text-pearl-dim">· {pct(d.anomaly_score)}</span>
            </dd>
          </div>
          {family && family.severity_weight > 0 && (
            <div>
              <dt className="label">Severity weight</dt>
              <dd className="font-mono">{family.severity_weight.toFixed(2)}</dd>
            </div>
          )}
        </dl>
      </div>

      {steps.length > 0 && (
        <div>
          <h3 className="label mb-3">How it's attacking</h3>
          <Steps steps={steps} active={live ? step : undefined} />
        </div>
      )}

      <div>
        <h3 className="label mb-3">Why it was flagged</h3>
        <FeatureReasons features={d.top_features} />
      </div>

      {module === 'network' && d.src_ip && (
        <div>
          <h3 className="label mb-2">Flow</h3>
          <p className="font-mono text-sm text-pearl-muted">
            {d.src_ip}
            {d.src_port ? `:${d.src_port}` : ''} → {d.dst_ip}
            {d.dst_port ? `:${d.dst_port}` : ''}{' '}
            <span className="text-pearl-dim">{protocolName(d.protocol)}</span>
          </p>
        </div>
      )}

      {family && family.mitigations.length > 0 && (
        <div>
          <h3 className="label mb-2">What stops it</h3>
          <ul className="list-disc space-y-1 pl-5 text-sm text-pearl-muted">
            {family.mitigations.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}

      {action && (
        <div className="mt-auto rounded-xl border border-midnight-700 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium">
                {blocked ? `Blocked ${action.target_ip}` : `Block ${action.status}`}
              </div>
              <div className="text-xs text-pearl-dim">
                {action.mode === 'simulate'
                  ? 'Simulated firewall rule (sandbox)'
                  : 'Firewall rule in the victim container'}
              </div>
            </div>
            {blocked && (
              <button
                className="btn-ghost"
                onClick={() => undo.mutate(action.id)}
                disabled={undo.isPending}
              >
                <Undo2 className="h-4 w-4" /> Undo
              </button>
            )}
          </div>
          {undo.error && <p className="mt-2 text-xs text-risk-high">{undo.error.message}</p>}
        </div>
      )}
    </aside>
  );
}
