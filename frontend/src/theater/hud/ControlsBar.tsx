import React from 'react';
import { QualityTier } from '../../hooks/useQualityTier';
import { Sliders, Camera, EyeOff } from 'lucide-react';

interface ControlsBarProps {
  qualityTier: QualityTier;
  onChangeQuality: (tier: QualityTier) => void;
  reducedMotion: boolean;
  onToggleReducedMotion: () => void;
  enableCameraDrift: boolean;
  onToggleCameraDrift: () => void;
  streamStatus?: 'connecting' | 'live' | 'reconnecting' | 'offline' | 'demo';
}

export const ControlsBar: React.FC<ControlsBarProps> = ({
  qualityTier,
  onChangeQuality,
  reducedMotion,
  onToggleReducedMotion,
  enableCameraDrift,
  onToggleCameraDrift,
  streamStatus = 'demo',
}) => {
  const statusColors = {
    live: 'bg-neon-green text-dark-950 border-neon-green',
    demo: 'bg-neon-amber/20 text-neon-amber border-neon-amber/40',
    connecting: 'bg-neon-cyan/20 text-neon-cyan border-neon-cyan/40',
    reconnecting: 'bg-neon-amber/20 text-neon-amber border-neon-amber/40',
    offline: 'bg-slate-800 text-slate-400 border-slate-700',
  };

  return (
    <div className="bg-dark-900/80 backdrop-blur border border-dark-800 rounded-xl p-2.5 flex flex-wrap items-center gap-3 text-xs font-mono select-none shadow-xl">
      {/* Stream Status Indicator */}
      <div className="flex items-center gap-1.5 pr-2 border-r border-dark-800">
        <span className="text-[10px] text-slate-500 uppercase">Stream:</span>
        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${statusColors[streamStatus]}`}>
          {streamStatus}
        </span>
      </div>

      {/* Quality Tier Selector */}
      <div className="flex items-center gap-1.5 pr-2 border-r border-dark-800">
        <Sliders className="w-3.5 h-3.5 text-slate-400" />
        <span className="text-[10px] text-slate-500 uppercase">Quality:</span>
        {(['high', 'medium', 'low'] as QualityTier[]).map((tier) => (
          <button
            key={tier}
            onClick={() => onChangeQuality(tier)}
            className={`px-2 py-0.5 rounded text-[10px] uppercase font-semibold transition-colors ${
              qualityTier === tier
                ? 'bg-dark-800 text-neon-cyan border border-neon-cyan/40'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            {tier}
          </button>
        ))}
      </div>

      {/* Camera Drift Toggle */}
      <button
        onClick={onToggleCameraDrift}
        className={`flex items-center gap-1.5 px-2 py-1 rounded transition-colors text-[11px] ${
          enableCameraDrift
            ? 'bg-dark-800 text-neon-cyan border border-neon-cyan/30'
            : 'text-slate-400 hover:text-white'
        }`}
        title="Toggle automatic camera drifting"
      >
        <Camera className="w-3.5 h-3.5" />
        <span>Camera Drift: {enableCameraDrift ? 'ON' : 'OFF'}</span>
      </button>

      {/* Reduce Effects Toggle */}
      <button
        onClick={onToggleReducedMotion}
        className={`flex items-center gap-1.5 px-2 py-1 rounded transition-colors text-[11px] ${
          reducedMotion
            ? 'bg-neon-amber/20 text-neon-amber border border-neon-amber/40 font-bold'
            : 'text-slate-400 hover:text-white'
        }`}
        title="Toggle reduced motion / effects"
      >
        <EyeOff className="w-3.5 h-3.5" />
        <span>Reduce Effects: {reducedMotion ? 'ON' : 'OFF'}</span>
      </button>
    </div>
  );
};
