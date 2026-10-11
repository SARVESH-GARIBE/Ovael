import React from 'react';
import { TheaterEvent } from '../events';
import { Sparkles, HelpCircle, Activity } from 'lucide-react';

interface VerdictCardProps {
  currentEvent: TheaterEvent | null;
}

export const VerdictCard: React.FC<VerdictCardProps> = ({ currentEvent }) => {
  if (!currentEvent) {
    return (
      <div className="bg-dark-900/85 backdrop-blur border border-dark-800 rounded-xl p-4 text-xs font-mono text-slate-400 select-none shadow-xl max-w-sm">
        <div className="flex items-center gap-2 text-slate-500 mb-1">
          <Activity className="w-4 h-4 animate-pulse text-neon-cyan" />
          <span className="font-bold uppercase tracking-wider">Awaiting Flow Events</span>
        </div>
        <div>No active flow in transit. Standing by for telemetry.</div>
      </div>
    );
  }

  const {
    predicted_class,
    confidence,
    is_novel,
    novelty_score,
    is_stub,
    origin,
    risk_score,
    severity,
  } = currentEvent;

  return (
    <div className="bg-dark-900/90 backdrop-blur border border-dark-700 rounded-xl p-4 text-xs font-mono text-slate-200 select-none shadow-2xl max-w-sm w-full space-y-3">
      {/* Header with Origin and Badges */}
      <div className="flex items-center justify-between border-b border-dark-800 pb-2">
        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase font-bold text-slate-400">Origin:</span>
          <span className="px-2 py-0.5 rounded bg-dark-800 border border-dark-700 text-slate-300 text-[11px]">
            {origin}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {is_stub && (
            <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 text-[10px]">
              STUB
            </span>
          )}
          {origin === 'demo' && (
            <span className="px-1.5 py-0.5 rounded bg-neon-amber/20 text-neon-amber border border-neon-amber/40 text-[10px] font-bold">
              DEMO
            </span>
          )}
        </div>
      </div>

      {/* Signal 1: Detection Classifier */}
      <div>
        <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1 flex items-center justify-between">
          <span>Signal 1 • Detection Classifier</span>
          <span className="text-slate-300 font-semibold">
            {(confidence * 100).toFixed(1)}% conf
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`text-base font-bold uppercase tracking-wide ${
              is_stub
                ? 'text-slate-400'
                : predicted_class === 'benign'
                ? 'text-neon-cyan'
                : 'text-neon-red'
            }`}
          >
            {predicted_class}
          </span>
        </div>
      </div>

      {/* Signal 2: Novelty Detector */}
      <div className="pt-1 border-t border-dark-800/60">
        <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1 flex items-center justify-between">
          <span>Signal 2 • Novelty Detector</span>
          <span className="text-neon-violet font-semibold">
            score: {novelty_score.toFixed(2)}
          </span>
        </div>
        {is_novel ? (
          <div className="p-2 rounded bg-neon-violet/10 border border-neon-violet/30 text-neon-violet space-y-1">
            <div className="flex items-center gap-1.5 font-bold">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Unfamiliar Behavior</span>
            </div>
            <div className="text-[10px] text-slate-300 leading-tight">
              Unfamiliar behavior, not confirmed malicious.
            </div>
          </div>
        ) : (
          <div className="text-slate-400 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-500"></span>
            <span>Standard profile pattern (non-novel)</span>
          </div>
        )}
      </div>

      {/* Risk Engine Status (Explicit Placeholder Badge) */}
      <div className="pt-2 border-t border-dark-800 flex items-center justify-between text-[11px]">
        <div className="flex items-center gap-1 text-slate-400">
          <span>Risk:</span>
          <span className="text-slate-300">{risk_score.toFixed(1)} ({severity})</span>
        </div>
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-dark-800 text-slate-400 border border-dark-700 text-[9px]">
          <HelpCircle className="w-2.5 h-2.5" />
          placeholder
        </span>
      </div>
    </div>
  );
};
