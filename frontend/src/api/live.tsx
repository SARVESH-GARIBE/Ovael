import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';

/**
 * One WebSocket per tab to WS /ws. Reconnects with backoff, and invalidates the matching REST
 * queries when an event arrives, so lists stay correct even if events were dropped while the
 * connection was down.
 */

export type LiveStatus = 'connecting' | 'open' | 'closed';

export interface LiveEvent<T = unknown> {
  type: string;
  ts?: number;
  source?: string;
  data: T;
}

type Listener = (e: LiveEvent) => void;

interface LiveContextValue {
  status: LiveStatus;
  subscribe: (fn: Listener) => () => void;
}

const LiveContext = createContext<LiveContextValue>({
  status: 'closed',
  subscribe: () => () => {},
});

const INVALIDATES: Record<string, string[][]> = {
  defense_action: [['actions'], ['incidents'], ['stats']],
  incident_update: [['incidents'], ['stats']],
  review_item: [['review-queue'], ['stats']],
  scan_complete: [['scans']],
  scan_update: [['scans']],
  model_retrained: [['models']],
};

function wsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws`;
}

export function LiveProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<LiveStatus>('connecting');
  const listeners = useRef(new Set<Listener>());
  const qc = useQueryClient();

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    let pendingInvalidations = new Set<string>();
    let flush: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      if (stopped || typeof WebSocket === 'undefined') return;
      setStatus('connecting');
      ws = new WebSocket(wsUrl());
      ws.onopen = () => {
        retry = 0;
        setStatus('open');
        qc.invalidateQueries();
      };
      ws.onmessage = (msg) => {
        let event: LiveEvent;
        try {
          event = JSON.parse(msg.data as string) as LiveEvent;
        } catch {
          return;
        }
        listeners.current.forEach((fn) => fn(event));
        for (const key of INVALIDATES[event.type] ?? [])
          pendingInvalidations.add(JSON.stringify(key));
        // Batch refetches: a flood can produce many events a second.
        if (pendingInvalidations.size && !flush) {
          flush = setTimeout(() => {
            pendingInvalidations.forEach((k) => qc.invalidateQueries({ queryKey: JSON.parse(k) }));
            pendingInvalidations = new Set();
            flush = undefined;
          }, 400);
        }
      };
      ws.onclose = () => {
        setStatus('closed');
        if (stopped) return;
        retry = Math.min(retry + 1, 6);
        timer = setTimeout(connect, 500 * 2 ** retry);
      };
      ws.onerror = () => ws?.close();
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      clearTimeout(flush);
      ws?.close();
    };
  }, [qc]);

  const subscribe = (fn: Listener) => {
    listeners.current.add(fn);
    return () => {
      listeners.current.delete(fn);
    };
  };

  return <LiveContext.Provider value={{ status, subscribe }}>{children}</LiveContext.Provider>;
}

export function useLiveStatus(): LiveStatus {
  return useContext(LiveContext).status;
}

/** Calls `handler` for every live event of the given types. */
export function useLiveEvents(types: string[], handler: (e: LiveEvent) => void): void {
  const { subscribe } = useContext(LiveContext);
  const ref = useRef(handler);
  ref.current = handler;
  const key = types.join(',');
  useEffect(
    () =>
      subscribe((e) => {
        if (key.split(',').includes(e.type)) ref.current(e);
      }),
    [subscribe, key]
  );
}
