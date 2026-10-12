import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { LiveDetection } from '../api/client';
import { Stage } from '../characters/Stage';
import { CALM, deriveStage, MOOD_WINDOW_MS } from '../lib/mood';

function det(over: Partial<LiveDetection>): LiveDetection {
  return {
    id: Math.random().toString(36).slice(2),
    created_at: new Date().toISOString(),
    module: 'network',
    origin: 'simulated',
    label: 'dos_flood',
    confidence: 0.98,
    anomaly_score: 0.99,
    risk_level: 'high',
    top_features: [],
    model_version: 'network-v1',
    family: 'dos_flood',
    risk_score: 95,
    is_attack: true,
    is_unusual: true,
    models_agree: true,
    action: 'alert_and_defend',
    breakdown: {},
    probabilities: {},
    src_ip: '172.28.0.66',
    blocked: false,
    incident_count: 1,
    ...over,
  } as LiveDetection;
}

describe('deriveStage', () => {
  const now = 100_000;

  it('is calm with no recent alerts', () => {
    expect(deriveStage([], new Set(), now)).toEqual(CALM);
    const old = [{ at: now - MOOD_WINDOW_MS - 1, d: det({}) }];
    expect(deriveStage(old, new Set(), now)).toEqual(CALM);
    const benign = [{ at: now, d: det({ risk_level: 'low', family: 'benign' }) }];
    expect(deriveStage(benign, new Set(), now).victim).toBe('calm');
  });

  it('maps risk levels to moods', () => {
    expect(deriveStage([{ at: now, d: det({}) }], new Set(), now)).toMatchObject({
      attacker: 'attacking',
      victim: 'scared',
    });
    expect(
      deriveStage([{ at: now, d: det({ risk_level: 'medium' }) }], new Set(), now).victim
    ).toBe('worried');
    expect(
      deriveStage(
        [{ at: now, d: det({ risk_level: 'suspicious', family: 'unknown' }) }],
        new Set(),
        now
      )
    ).toMatchObject({
      attacker: 'sneaky',
      victim: 'confused',
    });
  });

  it('shows the attack first, then relief once the source is blocked', () => {
    const blocked = new Set(['172.28.0.66']);
    expect(deriveStage([{ at: now, d: det({}) }], blocked, now).attacker).toBe('attacking');
    const s = deriveStage(
      [
        { at: now - 4000, d: det({}) },
        { at: now, d: det({ blocked: true }) },
      ],
      blocked,
      now
    );
    expect(s).toMatchObject({ attacker: 'blocked', victim: 'relieved', blocked: true });
  });

  it('follows the most severe recent alert', () => {
    const s = deriveStage(
      [
        { at: now - 100, d: det({ risk_level: 'high', family: 'port_scan' }) },
        { at: now, d: det({ risk_level: 'medium', family: 'brute_force' }) },
      ],
      new Set(),
      now
    );
    expect(s.family).toBe('port_scan');
  });
});

describe('Stage', () => {
  it('renders both characters with their current moods', () => {
    render(
      <Stage
        state={{
          ...CALM,
          attacker: 'attacking',
          victim: 'scared',
          level: 'high',
          family: 'dos_flood',
          intensity: 3,
        }}
        reducedMotion
      />
    );
    expect(screen.getByLabelText('attacker, attacking')).toBeInTheDocument();
    expect(screen.getByLabelText('victim, scared')).toBeInTheDocument();
    expect(screen.getByText('help!')).toBeInTheDocument();
  });

  it('moves a character with the arrow keys', () => {
    render(<Stage state={CALM} reducedMotion />);
    const victim = screen.getByRole('button', { name: /Victim/ });
    const before = victim.getAttribute('transform');
    fireEvent.keyDown(victim, { key: 'ArrowLeft' });
    expect(victim.getAttribute('transform')).not.toBe(before);
  });
});
