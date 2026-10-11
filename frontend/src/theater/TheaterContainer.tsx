import React, { useState, useEffect, useRef, useMemo, Suspense } from 'react';
import { TheaterEvent } from './events';
import { AttackTheaterDirector, SceneCommand } from './director';
import { useReducedMotion } from '../hooks/useReducedMotion';
import { useQualityTier } from '../hooks/useQualityTier';
import { useWebGLSupport } from '../hooks/useWebGLSupport';
import { HonestyStrip } from './hud/HonestyStrip';
import { ChamberLabels } from './hud/ChamberLabels';
import { VerdictCard } from './hud/VerdictCard';
import { EventTimeline } from './hud/EventTimeline';
import { StyleLegend } from './hud/StyleLegend';
import { ControlsBar } from './hud/ControlsBar';
import { WebGLFallback } from './hud/WebGLFallback';

// Lazy-loaded 3D chunk as strictly mandated
const AttackTheaterScene = React.lazy(() => import('./scene/AttackTheaterScene'));

interface TheaterContainerProps {
  initialEvents?: TheaterEvent[];
  streamEvent?: TheaterEvent | null;
  isDemo?: boolean;
}

export const TheaterContainer: React.FC<TheaterContainerProps> = ({
  initialEvents = [],
  streamEvent = null,
  isDemo = false,
}) => {
  const systemReducedMotion = useReducedMotion();
  const [userReducedMotion, setUserReducedMotion] = useState<boolean | null>(null);
  const reducedMotion = userReducedMotion !== null ? userReducedMotion : systemReducedMotion;

  const [qualityTier, setQualityTier] = useQualityTier('high');
  const webGLSupported = useWebGLSupport();

  const [enableCameraDrift, setEnableCameraDrift] = useState(true);
  const [maskIps, setMaskIps] = useState(false);

  const [eventsList, setEventsList] = useState<TheaterEvent[]>(initialEvents);
  const [selectedEvent, setSelectedEvent] = useState<TheaterEvent | null>(
    initialEvents.length > 0 ? initialEvents[0] : null
  );

  const director = useMemo(() => new AttackTheaterDirector(), []);
  const [activeWaves, setActiveWaves] = useState<SceneCommand[]>([]);

  // Rate-limited aria-live announcement text
  const [ariaLiveText, setAriaLiveText] = useState('');
  const lastAriaAnnouncementTime = useRef(0);

  // Ingest stream events or prop events
  useEffect(() => {
    if (!streamEvent) return;

    setEventsList((prev) => [streamEvent, ...prev.slice(0, 49)]); // keep last 50
    setSelectedEvent(streamEvent);

    director.processEvent(streamEvent);

    // Rate-limited aria announcement (max 1 per 2 seconds)
    const now = Date.now();
    if (now - lastAriaAnnouncementTime.current > 2000) {
      lastAriaAnnouncementTime.current = now;
      const statusNote = streamEvent.is_novel ? ' (Unfamiliar behavior observed)' : '';
      setAriaLiveText(
        `Flow verdict: ${streamEvent.predicted_class} with ${(streamEvent.confidence * 100).toFixed(0)}% confidence.${statusNote}`
      );
    }
  }, [streamEvent, director]);

  // Director tick loop (runs at ~30fps to clean expired waves)
  useEffect(() => {
    const interval = setInterval(() => {
      const state = director.update();
      setActiveWaves(state.activeWaves);
    }, 32);

    return () => clearInterval(interval);
  }, [director]);

  const currentWave = activeWaves.length > 0 ? activeWaves[0] : null;
  const isStub = selectedEvent?.is_stub || currentWave?.isStub || false;

  return (
    <div className="flex-1 flex flex-col h-full bg-dark-950 relative overflow-hidden select-none">
      {/* Screen Reader Aria-Live Region */}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {ariaLiveText}
      </div>

      {/* Mandatory Honesty Strip at Top */}
      <HonestyStrip isDemo={isDemo} isStub={isStub} />

      {/* Main 3D Stage / Fallback Area */}
      <div className="flex-1 relative w-full h-full min-h-0">
        {webGLSupported ? (
          <Suspense
            fallback={
              <div className="w-full h-full flex items-center justify-center font-mono text-sm text-neon-cyan animate-pulse">
                Initializing Attack Theater 3D Engine...
              </div>
            }
          >
            <AttackTheaterScene
              activeWaves={activeWaves}
              qualityTier={qualityTier}
              reducedMotion={reducedMotion}
              enableCameraDrift={enableCameraDrift}
            />
          </Suspense>
        ) : (
          <WebGLFallback activeWaves={activeWaves} reducedMotion={reducedMotion} />
        )}

        {/* DOM HUD OVERLAY */}
        <ChamberLabels
          sourceIp={selectedEvent?.flow_metadata?.source_ip || currentWave?.sourceIp}
          sourcePort={selectedEvent?.flow_metadata?.source_port || currentWave?.sourcePort}
          destinationIp={selectedEvent?.flow_metadata?.destination_ip || currentWave?.destinationIp}
          destinationPort={selectedEvent?.flow_metadata?.destination_port || currentWave?.destinationPort}
          maskIps={maskIps}
          onToggleMaskIps={() => setMaskIps(!maskIps)}
        />

        {/* Bottom Left: Verdict Card */}
        <div className="absolute bottom-6 left-6 z-10">
          <VerdictCard currentEvent={selectedEvent} />
        </div>

        {/* Bottom Right: Timeline & Controls */}
        <div className="absolute bottom-6 right-6 z-10 flex flex-col items-end gap-3">
          <StyleLegend />
          <EventTimeline
            events={eventsList}
            selectedEventId={selectedEvent?.id}
            onSelectEvent={(ev) => {
              setSelectedEvent(ev);
              director.processEvent(ev);
            }}
          />
          <ControlsBar
            qualityTier={qualityTier}
            onChangeQuality={setQualityTier}
            reducedMotion={reducedMotion}
            onToggleReducedMotion={() => setUserReducedMotion(!reducedMotion)}
            enableCameraDrift={enableCameraDrift}
            onToggleCameraDrift={() => setEnableCameraDrift(!enableCameraDrift)}
            streamStatus={isDemo ? 'demo' : 'offline'}
          />
        </div>
      </div>
    </div>
  );
};
