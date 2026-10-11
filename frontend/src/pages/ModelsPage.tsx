import { RefreshCw } from 'lucide-react';
import type { Module, ModelVersion } from '../api/client';
import { usePromote, useModels, useRetrain } from '../api/hooks';
import { useLiveEvents } from '../api/live';
import { useState } from 'react';
import { Chip, Empty, Section, Stat } from '../components/ui';
import { pct, timeAgo, titleCase } from '../lib/format';

interface Metrics {
  accuracy?: number;
  macro_f1?: number;
  anomaly_false_alarm_rate?: number | null;
  anomaly_attack_rate?: number | null;
  novel_detection_rate?: number;
  per_class_f1?: Record<string, number>;
  holdout_rows?: number;
}

const SOURCE_NOTE: Record<string, string> = {
  synthetic_bootstrap: 'Trained on synthetic flows. Scores say nothing about real traffic yet.',
  weak_rules_v1:
    'Labels come from tracker-list rules, not human review. The model mostly reproduces the rules.',
};

function ModuleCard({ module, versions }: { module: Module; versions: ModelVersion[] }) {
  const retrain = useRetrain();
  const promote = usePromote();
  const [note, setNote] = useState<string>();
  useLiveEvents(['model_retrained', 'model_retraining'], (e) => {
    const d = e.data as {
      module: string;
      version?: string;
      promoted?: boolean;
      reason?: string;
      error?: string;
    };
    if (d.module !== module) return;
    if (e.type === 'model_retraining') setNote('Retraining…');
    else
      setNote(
        d.error
          ? `Retrain failed: ${d.error}`
          : `${d.version}: ${d.promoted ? 'promoted' : 'kept current model'} (${d.reason})`
      );
  });

  const active = versions.find((v) => v.status === 'active');
  const m = (active?.metrics ?? {}) as Metrics;
  const source = active?.label_source ?? '';
  const warn = Object.entries(SOURCE_NOTE).find(([k]) => source.startsWith(k))?.[1];

  return (
    <Section
      title={`${titleCase(module)} models`}
      action={
        <button
          className="btn-ghost"
          onClick={() => retrain.mutate(module, { onSuccess: () => setNote('Retrain queued…') })}
          disabled={retrain.isPending}
        >
          <RefreshCw className="h-4 w-4" /> Retrain
        </button>
      }
    >
      {active ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-semibold">{active.version}</span>
            <Chip>{source}</Chip>
            <span className="text-xs text-pearl-dim">trained {timeAgo(active.trained_at)}</span>
          </div>
          {warn && <p className="mt-2 text-xs text-risk-medium">{warn}</p>}
          <div className="mt-5 grid grid-cols-2 gap-5 sm:grid-cols-4">
            <Stat label="Macro F1" value={pct(m.macro_f1, 1)} />
            <Stat label="Accuracy" value={pct(m.accuracy, 1)} />
            <Stat label="False alarms" value={pct(m.anomaly_false_alarm_rate, 1)} />
            <Stat
              label={m.novel_detection_rate != null ? 'Unknown caught' : 'Attacks unusual'}
              value={pct(m.novel_detection_rate ?? m.anomaly_attack_rate, 1)}
            />
          </div>
          {m.per_class_f1 && (
            <div className="mt-5 space-y-1.5">
              {Object.entries(m.per_class_f1).map(([c, f1]) => (
                <div key={c} className="flex items-center gap-3 text-sm">
                  <span className="w-36 truncate text-pearl-muted">{titleCase(c)}</span>
                  <div className="h-1 flex-1 rounded-full bg-midnight-800">
                    <div className="h-1 rounded-full bg-ocean" style={{ width: `${f1 * 100}%` }} />
                  </div>
                  <span className="w-12 text-right font-mono text-xs">{f1.toFixed(2)}</span>
                </div>
              ))}
              <p className="pt-1 text-[11px] text-pearl-dim">
                F1 per class on {m.holdout_rows} held-out rows
              </p>
            </div>
          )}
        </>
      ) : (
        <Empty>No trained model. Run `python -m ovael.cli train {module}`.</Empty>
      )}
      {note && <p className="mt-4 text-sm text-pearl-muted">{note}</p>}
      {retrain.error && <p className="mt-2 text-sm text-risk-high">{retrain.error.message}</p>}

      {versions.length > 1 && (
        <table className="mt-6 w-full text-sm">
          <thead>
            <tr className="label text-left">
              <th className="pb-2 font-medium">Version</th>
              <th className="pb-2 font-medium">Macro F1</th>
              <th className="pb-2 font-medium">Trained</th>
              <th />
            </tr>
          </thead>
          <tbody className="divide-y divide-midnight-800">
            {versions.map((v) => (
              <tr key={v.version}>
                <td className="py-2 font-mono">{v.version}</td>
                <td className="py-2">{pct((v.metrics as Metrics).macro_f1, 1)}</td>
                <td className="py-2 text-pearl-dim">{timeAgo(v.trained_at)}</td>
                <td className="py-2 text-right">
                  {v.status === 'active' ? (
                    <span className="text-xs text-ocean">active</span>
                  ) : (
                    <button
                      className="btn-ghost px-2 py-1 text-xs"
                      onClick={() => promote.mutate({ module, version: v.version })}
                    >
                      Make active
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Section>
  );
}

export function ModelsPage() {
  const { data } = useModels();
  return (
    <div className="mx-auto flex w-full max-w-[1100px] flex-col gap-6 p-5 lg:p-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Models</h1>
        <p className="mt-1 text-sm text-pearl-dim">
          Random Forest for known behaviour, Isolation Forest for unusual behaviour, one pair per
          module. Every version is kept, so rolling back means making an older one active.
        </p>
      </header>
      {(['network', 'website'] as const).map((m) => (
        <ModuleCard key={m} module={m} versions={(data ?? []).filter((v) => v.module === m)} />
      ))}
    </div>
  );
}
