import React from 'react';
import { SceneCommand } from '../director';
import { STYLE_CONFIGS } from '../styles';
import { Skull, Shield } from 'lucide-react';

interface WebGLFallbackProps {
  activeWaves: SceneCommand[];
  reducedMotion?: boolean;
}

export const WebGLFallback: React.FC<WebGLFallbackProps> = ({ activeWaves, reducedMotion }) => {
  const currentWave = activeWaves.length > 0 ? activeWaves[0] : null;
  const config = currentWave ? STYLE_CONFIGS[currentWave.family] : STYLE_CONFIGS.benign;

  return (
    <div className="w-full h-full flex flex-col items-center justify-center p-8 bg-dark-950 relative overflow-hidden select-none">
      {/* Background Grid Pattern */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#0f1423_1px,transparent_1px),linear-gradient(to_bottom,#0f1423_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_50%,#000_70%,transparent_100%)] opacity-40 pointer-events-none" />

      {/* Notice Banner */}
      <div className="absolute top-16 text-center z-10">
        <span className="text-[11px] font-mono px-3 py-1 rounded bg-dark-900 border border-dark-700 text-slate-400">
          DOM-Only Fallback Active • WebGL Hardware Acceleration Unavailable
        </span>
      </div>

      {/* Main Chamber Visualization Arena */}
      <div className="w-full max-w-4xl flex items-center justify-between gap-6 z-10 px-6">
        {/* ATTACKER CHAMBER BOX */}
        <div className="w-64 h-72 rounded-2xl bg-dark-900 border-2 border-neon-red/40 p-5 flex flex-col justify-between shadow-[0_0_25px_rgba(255,0,85,0.15)]">
          <div className="flex items-center gap-2 text-neon-red font-mono font-bold text-sm">
            <Skull className="w-5 h-5 text-neon-red" />
            <span>ATTACKER CHAMBER</span>
          </div>
          <div className="text-center font-mono text-xs text-slate-400">
            <div className="text-lg font-bold text-white mb-1">Terminal Active</div>
            <div>Low-Poly Ingress Station</div>
            {currentWave && (
              <div className="mt-3 px-2 py-1 rounded bg-dark-950 border border-neon-red/30 text-neon-red font-bold text-[11px]">
                Firing: {currentWave.family.toUpperCase()} (×{currentWave.eventCount})
              </div>
            )}
          </div>
          <div className="w-full h-1.5 rounded-full bg-dark-950 overflow-hidden">
            <div className="w-full h-full bg-neon-red animate-pulse" />
          </div>
        </div>

        {/* FLOW CONDUIT / BRIDGE */}
        <div className="flex-1 flex flex-col items-center justify-center relative px-4">
          <div className="w-full h-2 bg-dark-900 rounded-full border border-dark-800 relative overflow-hidden">
            {currentWave && (
              <div
                className={`absolute top-0 bottom-0 rounded-full ${
                  reducedMotion ? 'w-full' : 'w-12 animate-[ping_2s_cubic-bezier(0,0,0.2,1)_infinite]'
                }`}
                style={{
                  backgroundColor: currentWave.isStub ? '#6c757d' : config.primaryColor,
                }}
              />
            )}
          </div>

          <div className="mt-4 font-mono text-xs text-slate-400 text-center">
            {currentWave ? (
              <div className="space-y-1">
                <div className="font-bold text-slate-200">
                  {currentWave.isStub ? 'STUB FLOW' : config.label}
                </div>
                {currentWave.hasNoveltyOverlay && (
                  <div className="text-neon-violet font-semibold text-[11px]">
                    ✦ Unfamiliar Behavior Overlay Active
                  </div>
                )}
              </div>
            ) : (
              <span className="text-slate-600">Conduit Idle</span>
            )}
          </div>
        </div>

        {/* VICTIM CHAMBER BOX */}
        <div className="w-64 h-72 rounded-2xl bg-dark-900 border-2 border-neon-cyan/40 p-5 flex flex-col justify-between shadow-[0_0_25px_rgba(0,242,254,0.15)]">
          <div className="flex items-center justify-end gap-2 text-neon-cyan font-mono font-bold text-sm">
            <span>VICTIM CHAMBER</span>
            <Shield className="w-5 h-5 text-neon-cyan" />
          </div>
          <div className="text-center font-mono text-xs text-slate-400">
            <div className="text-lg font-bold text-white mb-1">Server Tower</div>
            <div>Hex Shield System Active</div>
            {currentWave && (
              <div className="mt-3 px-2 py-1 rounded bg-dark-950 border border-neon-cyan/30 text-neon-cyan font-bold text-[11px]">
                Impact Load: Level {currentWave.intensity}/5
              </div>
            )}
          </div>
          <div className="w-full h-1.5 rounded-full bg-dark-950 overflow-hidden">
            <div className="w-full h-full bg-neon-cyan" />
          </div>
        </div>
      </div>
    </div>
  );
};
