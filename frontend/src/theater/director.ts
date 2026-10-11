import { TheaterEvent } from './events';
import { StyleFamily, resolveStyleFamily } from './styles';

export interface SceneCommand {
  id: string;
  family: StyleFamily;
  intensity: number; // 1 to 5, derived from event count in coalescing window
  duration: number; // 1.5 to 4.0 seconds
  eventCount: number; // Multiplier counter (e.g., ×N)
  hasNoveltyOverlay: boolean;
  isStub: boolean;
  startTime: number;
  endTime: number;
  sourceIp?: string;
  destinationIp?: string;
  sourcePort?: number;
  destinationPort?: number;
  protocol?: string | number;
}

export interface DirectorState {
  activeWaves: SceneCommand[];
  droppedEventsCount: number;
  isIdle: boolean;
  flashTimestamps: number[];
}

export class AttackTheaterDirector {
  private activeWaves: SceneCommand[] = [];
  private droppedEventsCount = 0;
  private lastEventTime = 0;
  private flashTimestamps: number[] = [];

  // Configuration limits
  private readonly maxConcurrentWaves = 6;
  private readonly coalescingWindowMs = 800; // Events within 800ms merge if same family
  private readonly idleTimeoutMs = 5000; // Returns to idle after 5 seconds
  private readonly maxQueueCapacity = 20; // Hard cap on queued/active commands
  private readonly maxFlashesPerSecond = 3;

  public processEvent(event: TheaterEvent, now: number = Date.now()): SceneCommand | null {
    this.cleanExpired(now);
    this.lastEventTime = now;

    const family = resolveStyleFamily(event.predicted_class, event.is_stub);
    const hasNoveltyOverlay = Boolean(event.is_novel);
    const isStub = Boolean(event.is_stub);

    // Check if we can coalesce into an existing active wave of the same family
    const existingWave = this.activeWaves.find(
      (w) =>
        w.family === family &&
        w.hasNoveltyOverlay === hasNoveltyOverlay &&
        w.isStub === isStub &&
        now - w.startTime <= this.coalescingWindowMs
    );

    if (existingWave) {
      existingWave.eventCount += 1;
      // Intensity scales 1..5 based purely on event count
      existingWave.intensity = Math.min(5, Math.ceil(Math.log2(existingWave.eventCount + 1)));
      // Extend duration slightly up to max 4.0s
      existingWave.duration = Math.min(4.0, existingWave.duration + 0.2);
      existingWave.endTime = existingWave.startTime + existingWave.duration * 1000;
      return existingWave;
    }

    // Check capacity limit
    if (this.activeWaves.length >= this.maxConcurrentWaves) {
      if (this.activeWaves.length >= this.maxQueueCapacity) {
        // Drop oldest and increment drop counter
        this.activeWaves.shift();
        this.droppedEventsCount++;
      } else {
        // Drop current event if concurrency limit hit and not merging
        this.droppedEventsCount++;
        return null;
      }
    }

    // Create a new wave
    const duration = isStub ? 2.0 : 2.5; // Base duration between 1.5s and 4.0s
    const newWave: SceneCommand = {
      id: event.id || Math.random().toString(36).substring(2, 9),
      family,
      intensity: 1,
      duration,
      eventCount: 1,
      hasNoveltyOverlay,
      isStub,
      startTime: now,
      endTime: now + duration * 1000,
      sourceIp: event.flow_metadata?.source_ip || undefined,
      destinationIp: event.flow_metadata?.destination_ip || undefined,
      sourcePort: event.flow_metadata?.source_port ?? undefined,
      destinationPort: event.flow_metadata?.destination_port ?? undefined,
      protocol: event.flow_metadata?.protocol ?? undefined,
    };

    this.activeWaves.push(newWave);
    return newWave;
  }

  /**
   * Safe flash scheduler check: Returns true only if a flash impact is permitted.
   * Enforces that flashes never exceed 3 times per second.
   */
  public canTriggerFlash(now: number = Date.now()): boolean {
    const oneSecondAgo = now - 1000;
    this.flashTimestamps = this.flashTimestamps.filter((t) => t > oneSecondAgo);

    if (this.flashTimestamps.length < this.maxFlashesPerSecond) {
      this.flashTimestamps.push(now);
      return true;
    }
    return false;
  }

  public update(now: number = Date.now()): DirectorState {
    this.cleanExpired(now);
    const isIdle = now - this.lastEventTime >= this.idleTimeoutMs && this.activeWaves.length === 0;

    return {
      activeWaves: [...this.activeWaves],
      droppedEventsCount: this.droppedEventsCount,
      isIdle,
      flashTimestamps: [...this.flashTimestamps],
    };
  }

  private cleanExpired(now: number): void {
    this.activeWaves = this.activeWaves.filter((w) => w.endTime > now);
  }

  public reset(): void {
    this.activeWaves = [];
    this.droppedEventsCount = 0;
    this.lastEventTime = 0;
    this.flashTimestamps = [];
  }
}
