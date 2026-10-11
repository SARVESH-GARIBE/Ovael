import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { ATTACKER_LINES, VICTIM_LINES, type StageState } from '../lib/mood';
import { Attacker } from './Attacker';
import { Victim } from './Victim';

/**
 * The attack stage: attacker on one side, victim on the other, packets in between.
 *
 * Both characters can be dragged (mouse, touch or pen) or moved with the arrow keys when focused.
 * Packets are drawn from the attacker's laptop to the victim, shaped by attack family. When the
 * attacker is blocked a shield goes up and packets break against it.
 */

const W = 800;
const H = 340;
const GROUND = 300;

type Who = 'attacker' | 'victim';
interface Pos {
  x: number;
  y: number;
}

interface PacketStyle {
  color: string;
  glyph?: string;
  r: number;
  dur: number;
  perSecond: number;
  spread: number;
}

const PACKETS: Record<string, PacketStyle> = {
  dos_flood: { color: '#E4572E', r: 4, dur: 0.9, perSecond: 14, spread: 18 },
  slow_dos: { color: '#E8B04B', r: 3, dur: 3.2, perSecond: 3, spread: 6 },
  port_scan: { color: '#E8B04B', glyph: '○', r: 4, dur: 1.2, perSecond: 7, spread: 60 },
  brute_force: { color: '#E4572E', glyph: '*', r: 4, dur: 1.0, perSecond: 6, spread: 10 },
  web_attack: { color: '#E4572E', glyph: '</>', r: 4, dur: 1.4, perSecond: 3, spread: 8 },
  botnet: { color: '#B9A9E8', r: 3, dur: 2.0, perSecond: 2, spread: 4 },
  unknown: { color: '#B9A9E8', glyph: '?', r: 4, dur: 1.6, perSecond: 3, spread: 20 },
};
const BENIGN: PacketStyle = { color: '#5B88B2', r: 3, dur: 2.2, perSecond: 1.2, spread: 6 };

interface Packet {
  id: number;
  style: PacketStyle;
  path: string;
  burst: boolean;
}

function clamp(p: Pos): Pos {
  return { x: Math.min(W - 60, Math.max(60, p.x)), y: Math.min(GROUND, Math.max(230, p.y)) };
}

function Bubble({ x, y, text }: { x: number; y: number; text: string }) {
  const w = Math.max(44, text.length * 9 + 22);
  return (
    <g transform={`translate(${x},${y})`}>
      <g
        className="animate-pop"
        style={{ transformBox: 'fill-box', transformOrigin: 'center bottom' }}
      >
        <rect x={-w / 2} y={-26} width={w} height={26} rx={13} fill="#FBF9E4" />
        <path d="M-4,0 L4,0 L0,8 Z" fill="#FBF9E4" />
        <text x={0} y={-8} textAnchor="middle" fontSize={13} fontWeight={600} fill="#000">
          {text}
        </text>
      </g>
    </g>
  );
}

export function Stage({
  state,
  reducedMotion = false,
}: {
  state: StageState;
  reducedMotion?: boolean;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [pos, setPos] = useState<Record<Who, Pos>>({
    attacker: { x: 190, y: GROUND },
    victim: { x: 610, y: GROUND },
  });
  const drag = useRef<{ who: Who; dx: number; dy: number } | null>(null);
  const [packets, setPackets] = useState<Packet[]>([]);
  const nextId = useRef(0);
  const posRef = useRef(pos);
  posRef.current = pos;

  const facing: 1 | -1 = pos.victim.x >= pos.attacker.x ? 1 : -1;
  const attacking = state.attacker === 'attacking' || state.attacker === 'sneaky';

  // ----------------------------------------------------------------- packets
  useEffect(() => {
    if (reducedMotion) {
      setPackets([]);
      return;
    }
    const style =
      attacking || state.blocked ? (PACKETS[state.family ?? ''] ?? PACKETS.unknown) : BENIGN;
    const rate =
      style === BENIGN ? BENIGN.perSecond : style.perSecond * (0.6 + state.intensity * 0.2);
    const interval = 1000 / rate;
    const timer = setInterval(() => {
      const { attacker: a, victim: v } = posRef.current;
      const dir = v.x >= a.x ? 1 : -1;
      const jitter = (Math.random() - 0.5) * style.spread;
      let sx: number, sy: number;
      if (style === BENIGN) {
        // normal traffic arrives from off-stage along the floor
        sx = dir > 0 ? -10 : W + 10;
        sy = GROUND - 40 + jitter;
      } else {
        sx = a.x + 34 * dir;
        sy = a.y - 110;
      }
      const shieldX = v.x - 72 * dir;
      const ex = state.blocked && style !== BENIGN ? shieldX : v.x - 30 * dir;
      const ey = v.y - 100 + jitter;
      const mx = (sx + ex) / 2;
      const my = Math.min(sy, ey) - 40 - Math.random() * 30;
      const p: Packet = {
        id: nextId.current++,
        style,
        path: `M${sx},${sy} Q${mx},${my} ${ex},${ey}`,
        burst: state.blocked && style !== BENIGN,
      };
      setPackets((ps) => [...ps.slice(-60), p]);
      setTimeout(() => setPackets((ps) => ps.filter((q) => q.id !== p.id)), style.dur * 1000 + 50);
    }, interval);
    return () => clearInterval(timer);
  }, [attacking, state.blocked, state.family, state.intensity, reducedMotion]);

  // ----------------------------------------------------------------- dragging
  const toSvg = (e: PointerEvent): Pos => {
    const svg = svgRef.current!;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const m = svg.getScreenCTM();
    const p = m ? pt.matrixTransform(m.inverse()) : pt;
    return { x: p.x, y: p.y };
  };

  const onDown = (who: Who) => (e: PointerEvent) => {
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    const p = toSvg(e);
    drag.current = { who, dx: pos[who].x - p.x, dy: pos[who].y - p.y };
  };
  const onMove = (e: PointerEvent) => {
    if (!drag.current) return;
    const p = toSvg(e);
    const { who, dx, dy } = drag.current;
    setPos((s) => ({ ...s, [who]: clamp({ x: p.x + dx, y: p.y + dy }) }));
  };
  const onUp = () => {
    drag.current = null;
  };
  const onKey = (who: Who) => (e: KeyboardEvent) => {
    const step = e.shiftKey ? 30 : 10;
    const d: Record<string, Pos> = {
      ArrowLeft: { x: -step, y: 0 },
      ArrowRight: { x: step, y: 0 },
      ArrowUp: { x: 0, y: -step },
      ArrowDown: { x: 0, y: step },
    };
    if (!d[e.key]) return;
    e.preventDefault();
    setPos((s) => ({ ...s, [who]: clamp({ x: s[who].x + d[e.key].x, y: s[who].y + d[e.key].y }) }));
  };

  const a = pos.attacker;
  const v = pos.victim;
  const victimLine = VICTIM_LINES[state.victim];
  const attackerLine = ATTACKER_LINES[state.attacker];

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${W} ${H}`}
      className="h-full w-full touch-none select-none"
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerLeave={onUp}
      role="img"
      aria-label={`Attack stage: attacker is ${state.attacker}, victim is ${state.victim}`}
    >
      {/* floor */}
      <line
        x1={30}
        y1={GROUND + 4}
        x2={W - 30}
        y2={GROUND + 4}
        stroke="#122C4F"
        strokeWidth={2}
        strokeDasharray="2 8"
        strokeLinecap="round"
      />

      {/* packets */}
      {packets.map((p) => (
        <g key={p.id} opacity={0.95}>
          {p.style.glyph ? (
            <text
              fontSize={p.style.glyph.length > 1 ? 11 : 15}
              fontWeight={700}
              fill={p.style.color}
              textAnchor="middle"
              dy={4}
            >
              {p.style.glyph}
              <animateMotion dur={`${p.style.dur}s`} path={p.path} fill="freeze" />
            </text>
          ) : (
            <circle r={p.style.r} fill={p.style.color}>
              <animateMotion dur={`${p.style.dur}s`} path={p.path} fill="freeze" />
            </circle>
          )}
        </g>
      ))}

      {/* shield */}
      {state.blocked && (
        <g transform={`translate(${v.x - 72 * facing},${v.y - 92})`}>
          <g
            className="animate-pop"
            style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
          >
            <path
              d={facing > 0 ? 'M8,-70 Q-22,0 8,70' : 'M-8,-70 Q22,0 -8,70'}
              fill="none"
              stroke="#5B88B2"
              strokeWidth={6}
              strokeLinecap="round"
            />
            <path
              d={facing > 0 ? 'M8,-70 Q-22,0 8,70' : 'M-8,-70 Q22,0 -8,70'}
              fill="none"
              stroke="#FBF9E4"
              strokeWidth={14}
              strokeLinecap="round"
              opacity={0.12}
            />
            <g transform="translate(-8,0)">
              <rect x={-8} y={-4} width={16} height={12} rx={2} fill="#FBF9E4" />
              <path
                d="M-5,-4 v-4 a5,5 0 0 1 10,0 v4"
                fill="none"
                stroke="#FBF9E4"
                strokeWidth={2.5}
              />
            </g>
          </g>
        </g>
      )}

      {/* attacker */}
      <g
        transform={`translate(${a.x},${a.y})`}
        onPointerDown={onDown('attacker')}
        onKeyDown={onKey('attacker')}
        tabIndex={0}
        role="button"
        aria-label="Attacker (drag or use arrow keys to move)"
        className="cursor-grab outline-none focus-visible:[&>g]:opacity-90 active:cursor-grabbing"
      >
        <g transform={`scale(${facing * 1.15},1.15)`}>
          <g className={state.attacker === 'idle' && !reducedMotion ? 'animate-bob' : undefined}>
            <Attacker mood={state.attacker} facing={1} />
          </g>
        </g>
        {attackerLine && <Bubble x={0} y={-262} text={attackerLine} />}
      </g>

      {/* victim */}
      <g
        transform={`translate(${v.x},${v.y})`}
        onPointerDown={onDown('victim')}
        onKeyDown={onKey('victim')}
        tabIndex={0}
        role="button"
        aria-label="Victim (drag or use arrow keys to move)"
        className="cursor-grab outline-none active:cursor-grabbing"
      >
        <g transform="scale(1.15)">
          <g className={state.victim === 'calm' && !reducedMotion ? 'animate-bob' : undefined}>
            <Victim mood={state.victim} />
          </g>
        </g>
        {victimLine && <Bubble x={0} y={-228} text={victimLine} />}
      </g>
    </svg>
  );
}
