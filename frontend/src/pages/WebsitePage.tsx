import { useState, type FormEvent } from 'react';
import { Globe, Loader2, Search } from 'lucide-react';
import type { RiskLevel, ScanDetail } from '../api/client';
import { useFamily, useScan, useScans, useSubmitScan } from '../api/hooks';
import {
  Chip,
  Empty,
  FeatureReasons,
  RiskBadge,
  RiskGauge,
  Section,
  Steps,
} from '../components/ui';
import { SmartReport, type Smart } from '../components/SmartReport';
import { num, pct, timeAgo, titleCase } from '../lib/format';

interface Report {
  final_url?: string;
  title?: string;
  http_status?: number;
  trackers?: Array<{ hostname: string; requests: number; owner?: string; categories: string[] }>;
  third_party_cookie_domains?: string[];
  redirect_chain?: string[];
  fingerprinting?: Record<string, number | null>;
  counts?: Record<string, number | null>;
  smart?: Smart;
}

const COUNT_LABELS: Record<string, string> = {
  total_requests: 'Requests',
  third_party_requests: 'Third-party requests',
  tracker_matched_requests: 'Tracker requests',
  unique_tracker_domains: 'Tracker domains',
  total_cookies: 'Cookies',
  third_party_cookies: 'Third-party cookies',
  hidden_iframe_count: 'Hidden iframes',
  redirect_count: 'Redirects',
};

const FP_LABELS: Record<string, string> = {
  canvas_readback_calls: 'Canvas readback',
  webgl_unmasked_info_queries: 'GPU identity query',
  offline_audio_contexts: 'Offline audio',
  audio_api_calls: 'Audio API',
  other_fingerprinting_api_calls: 'Other fingerprinting',
};

function ReportView({ scan }: { scan: ScanDetail }) {
  const d = scan.detection;
  const family = useFamily('website', d?.family);
  const r = scan.report as Report;
  if (!d) return null;
  const level = d.risk_level as RiskLevel;

  return (
    <div className="flex flex-col gap-5">
      {r.smart && <SmartReport smart={r.smart} domain={scan.domain} />}
      {r.smart && <h2 className="label mt-3">Technical details</h2>}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-[360px_minmax(0,1fr)] animate-fadein">
        <section className="card flex flex-col items-center p-6 text-center">
          <span className="label mb-1">Tracking model</span>
          <RiskGauge score={d.risk_score} level={level} size={200} />
          <div className="mt-2">
            <RiskBadge level={level} />
          </div>
          <h2 className="mt-3 text-xl font-semibold">{family?.name ?? titleCase(d.label)}</h2>
          <p className="mt-1 text-sm text-pearl-muted">{family?.summary}</p>
          <p className="mt-4 break-all font-mono text-xs text-pearl-dim">
            {r.final_url ?? scan.url}
          </p>
          {r.title && <p className="mt-1 text-sm text-pearl-muted">“{r.title}”</p>}
          <div className="mt-4 grid w-full grid-cols-2 gap-3 border-t border-midnight-800 pt-4 text-left text-sm">
            <div>
              <div className="label">Classifier</div>
              <div>
                {titleCase(d.label)} · {pct(d.confidence)}
              </div>
            </div>
            <div>
              <div className="label">Unusual</div>
              <div>
                {d.is_unusual ? 'Yes' : 'No'} · {pct(d.anomaly_score)}
              </div>
            </div>
          </div>
          {scan.cached && (
            <p className="mt-3 text-[11px] text-pearl-dim">Cached result for {scan.domain}</p>
          )}
        </section>

        <div className="grid grid-cols-[minmax(0,1fr)] gap-5 md:grid-cols-2">
          <Section title="Why this score">
            <FeatureReasons features={d.top_features} limit={6} />
          </Section>

          <Section title="What we saw">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
              {Object.entries(COUNT_LABELS).map(([k, label]) => (
                <div key={k}>
                  <dt className="text-[11px] text-pearl-dim">{label}</dt>
                  <dd className="font-mono text-sm">{num(r.counts?.[k])}</dd>
                </div>
              ))}
            </dl>
            {r.fingerprinting && Object.values(r.fingerprinting).some((v) => v) && (
              <div className="mt-4 flex flex-wrap gap-1.5">
                {Object.entries(r.fingerprinting)
                  .filter(([, v]) => v)
                  .map(([k, v]) => (
                    <Chip key={k} tone="warn">
                      {FP_LABELS[k] ?? k} ×{v}
                    </Chip>
                  ))}
              </div>
            )}
          </Section>

          <Section title="Trackers on this page" className="md:col-span-2">
            {r.trackers?.length ? (
              <ul className="divide-y divide-midnight-800">
                {r.trackers.map((t) => (
                  <li key={t.hostname} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                    <span className="font-mono text-sm">{t.hostname}</span>
                    {t.owner && <span className="text-xs text-pearl-dim">{t.owner}</span>}
                    <span className="ml-auto flex flex-wrap gap-1">
                      {t.categories.slice(0, 3).map((c) => (
                        <Chip key={c}>{c}</Chip>
                      ))}
                    </span>
                    <span className="w-12 text-right font-mono text-xs text-pearl-dim">
                      {t.requests}×
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No known tracker domains were contacted.</Empty>
            )}
          </Section>

          {family && family.how_it_works.length > 1 && !family.is_benign && (
            <Section title="How this tracking works" className="md:col-span-2">
              <Steps steps={family.how_it_works} />
              {family.mitigations.length > 0 && (
                <p className="mt-4 text-sm text-pearl-muted">
                  <span className="text-pearl">Protect yourself: </span>
                  {family.mitigations.join(' · ')}
                </p>
              )}
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}

export function WebsitePage() {
  const [url, setUrl] = useState('');
  const [scanId, setScanId] = useState<string>();
  const submit = useSubmitScan();
  const scan = useScan(scanId);
  const recent = useScans();

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    submit.mutate(url.trim(), { onSuccess: (s) => setScanId(s.id) });
  };

  const s = scan.data;
  const busy = submit.isPending || (s && ['queued', 'running'].includes(s.status));

  return (
    <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-6 p-5 lg:p-8">
      <header className="mx-auto w-full max-w-2xl pt-6 text-center">
        <h1 className="text-3xl font-semibold tracking-tight">Website analysis</h1>
        <p className="mt-2 text-sm text-pearl-dim">
          Type a website or just its name, like instagram or rummycircle. We open it in an isolated
          browser, check its reputation, connection and content, and tell you how risky it is to
          open.
        </p>
        <form onSubmit={onSubmit} className="mt-6 flex gap-2">
          <label className="relative flex-1">
            <span className="sr-only">Website URL</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-pearl-dim" />
            <input
              className="input w-full py-3 pl-10 text-base"
              placeholder="instagram.com or rummycircle"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              autoFocus
            />
          </label>
          <button className="btn-primary px-5" disabled={busy || !url.trim()}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Analyze'}
          </button>
        </form>
        {submit.error && <p className="mt-3 text-sm text-risk-high">{submit.error.message}</p>}
      </header>

      {s && ['queued', 'running'].includes(s.status) && (
        <div className="card mx-auto flex w-full max-w-2xl items-center gap-4 p-5">
          <Loader2 className="h-5 w-5 animate-spin text-ocean" />
          <div>
            <div className="text-sm font-medium">
              {s.status === 'queued' ? 'Waiting for a scanner…' : `Scanning ${s.domain}…`}
            </div>
            <div className="text-xs text-pearl-dim">
              Loading the page, checking reputation and certificates, then scoring. Usually 10–30 s.
            </div>
          </div>
        </div>
      )}
      {s?.status === 'failed' && (
        <div className="card mx-auto w-full max-w-2xl p-5 text-sm">
          <span className="text-risk-high">Scan failed.</span>{' '}
          <span className="text-pearl-muted">{s.error}</span>
        </div>
      )}
      {s?.status === 'failed' && (s.report as Report).smart && (
        <SmartReport smart={(s.report as Report).smart!} domain={s.domain} />
      )}
      {s?.status === 'completed' && <ReportView scan={s} />}

      <Section title="Recent scans">
        {recent.data?.length ? (
          <ul className="-mx-2">
            {recent.data.map((r) => (
              <li key={r.id}>
                <button
                  className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-midnight-900"
                  onClick={() => setScanId(r.id)}
                >
                  <Globe className="h-4 w-4 shrink-0 text-pearl-dim" />
                  <span className="flex-1 truncate text-sm">{r.domain}</span>
                  <span className="text-xs text-pearl-dim">{r.status}</span>
                  <span className="w-20 text-right text-xs text-pearl-dim">
                    {timeAgo(r.created_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No scans yet. Try a news site and compare it with a plain one.</Empty>
        )}
      </Section>
    </div>
  );
}
