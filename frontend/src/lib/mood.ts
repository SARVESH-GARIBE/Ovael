import type { LiveDetection, RiskLevel } from '../api/client';

/**
 * Turns the last few seconds of live detections into what the two characters feel.
 * Pure function so it is easy to test and reason about.
 */

export type AttackerMood = 'idle' | 'sneaky' | 'attacking' | 'blocked';
export type VictimMood = 'calm' | 'confused' | 'worried' | 'scared' | 'relieved';

export interface StageState {
  attacker: AttackerMood;
  victim: VictimMood;
  family: string | null; // attack family driving the packets
  level: RiskLevel;
  intensity: number; // 1..5, how many alerts in the window
  blocked: boolean;
  focus: LiveDetection | null; // the alert the stage is showing
}

export const MOOD_WINDOW_MS = 4000;
/** The block usually lands within a second; hold the "attack" beat this long so it can be seen. */
export const BLOCK_REVEAL_MS = 2000;
const ORDER: Record<RiskLevel, number> = { low: 0, suspicious: 1, medium: 2, high: 3 };

export const CALM: StageState = {
  attacker: 'idle',
  victim: 'calm',
  family: null,
  level: 'low',
  intensity: 0,
  blocked: false,
  focus: null,
};

export function deriveStage(
  recent: Array<{ at: number; d: LiveDetection }>,
  blockedIps: Set<string>,
  now: number
): StageState {
  const alerts = recent.filter((r) => now - r.at <= MOOD_WINDOW_MS && r.d.risk_level !== 'low');
  if (alerts.length === 0) return CALM;

  // The most severe recent alert decides the mood; ties go to the newest.
  const focus = alerts.reduce((a, b) =>
    ORDER[b.d.risk_level as RiskLevel] > ORDER[a.d.risk_level as RiskLevel] ||
    (ORDER[b.d.risk_level as RiskLevel] === ORDER[a.d.risk_level as RiskLevel] && b.at >= a.at)
      ? b
      : a
  ).d;
  const level = focus.risk_level as RiskLevel;
  const firstAlertAt = Math.min(
    ...recent
      .filter((r) => r.d.src_ip === focus.src_ip && r.d.risk_level !== 'low')
      .map((r) => r.at)
  );
  const blocked =
    Boolean(focus.blocked || (focus.src_ip && blockedIps.has(focus.src_ip))) &&
    now - firstAlertAt >= BLOCK_REVEAL_MS;
  const intensity = Math.min(5, Math.max(1, Math.ceil(Math.log2(alerts.length + 1))));

  if (blocked) {
    return {
      attacker: 'blocked',
      victim: 'relieved',
      family: focus.family,
      level,
      intensity,
      blocked,
      focus,
    };
  }
  const victim: VictimMood =
    level === 'high' ? 'scared' : level === 'medium' ? 'worried' : 'confused';
  const attacker: AttackerMood = level === 'suspicious' ? 'sneaky' : 'attacking';
  return { attacker, victim, family: focus.family, level, intensity, blocked, focus };
}

export const VICTIM_LINES: Record<VictimMood, string | null> = {
  calm: null,
  confused: 'huh?',
  worried: 'uh oh…',
  scared: 'help!',
  relieved: 'phew',
};

export const ATTACKER_LINES: Record<AttackerMood, string | null> = {
  idle: null,
  sneaky: 'shh…',
  attacking: 'hehe',
  blocked: 'argh!',
};
