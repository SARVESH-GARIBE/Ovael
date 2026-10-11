import React from 'react';
import { AlertTriangle, Info, Eye } from 'lucide-react';

interface HonestyStripProps {
  isDemo?: boolean;
  isStub?: boolean;
}

export const HonestyStrip: React.FC<HonestyStripProps> = ({ isDemo = false, isStub = false }) => {
  return (
    <div className="w-full bg-dark-900/95 border-b border-dark-800 px-4 py-2 text-xs flex flex-wrap items-center justify-between gap-2 z-20 backdrop-blur select-none">
      <div className="flex flex-wrap items-center gap-3">
        {/* Rule 4: Mandatory statement */}
        <div className="flex items-center gap-1.5 text-slate-300 font-medium">
          <Eye className="w-3.5 h-3.5 text-neon-cyan shrink-0" />
          <span>Visualization of analyzed flows, not live packet capture.</span>
        </div>

        {/* Rule 5: Novelty disclaimer */}
        <div className="flex items-center gap-1.5 text-slate-400">
          <Info className="w-3.5 h-3.5 text-neon-violet shrink-0" />
          <span>
            Novelty represents <span className="text-neon-violet font-semibold">unfamiliar behavior</span>, not confirmed maliciousness.
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {/* Rule 2: Demo banner */}
        {isDemo && (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded bg-neon-amber/15 text-neon-amber border border-neon-amber/40 font-mono text-[11px] font-bold tracking-tight">
            <AlertTriangle className="w-3.5 h-3.5" />
            DEMO — scripted events, not real detections
          </span>
        )}

        {/* Rule 3: Stub banner */}
        {isStub && (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-600 font-mono text-[11px] font-semibold">
            STUB MODEL — placeholder verdict
          </span>
        )}
      </div>
    </div>
  );
};
