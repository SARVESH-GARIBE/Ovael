import { describe, it, expect, beforeEach } from 'vitest';
import { AttackTheaterDirector } from '../theater/director';
import { resolveStyleFamily, normalizeClass } from '../theater/styles';
import { parseTheaterEvent, resetDroppedEventsCount, getDroppedEventsCount } from '../theater/events';

describe('AttackTheaterDirector & Styles', () => {
  let director: AttackTheaterDirector;

  beforeEach(() => {
    director = new AttackTheaterDirector();
    resetDroppedEventsCount();
  });

  it('normalizes predicted classes properly', () => {
    expect(normalizeClass('  DDoS  ')).toBe('ddos');
    expect(normalizeClass('Web Attack—SQL Injection')).toBe('web attack-sql injection');
    expect(normalizeClass('DoS   Hulk')).toBe('dos hulk');
  });

  it('maps known classes to expected style families', () => {
    expect(resolveStyleFamily('benign')).toBe('benign');
    expect(resolveStyleFamily('syn flood')).toBe('flood');
    expect(resolveStyleFamily('port scan')).toBe('scan');
    expect(resolveStyleFamily('slowloris')).toBe('slow-connection');
    expect(resolveStyleFamily('dictionary attack')).toBe('credential');
    expect(resolveStyleFamily('web attack xss')).toBe('web');
    expect(resolveStyleFamily('bot')).toBe('stealth');
    expect(resolveStyleFamily('unknown-random-attack')).toBe('unrecognized');
    expect(resolveStyleFamily('syn flood', true)).toBe('stub');
  });

  it('coalesces events of the same family within the window and scales intensity', () => {
    const baseTime = 1000;
    const ev1 = parseTheaterEvent({
      predicted_class: 'syn flood',
      is_stub: false,
      flow_metadata: { source_ip: '10.0.0.1' },
    })!;

    const wave1 = director.processEvent(ev1, baseTime);
    expect(wave1).not.toBeNull();
    expect(wave1?.intensity).toBe(1);
    expect(wave1?.eventCount).toBe(1);

    // Second event arrives 100ms later
    const ev2 = parseTheaterEvent({
      predicted_class: 'syn flood',
      is_stub: false,
    })!;
    const wave2 = director.processEvent(ev2, baseTime + 100);
    expect(wave2?.id).toBe(wave1?.id);
    expect(wave2?.eventCount).toBe(2);
    expect(wave2?.intensity).toBe(2);
  });

  it('caps concurrent waves and drops excess', () => {
    const baseTime = 10000;
    // Inject 10 distinct families/events outside merge window
    const families = [
      'benign',
      'syn flood',
      'port scan',
      'slowloris',
      'dictionary attack',
      'web attack xss',
      'bot',
      'unknown-class',
    ];

    for (let i = 0; i < families.length; i++) {
      const ev = parseTheaterEvent({ predicted_class: families[i] })!;
      director.processEvent(ev, baseTime + i * 2);
    }

    const state = director.update(baseTime + 20);
    expect(state.activeWaves.length).toBeLessThanOrEqual(6);
    expect(state.droppedEventsCount).toBeGreaterThan(0);
  });

  it('drops invalid events and increments drop counter without throwing', () => {
    expect(parseTheaterEvent({ domain: 'invalid-domain' })).toBeNull();
    expect(getDroppedEventsCount()).toBe(1);
  });

  it('enforces safety limit of at most 3 flashes per second', () => {
    const baseTime = 50000;
    expect(director.canTriggerFlash(baseTime)).toBe(true);
    expect(director.canTriggerFlash(baseTime + 100)).toBe(true);
    expect(director.canTriggerFlash(baseTime + 200)).toBe(true);

    // 4th flash within the same second must be rejected
    expect(director.canTriggerFlash(baseTime + 300)).toBe(false);
    expect(director.canTriggerFlash(baseTime + 500)).toBe(false);

    // After 1 second has elapsed, a new flash is allowed
    expect(director.canTriggerFlash(baseTime + 1050)).toBe(true);
  });

  it('supports novelty overlay independently of attack family', () => {
    const ev = parseTheaterEvent({
      predicted_class: 'port scan',
      is_novel: true,
      novelty_score: 0.88,
    })!;

    const wave = director.processEvent(ev, 1000);
    expect(wave?.family).toBe('scan');
    expect(wave?.hasNoveltyOverlay).toBe(true);
  });

  it('returns to idle after 5 seconds without events', () => {
    const ev = parseTheaterEvent({ predicted_class: 'benign' })!;
    director.processEvent(ev, 1000);

    const activeState = director.update(2000);
    expect(activeState.isIdle).toBe(false);

    const idleState = director.update(7000); // 6 seconds later
    expect(idleState.isIdle).toBe(true);
  });
});
