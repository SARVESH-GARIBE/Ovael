import React from 'react';
import { TheaterEvent } from '../events';
import { Sparkles } from 'lucide-react';

interface EventTimelineProps {
  events: TheaterEvent[];
  selectedEventId?: string;
  onSelectEvent: (event: TheaterEvent) => void;
}

export const EventTimeline: React.FC<EventTimelineProps> = ({
  events,
  selectedEventId,
  onSelectEvent,
}) => {
  if (events.length === 0) return null;

  return (
    <div className="bg-dark-900/80 backdrop-blur border border-dark-800 rounded-xl p-3 max-h-48 overflow-y-auto w-72 text-xs font-mono select-none shadow-xl">
      <div className="text-[10px] text-slate-500 font-bold uppercase tracking-wider mb-2 flex items-center justify-between">
        <span>Recent Analyzed Flows</span>
        <span className="text-neon-cyan">{events.length}</span>
      </div>

      <div className="space-y-1.5">
        {events.map((ev) => {
          const isSelected = ev.id === selectedEventId;
          const timeStr = new Date(ev.timestamp).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          });

          return (
            <button
              key={ev.id}
              onClick={() => onSelectEvent(ev)}
              className={`w-full text-left p-2 rounded-lg border transition-all flex items-center justify-between ${
                isSelected
                  ? 'bg-dark-800 border-neon-cyan/50 text-white shadow-[0_0_8px_rgba(0,242,254,0.15)]'
                  : 'bg-dark-950/60 border-dark-800/80 text-slate-300 hover:bg-dark-850 hover:text-white'
              }`}
            >
              <div className="flex items-center gap-2 truncate">
                <span
                  className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                    ev.is_stub
                      ? 'bg-slate-500'
                      : ev.predicted_class === 'benign'
                      ? 'bg-neon-cyan'
                      : 'bg-neon-red'
                  }`}
                />
                <span className="font-semibold uppercase truncate">{ev.predicted_class}</span>
                {ev.is_novel && (
                  <span title="Novel behavior">
                    <Sparkles className="w-3 h-3 text-neon-violet shrink-0" />
                  </span>
                )}
              </div>

              <div className="text-[10px] text-slate-500 shrink-0 ml-2">{timeStr}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
