import { useMemo, useState } from 'react';
import { Check, CheckCheck, Loader2, Sparkles, X } from 'lucide-react';
import type { Module, ReviewItem } from '../api/client';
import {
  useConfirmBatch,
  useModels,
  useReviewDecision,
  useReviewQueue,
  useReviewSuggestions,
  type ReviewSuggestion,
} from '../api/hooks';
import { Chip, Empty } from '../components/ui';
import { pct, timeAgo, titleCase } from '../lib/format';

const REASONS: Record<string, string> = {
  normal_but_unusual: 'Classifier says normal, anomaly detector says unusual',
  low_confidence: 'Classifier was unsure',
  lab_probe: 'Learning-loop experiment flow',
};

const SOURCE_TONE: Record<ReviewSuggestion['source'], string> = {
  similar: 'text-ocean-light',
  second: 'text-risk-medium',
  normal: 'text-pearl-muted',
  none: 'text-pearl-dim',
};

const NEW = '__new';

function Row({
  item,
  classes,
  suggestion,
  value,
  onChange,
}: {
  item: ReviewItem;
  classes: string[];
  suggestion?: ReviewSuggestion;
  value: string;
  onChange: (label: string) => void;
}) {
  const [custom, setCustom] = useState('');
  const decide = useReviewDecision();
  const ctx = item.context as {
    anomaly_score?: number;
    confidence?: number;
    src_ip?: string;
  };
  const options = Array.from(
    new Set([...classes, ...(suggestion?.label ? [suggestion.label] : [])])
  );
  const isNew = value === NEW;
  const finalLabel = isNew ? custom.trim() : value;

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
        {suggestion && (
          <div
            className={`mt-1.5 flex items-center gap-1.5 text-xs ${SOURCE_TONE[suggestion.source]}`}
          >
            <Sparkles className="h-3.5 w-3.5 shrink-0" />
            {suggestion.label ? (
              <span>
                Suggested <span className="font-semibold">{titleCase(suggestion.label)}</span> ·{' '}
                {suggestion.reason}
              </span>
            ) : (
              <span>No suggestion: {suggestion.reason}. Pick a label yourself.</span>
            )}
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <select
          className="input py-1.5"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-label="Final label"
        >
          {!value && <option value="">Pick a label…</option>}
          {options.map((c) => (
            <option key={c} value={c}>
              {titleCase(c)}
            </option>
          ))}
          <option value={NEW}>New class…</option>
        </select>
        {isNew && (
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
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [confirming, setConfirming] = useState(false);
  const queue = useReviewQueue(module);
  const models = useModels();
  const netSugg = useReviewSuggestions('network', module !== 'website');
  const webSugg = useReviewSuggestions('website', module !== 'network');
  const batch = useConfirmBatch();

  const suggestions = useMemo(
    () => ({ ...(netSugg.data ?? {}), ...(webSugg.data ?? {}) }),
    [netSugg.data, webSugg.data]
  );
  const classesFor = (m: string) =>
    models.data?.find((v) => v.module === m && v.status === 'active')?.classes ?? ['benign'];

  const items = queue.data ?? [];
  // A row's label: what the reviewer picked, else Ovael's suggestion, else empty.
  const labelOf = (item: ReviewItem) => picked[item.id] ?? suggestions[item.id]?.label ?? '';
  const ready = items
    .map((i) => ({ id: i.id, label: labelOf(i) }))
    .filter((d) => d.label && d.label !== NEW);
  const summary = ready.reduce<Record<string, number>>((acc, d) => {
    acc[d.label] = (acc[d.label] ?? 0) + 1;
    return acc;
  }, {});
  const missing = items.length - ready.length;

  const acceptAll = () =>
    batch.mutate(ready, {
      onSuccess: () => {
        setConfirming(false);
        setPicked({});
      },
    });

  return (
    <div className="mx-auto flex w-full max-w-[1100px] flex-col gap-6 p-5 lg:p-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Review queue</h1>
        <p className="mt-1 max-w-2xl text-sm text-pearl-dim">
          Hard examples: cases the two models disagreed on, or the classifier was unsure about.
          Ovael suggests a label for each one and says why. Nothing is learned until you confirm,
          and a new model is promoted only if it scores at least as well on the same held-out set.
        </p>
      </header>

      <div className="flex gap-1" role="tablist">
        {([undefined, 'network', 'website'] as const).map((m) => (
          <button
            key={m ?? 'all'}
            role="tab"
            aria-selected={module === m}
            onClick={() => {
              setModule(m);
              setConfirming(false);
            }}
            className={`rounded-lg px-3 py-1.5 text-sm ${module === m ? 'bg-midnight-800 text-pearl' : 'text-pearl-dim hover:text-pearl'}`}
          >
            {m ? titleCase(m) : 'All'}
          </button>
        ))}
      </div>

      {items.length > 0 && (
        <section className="card flex flex-wrap items-center gap-4 p-5">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 font-medium">
              <Sparkles className="h-4 w-4 text-ocean" />
              {ready.length} of {items.length} items have a label ready
            </div>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-pearl-dim">
              {Object.entries(summary)
                .sort((a, b) => b[1] - a[1])
                .map(([label, n]) => (
                  <span key={label}>
                    {titleCase(label)} <span className="font-mono text-pearl-muted">{n}</span>
                  </span>
                ))}
              {missing > 0 && <span>· {missing} without a suggestion are skipped</span>}
            </div>
            {batch.data && !confirming && (
              <p className="mt-2 text-xs text-ocean-light">
                Confirmed {batch.data.confirmed}
                {batch.data.skipped ? `, skipped ${batch.data.skipped} already handled` : ''}.
              </p>
            )}
            {batch.error && <p className="mt-2 text-xs text-risk-high">{batch.error.message}</p>}
          </div>
          {confirming ? (
            <div className="flex items-center gap-2">
              <span className="text-sm text-pearl-muted">Confirm {ready.length} labels?</span>
              <button className="btn-primary" onClick={acceptAll} disabled={batch.isPending}>
                {batch.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Check className="h-4 w-4" />
                )}
                Yes, confirm
              </button>
              <button className="btn-ghost" onClick={() => setConfirming(false)}>
                Cancel
              </button>
            </div>
          ) : (
            <button
              className="btn-primary"
              disabled={!ready.length}
              onClick={() => setConfirming(true)}
            >
              <CheckCheck className="h-4 w-4" /> Accept all ({ready.length})
            </button>
          )}
        </section>
      )}

      <section className="card px-5">
        {items.length ? (
          <ul className="divide-y divide-midnight-800">
            {items.map((item) => (
              <Row
                key={item.id}
                item={item}
                classes={classesFor(item.module)}
                suggestion={suggestions[item.id]}
                value={labelOf(item)}
                onChange={(label) => setPicked((p) => ({ ...p, [item.id]: label }))}
              />
            ))}
          </ul>
        ) : (
          <Empty>Nothing to review.</Empty>
        )}
      </section>
    </div>
  );
}
