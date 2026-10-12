import { useState } from 'react';
import { Check, X } from 'lucide-react';
import type { Module, ReviewItem } from '../api/client';
import { useModels, useReviewDecision, useReviewQueue } from '../api/hooks';
import { Chip, Empty } from '../components/ui';
import { pct, timeAgo, titleCase } from '../lib/format';

const REASONS: Record<string, string> = {
  normal_but_unusual: 'Classifier says normal, anomaly detector says unusual',
  low_confidence: 'Classifier was unsure',
  lab_probe: 'Learning-loop experiment flow',
};

function Row({ item, classes }: { item: ReviewItem; classes: string[] }) {
  const [label, setLabel] = useState(item.predicted_label);
  const [custom, setCustom] = useState('');
  const decide = useReviewDecision();
  const ctx = item.context as {
    anomaly_score?: number;
    confidence?: number;
    src_ip?: string;
    probabilities?: Record<string, number>;
  };
  const finalLabel = label === '__new' ? custom.trim() : label;

  return (
    <li className="grid gap-3 py-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Chip>{item.module}</Chip>
          <span className="text-sm">{REASONS[item.reason] ?? item.reason}</span>
          <span className="text-xs text-pearl-dim">{timeAgo(item.created_at)}</span>
        </div>
        <div className="mt-1 font-mono text-xs text-pearl-dim">
          predicted {titleCase(item.predicted_label)} · confidence {pct(ctx.confidence)} · unusual{' '}
          {pct(ctx.anomaly_score)}
          {ctx.src_ip ? ` · ${ctx.src_ip}` : ''}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <select
          className="input py-1.5"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          aria-label="Final label"
        >
          {classes.map((c) => (
            <option key={c} value={c}>
              {titleCase(c)}
            </option>
          ))}
          <option value="__new">New class…</option>
        </select>
        {label === '__new' && (
          <input
            className="input w-36 py-1.5"
            placeholder="class name"
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
          />
        )}
        <button
          className="btn-primary"
          disabled={!finalLabel || decide.isPending}
          onClick={() => decide.mutate({ id: item.id, label: finalLabel })}
        >
          <Check className="h-4 w-4" /> Confirm
        </button>
        <button
          className="btn-ghost"
          disabled={decide.isPending}
          onClick={() => decide.mutate({ id: item.id, reject: true })}
          title="Noise: not worth learning from"
        >
          <X className="h-4 w-4" /> Discard
        </button>
      </div>
      {decide.error && (
        <p className="text-xs text-risk-high md:col-span-2">{decide.error.message}</p>
      )}
    </li>
  );
}

export function ReviewPage() {
  const [module, setModule] = useState<Module | undefined>();
  const queue = useReviewQueue(module);
  const models = useModels();
  const classesFor = (m: string) => {
    const active = models.data?.find((v) => v.module === m && v.status === 'active');
    return active?.classes ?? ['benign'];
  };

  return (
    <div className="mx-auto flex w-full max-w-[1100px] flex-col gap-6 p-5 lg:p-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Review queue</h1>
        <p className="mt-1 max-w-2xl text-sm text-pearl-dim">
          Hard examples: cases the two models disagreed on, or the classifier was unsure about.
          Confirmed labels feed the next retrain, and a new model is promoted only if it scores at
          least as well on the same held-out set.
        </p>
      </header>
      <div className="flex gap-1" role="tablist">
        {([undefined, 'network', 'website'] as const).map((m) => (
          <button
            key={m ?? 'all'}
            role="tab"
            aria-selected={module === m}
            onClick={() => setModule(m)}
            className={`rounded-lg px-3 py-1.5 text-sm ${module === m ? 'bg-midnight-800 text-pearl' : 'text-pearl-dim hover:text-pearl'}`}
          >
            {m ? titleCase(m) : 'All'}
          </button>
        ))}
      </div>
      <section className="card px-5">
        {queue.data?.length ? (
          <ul className="divide-y divide-midnight-800">
            {queue.data.map((item) => (
              <Row key={item.id} item={item} classes={classesFor(item.module)} />
            ))}
          </ul>
        ) : (
          <Empty>Nothing to review.</Empty>
        )}
      </section>
    </div>
  );
}
