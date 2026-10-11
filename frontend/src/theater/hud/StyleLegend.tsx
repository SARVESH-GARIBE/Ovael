import React, { useState } from 'react';
import { STYLE_CONFIGS, StyleFamily } from '../styles';
import { ChevronDown, ChevronUp, Palette, Sparkles } from 'lucide-react';

export const StyleLegend: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  const families: StyleFamily[] = [
    'benign',
    'flood',
    'scan',
    'slow-connection',
    'credential',
    'web',
    'stealth',
    'unrecognized',
    'stub',
  ];

  return (
    <div className="bg-dark-900/80 backdrop-blur border border-dark-800 rounded-xl overflow-hidden text-xs font-mono select-none shadow-xl w-72">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-3 py-2 flex items-center justify-between text-slate-300 hover:text-white transition-colors border-b border-dark-800"
      >
        <div className="flex items-center gap-2">
          <Palette className="w-3.5 h-3.5 text-neon-cyan" />
          <span className="font-semibold uppercase tracking-wider text-[11px]">Attack Styles Legend</span>
        </div>
        {isOpen ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
      </button>

      {isOpen && (
        <div className="p-3 space-y-2 max-h-60 overflow-y-auto">
          {families.map((fam) => {
            const cfg = STYLE_CONFIGS[fam];
            return (
              <div key={fam} className="flex items-start gap-2 text-[11px]">
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0 mt-0.5"
                  style={{ backgroundColor: cfg.primaryColor }}
                />
                <div>
                  <div className="font-semibold text-slate-200">{cfg.label}</div>
                  <div className="text-[10px] text-slate-400 leading-tight">{cfg.description}</div>
                </div>
              </div>
            );
          })}

          {/* Novelty Shimmer Legend Entry */}
          <div className="pt-2 border-t border-dark-800/80 flex items-start gap-2 text-[11px]">
            <Sparkles className="w-3 h-3 text-neon-violet shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-neon-violet">Novelty Shimmer Overlay</div>
              <div className="text-[10px] text-slate-400 leading-tight">
                Violet sparks along stream indicating unfamiliar profile (independent of family).
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
