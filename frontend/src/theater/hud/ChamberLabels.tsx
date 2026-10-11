import React from 'react';
import { Shield, Skull, Lock, Unlock } from 'lucide-react';

interface ChamberLabelsProps {
  sourceIp?: string;
  sourcePort?: number;
  destinationIp?: string;
  destinationPort?: number;
  maskIps: boolean;
  onToggleMaskIps: () => void;
}

export const ChamberLabels: React.FC<ChamberLabelsProps> = ({
  sourceIp,
  sourcePort,
  destinationIp,
  destinationPort,
  maskIps,
  onToggleMaskIps,
}) => {
  const maskIp = (ip?: string): string => {
    if (!ip) return '';
    if (!maskIps) return ip;
    const parts = ip.split('.');
    if (parts.length === 4) {
      return `${parts[0]}.***.***.${parts[3]}`;
    }
    return `${ip.substring(0, 4)}***`;
  };

  const srcDisplay = sourceIp
    ? `${maskIp(sourceIp)}${sourcePort ? `:${sourcePort}` : ''}`
    : 'Unknown source';

  const dstDisplay = destinationIp
    ? `${maskIp(destinationIp)}${destinationPort ? `:${destinationPort}` : ''}`
    : 'Unknown target';

  return (
    <div className="absolute top-12 left-0 right-0 px-8 flex justify-between items-start pointer-events-none z-10">
      {/* ATTACKER CHAMBER LABEL */}
      <div className="pointer-events-auto bg-dark-900/80 backdrop-blur border border-neon-red/30 rounded-lg p-3 text-left shadow-lg max-w-xs">
        <div className="flex items-center gap-2 text-neon-red font-mono text-xs font-bold uppercase tracking-wider mb-1">
          <Skull className="w-4 h-4 text-neon-red" />
          <span>Attacker Chamber</span>
        </div>
        <div className="text-sm font-mono text-slate-100 font-semibold">{srcDisplay}</div>
        <div className="text-[10px] text-slate-400 font-mono mt-0.5">Ingress Point • Origin Flow</div>
      </div>

      {/* CENTER MASK IP TOGGLE BUTTON */}
      <div className="pointer-events-auto bg-dark-900/80 backdrop-blur border border-dark-800 rounded-lg px-3 py-1.5 flex items-center gap-2 text-xs font-mono text-slate-300">
        <button
          onClick={onToggleMaskIps}
          className="flex items-center gap-1.5 hover:text-neon-cyan transition-colors"
          title="Toggle masking of IP addresses"
        >
          {maskIps ? (
            <>
              <Lock className="w-3.5 h-3.5 text-neon-cyan" />
              <span>Masked IPs</span>
            </>
          ) : (
            <>
              <Unlock className="w-3.5 h-3.5 text-slate-400" />
              <span>Raw IPs</span>
            </>
          )}
        </button>
      </div>

      {/* VICTIM CHAMBER LABEL */}
      <div className="pointer-events-auto bg-dark-900/80 backdrop-blur border border-neon-cyan/30 rounded-lg p-3 text-right shadow-lg max-w-xs">
        <div className="flex items-center justify-end gap-2 text-neon-cyan font-mono text-xs font-bold uppercase tracking-wider mb-1">
          <span>Victim Chamber</span>
          <Shield className="w-4 h-4 text-neon-cyan" />
        </div>
        <div className="text-sm font-mono text-slate-100 font-semibold">{dstDisplay}</div>
        <div className="text-[10px] text-slate-400 font-mono mt-0.5">Target Host • Hex Shield Active</div>
      </div>
    </div>
  );
};
