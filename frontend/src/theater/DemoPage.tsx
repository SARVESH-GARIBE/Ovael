import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { TheaterContainer } from './TheaterContainer';
import { TheaterEvent } from './events';
import { DEMO_SCENARIOS } from './demoData';
import { Play, RotateCcw } from 'lucide-react';

export const DemoPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const scenarioParam = searchParams.get('scenario') || 'benign';
  const [activeScenarioId, setActiveScenarioId] = useState<string>(scenarioParam);
  const [streamEvent, setStreamEvent] = useState<TheaterEvent | null>(null);
  const [initialEvents, setInitialEvents] = useState<TheaterEvent[]>([]);
  const isPlayingBurst = useRef(false);

  const loadScenario = useCallback(
    (scenarioId: string) => {
      setActiveScenarioId(scenarioId);
      setSearchParams({ scenario: scenarioId });
      const scenario = DEMO_SCENARIOS.find((s) => s.id === scenarioId);
      if (!scenario) return;

      if (scenario.id === 'burst-500') {
        const burstEvents = scenario.getEvents();
        setInitialEvents([burstEvents[0]]);
        setStreamEvent(burstEvents[0]);

        // Feed remaining rapidly in small batches
        isPlayingBurst.current = true;
        let idx = 1;
        const interval = setInterval(() => {
          if (idx >= burstEvents.length || !isPlayingBurst.current) {
            clearInterval(interval);
            return;
          }
          setStreamEvent(burstEvents[idx]);
          idx += 5; // Rapid 5 at a time
        }, 25);
      } else {
        isPlayingBurst.current = false;
        const events = scenario.getEvents();
        setInitialEvents(events);
        setStreamEvent(events[0]);
      }
    },
    [setSearchParams]
  );

  useEffect(() => {
    // Initial load
    loadScenario(scenarioParam);
    return () => {
      isPlayingBurst.current = false;
    };
  }, [loadScenario, scenarioParam]);

  return (
    <div className="flex-1 flex flex-col h-full relative">
      {/* Top Demo Scenario Bar */}
      <div className="bg-dark-900 border-b border-dark-800 px-6 py-2.5 flex flex-wrap items-center justify-between gap-3 z-30 select-none">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono font-bold text-neon-amber uppercase tracking-wider flex items-center gap-1.5">
            <Play className="w-3.5 h-3.5" />
            Demo Script Scenarios:
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 overflow-x-auto py-1">
          {DEMO_SCENARIOS.map((sc) => (
            <button
              key={sc.id}
              onClick={() => loadScenario(sc.id)}
              className={`px-2.5 py-1 rounded text-xs font-mono font-medium transition-all ${
                activeScenarioId === sc.id
                  ? 'bg-neon-amber text-dark-950 font-bold shadow-[0_0_10px_rgba(255,183,3,0.3)]'
                  : 'bg-dark-800 text-slate-300 hover:bg-dark-750 hover:text-white border border-dark-700'
              }`}
              title={sc.description}
            >
              {sc.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => loadScenario(activeScenarioId)}
            className="flex items-center gap-1 px-2.5 py-1 rounded bg-dark-800 hover:bg-dark-700 text-slate-200 border border-dark-700 text-xs font-mono transition-colors"
            title="Replay active demo scenario"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Replay</span>
          </button>
        </div>
      </div>

      {/* Main Theater Container running in Demo Mode */}
      <TheaterContainer
        key={activeScenarioId}
        initialEvents={initialEvents}
        streamEvent={streamEvent}
        isDemo={true}
      />
    </div>
  );
};
