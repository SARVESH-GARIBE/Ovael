import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HonestyStrip } from '../theater/hud/HonestyStrip';
import { VerdictCard } from '../theater/hud/VerdictCard';
import { WebGLFallback } from '../theater/hud/WebGLFallback';
import { ControlsBar } from '../theater/hud/ControlsBar';
import { QualityTier } from '../hooks/useQualityTier';
import { TheaterEvent } from '../theater/events';

describe('HUD Components & Honesty Rules', () => {
  it('HonestyStrip renders mandatory disclaimers and demo/stub banners', () => {
    const { rerender } = render(<HonestyStrip isDemo={true} isStub={true} />);

    expect(
      screen.getByText('Visualization of analyzed flows, not live packet capture.')
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Novelty represents/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText('DEMO — scripted events, not real detections')
    ).toBeInTheDocument();
    expect(
      screen.getByText('STUB MODEL — placeholder verdict')
    ).toBeInTheDocument();

    // When isDemo and isStub are false, banners are omitted
    rerender(<HonestyStrip isDemo={false} isStub={false} />);
    expect(
      screen.queryByText('DEMO — scripted events, not real detections')
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('STUB MODEL — placeholder verdict')
    ).not.toBeInTheDocument();
  });

  it('VerdictCard renders signals separately with placeholder risk badge', () => {
    const mockEvent: TheaterEvent = {
      id: 'test-1',
      domain: 'network',
      status: 'completed',
      origin: 'live',
      is_stub: false,
      predicted_class: 'syn flood',
      confidence: 0.95,
      is_novel: true,
      novelty_score: 0.88,
      risk_score: 8.5,
      severity: 'critical',
      flow_metadata: {},
      timestamp: Date.now(),
    };

    render(<VerdictCard currentEvent={mockEvent} />);

    expect(screen.getByText('syn flood')).toBeInTheDocument();
    expect(screen.getByText('95.0% conf')).toBeInTheDocument();
    expect(screen.getByText('Unfamiliar Behavior')).toBeInTheDocument();
    expect(
      screen.getByText('Unfamiliar behavior, not confirmed malicious.')
    ).toBeInTheDocument();
    expect(screen.getByText('placeholder')).toBeInTheDocument();
  });

  it('WebGLFallback renders DOM-only representation when WebGL is inactive', () => {
    render(<WebGLFallback activeWaves={[]} />);

    expect(
      screen.getByText(/DOM-Only Fallback Active/i)
    ).toBeInTheDocument();
    expect(screen.getByText('ATTACKER CHAMBER')).toBeInTheDocument();
    expect(screen.getByText('VICTIM CHAMBER')).toBeInTheDocument();
    expect(screen.getByText('Conduit Idle')).toBeInTheDocument();
  });

  it('ControlsBar allows switching quality tiers and toggling reduced motion', () => {
    let quality = 'high';
    let reducedMotion = false;
    let cameraDrift = true;

    render(
      <ControlsBar
        qualityTier={quality as QualityTier}
        onChangeQuality={(q) => {
          quality = q;
        }}
        reducedMotion={reducedMotion}
        onToggleReducedMotion={() => {
          reducedMotion = !reducedMotion;
        }}
        enableCameraDrift={cameraDrift}
        onToggleCameraDrift={() => {
          cameraDrift = !cameraDrift;
        }}
      />
    );

    const lowButton = screen.getByRole('button', { name: /low/i });
    fireEvent.click(lowButton);
    expect(quality).toBe('low');

    const reduceEffectsButton = screen.getByText(/Reduce Effects: OFF/i);
    fireEvent.click(reduceEffectsButton);
    expect(reducedMotion).toBe(true);
  });
});
