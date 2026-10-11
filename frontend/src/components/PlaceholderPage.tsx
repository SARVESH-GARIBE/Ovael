import React from 'react';

interface PlaceholderProps {
  title: string;
  description: string;
  badge?: string;
}

export const PlaceholderPage: React.FC<PlaceholderProps> = ({ title, description, badge }) => {
  return (
    <div className="flex-1 p-8 flex flex-col items-center justify-center text-center">
      <div className="max-w-lg w-full bg-dark-900 border border-dark-800 rounded-xl p-8">
        {badge && (
          <span className="inline-block text-[11px] font-mono px-2.5 py-0.5 rounded bg-dark-800 text-neon-blue border border-neon-blue/30 mb-3">
            {badge}
          </span>
        )}
        <h2 className="text-xl font-bold text-white mb-2 font-mono">{title}</h2>
        <p className="text-sm text-slate-400 mb-6">{description}</p>
        <div className="text-xs font-mono text-slate-500 bg-dark-950 p-3 rounded border border-dark-800">
          Awaiting backend platform connectivity. To test full attack visualizations without the backend,
          use <span className="text-neon-amber font-semibold">Demo Mode</span>.
        </div>
      </div>
    </div>
  );
};
