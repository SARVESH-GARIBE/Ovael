import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { ATTACKER_LINES, VICTIM_LINES, type StageState } from '../lib/mood';
import { Attacker } from './Attacker';
import { Victim } from './Victim';

/**
 * The attack stage: two sandbox containers (attacker, victim) drawn as 3D boxes, each with its
 * character standing underneath, and real-looking packets travelling between them.
 *
 * A packet is a small card showing what the wire would carry (protocol, flag, destination port),
 * built from the live detection when there is one. When the attacker is blocked a firewall goes up
 * in front of the victim, packets stop at it and are counted as dropped.
 *
 * Each unit (container + character) can be dragged, or moved with the arrow keys when focused.
 */

const W = 800;
const H = 350;
const FLOOR = 334;
const BOX_W = 176; // front face
const BOX_H = 112;
const DEPTH_X = 24; // isometric depth offset
const DEPTH_Y = -16;
const BOX_TOP = -232; // front face top, relative to the unit's floor point
const CHAR_SCALE = 0.52;

type Who = 'attacker' | 'victim';
interface Pos {
  x: number;
  y: number;
}

interface PacketKind {
  color: string;
  dur: number; // seconds in flight
  perSecond: number;
  label: (port: number, n: number) => string;
}

const SCAN_PORTS = [21, 22, 23, 25, 53, 80, 110, 135, 139, 443, 445, 1433, 3306, 3389, 5900, 8080];

const KINDS: Record<string, PacketKind> = {
  dos_flood: {
    color: '#E4572E',
    dur: 1.5,
    perSecond: 3,
    label: (p) => `TCP  SYN  → :${p || 80}  60 B`,
  },
  port_scan: {
    color: '#E8B04B',
    dur: 1.7,
    perSecond: 2.6,
    label: (_p, n) => `TCP  SYN  → :${SCAN_PORTS[n % SCAN_PORTS.length]}`,
  },
  slow_dos: {
    color: '#E8B04B',
    dur: 3.2,
    perSecond: 0.9,
    label: () => 'HTTP  GET /  (header unfinished)',
  },
  brute_force: {
    color: '#E4572E',
    dur: 1.8,
    perSecond: 1.6,
    label: (p, n) =>
      p === 21 ? `FTP  USER/PASS  try ${n + 1}` : `SSH  login  try ${n + 1}  → :22`,
  },
  web_attack: {
    color: '#E4572E',
    dur: 2,
    perSecond: 1.2,
    label: (_p, n) => (n % 2 ? "HTTP  GET /item?id=1'--" : 'HTTP  POST /comment  <script>'),
  },
  botnet: {
    color: '#B9A9E8',
    dur: 2.2,
    perSecond: 1,
    label: (p) => `TCP  PSH  → :${p || 8080}  beacon`,
  },
  unknown: {
    color: '#B9A9E8',
    dur: 2.2,
    perSecond: 1.1,
    label: (p) => `TCP  → :${p || 8080}  unfamiliar`,
  },
  learned: {
    color: '#B9A9E8',
    dur: 2,
    perSecond: 1.2,
    label: (p) => `TCP  → :${p || 8080}  learned`,
  },
};
const BENIGN: PacketKind = {
  color: '#5B88B2',
  dur: 2.6,
  perSecond: 0.7,
  label: (_p, n) => (n % 2 ? 'TLS  → :443  1.2 KB' : 'HTTP  GET /  → :80'),
};

const SERVICES = [
  { name: 'http', port: 80 },
  { name: 'ssh', port: 22 },
  { name: 'ftp', port: 21 },
];

interface Packet {
  id: number;
  kind: PacketKind;
  label: string;
  path: string;
  dropped: boolean;
  begin: number; // SVG document time the flight starts at
}

function clamp(p: Pos): Pos {
  return {
    x: Math.min(W - 120, Math.max(120, p.x)),
    y: Math.min(FLOOR, Math.max(FLOOR - 30, p.y)),
  };
}

/* ----------------------------------------------------------------- pieces */

function Bubble({ x, y, text }: { x: number; y: number; text: string }) {
  const w = Math.max(40, text.length * 8 + 18);
  return (
    <g transform={`translate(${x},${y})`}>
      <g
        className="animate-pop"
        style={{ transformBox: 'fill-box', transformOrigin: 'center bottom' }}
      >
        <rect x={-w / 2} y={-22} width={w} height={22} rx={11} fill="#FBF9E4" />
        <path d="M-4,0 L4,0 L0,7 Z" fill="#FBF9E4" />
        <text x={0} y={-7} textAnchor="middle" fontSize={11.5} fontWeight={600} fill="#000">
          {text}
        </text>
      </g>
    </g>
  );
}

/** An isometric box: front face at (-BOX_W/2, BOX_TOP), with top and right side faces. */
function Box({ accent, children }: { accent: string; children: React.ReactNode }) {
  const x0 = -BOX_W / 2;
  const x1 = BOX_W / 2;
  const y0 = BOX_TOP;
  const y1 = BOX_TOP + BOX_H;
  return (
    <g>
      <ellipse cx={DEPTH_X / 2} cy={y1 + 6} rx={BOX_W / 2 + 10} ry={7} fill="#000" opacity={0.45} />
      {/* top */}
      <path
        d={`M${x0},${y0} L${x0 + DEPTH_X},${y0 + DEPTH_Y} L${x1 + DEPTH_X},${y0 + DEPTH_Y} L${x1},${y0} Z`}
        fill="#1b3e6e"
        stroke="#255494"
        strokeWidth={1}
      />
      {/* right side */}
      <path
        d={`M${x1},${y0} L${x1 + DEPTH_X},${y0 + DEPTH_Y} L${x1 + DEPTH_X},${y1 + DEPTH_Y} L${x1},${y1} Z`}
        fill="#091629"
        stroke="#255494"
        strokeWidth={1}
      />
      {/* front */}
      <rect
        x={x0}
        y={y0}
        width={BOX_W}
        height={BOX_H}
        rx={3}
        fill="#0e203c"
        stroke="#255494"
        strokeWidth={1.2}
      />
      <rect x={x0} y={y0} width={BOX_W} height={3} fill={accent} opacity={0.9} />
      {children}
    </g>
  );
}

function Led({ x, y, color, blink }: { x: number; y: number; color: string; blink?: boolean }) {
  return (
    <circle cx={x} cy={y} r={3.2} fill={color} className={blink ? 'animate-flicker' : undefined}>
      <title>status</title>
    </circle>
  );
}

function AttackerBox({ state }: { state: StageState }) {
  const active = state.attacker === 'attacking' || state.attacker === 'sneaky';
  const blocked = state.attacker === 'blocked';
  const led = blocked ? '#E8B04B' : active ? '#E4572E' : '#3f6285';
  const x0 = -BOX_W / 2 + 12;
  const y0 = BOX_TOP + 12;
  return (
    <Box accent={active ? '#E4572E' : '#3f6285'}>
      <text x={x0} y={y0 + 10} fontSize={11} fontWeight={700} fill="#FBF9E4" letterSpacing={1.5}>
        ATTACKER
      </text>
      <text x={x0} y={y0 + 24} fontSize={9.5} fill="#9c9a88" fontFamily="JetBrains Mono, monospace">
        172.28.0.66 · container
      </text>
      <Led x={BOX_W / 2 - 14} y={y0 + 6} color={led} blink={active} />
      {/* terminal */}
      <rect x={x0} y={y0 + 34} width={BOX_W - 24} height={52} rx={3} fill="#000" stroke="#122C4F" />
      {[0, 1, 2].map((i) => (
        <rect
          key={i}
          x={x0 + 8}
          y={y0 + 44 + i * 12}
          width={[90, 62, 76][i] * (active || i === 0 ? 1 : 0.5)}
          height={4}
          rx={2}
          fill={blocked ? '#E8B04B' : active ? '#7CF29A' : '#3f6285'}
          opacity={0.75}
        />
      ))}
      {active && (
        <rect
          x={x0 + 8 + 80}
          y={y0 + 66}
          width={6}
          height={9}
          fill="#7CF29A"
          className="animate-flicker"
        />
      )}
      {blocked && (
        <text
          x={x0 + 8}
          y={y0 + 82}
          fontSize={8.5}
          fill="#E8B04B"
          fontFamily="JetBrains Mono, monospace"
        >
          connection refused
        </text>
      )}
    </Box>
  );
}

function VictimBox({ state, targetPort }: { state: StageState; targetPort: number | null }) {
  const underAttack = !state.blocked && (state.victim === 'scared' || state.victim === 'worried');
  const load = state.blocked
    ? 0.18
    : state.victim === 'scared'
      ? 0.55 + state.intensity * 0.09
      : state.victim === 'worried'
        ? 0.45
        : state.victim === 'confused'
          ? 0.3
          : 0.15;
  const loadColor = load > 0.7 ? '#E4572E' : load > 0.4 ? '#E8B04B' : '#5B88B2';
  const x0 = -BOX_W / 2 + 12;
  const y0 = BOX_TOP + 12;
  return (
    <Box accent={underAttack ? '#E4572E' : state.blocked ? '#5B88B2' : '#3f6285'}>
      <text x={x0} y={y0 + 10} fontSize={11} fontWeight={700} fill="#FBF9E4" letterSpacing={1.5}>
        VICTIM
      </text>
      <text x={x0} y={y0 + 24} fontSize={9.5} fill="#9c9a88" fontFamily="JetBrains Mono, monospace">
        172.28.0.10 · web server
      </text>
      <Led
        x={BOX_W / 2 - 14}
        y={y0 + 6}
        color={underAttack ? '#E4572E' : '#7CF29A'}
        blink={underAttack}
      />
      {SERVICES.map((s, i) => {
        const hit = underAttack && targetPort === s.port;
        return (
          <g key={s.name} transform={`translate(${x0},${y0 + 40 + i * 13})`}>
            <circle
              cx={3}
              cy={-3}
              r={2.6}
              fill={hit ? '#E4572E' : '#7CF29A'}
              className={hit ? 'animate-flicker' : undefined}
            />
            <text
              x={11}
              y={0}
              fontSize={9.5}
              fill={hit ? '#FBF9E4' : '#9c9a88'}
              fontFamily="JetBrains Mono, monospace"
            >
              {s.name} :{s.port}
            </text>
          </g>
        );
      })}
      {/* load / connection table */}
      <text x={x0 + 82} y={y0 + 40} fontSize={8.5} fill="#9c9a88">
        load
      </text>
      <rect x={x0 + 82} y={y0 + 46} width={66} height={7} rx={3.5} fill="#000" />
      <rect
        x={x0 + 82}
        y={y0 + 46}
        width={66 * Math.min(load, 1)}
        height={7}
        rx={3.5}
        fill={loadColor}
        style={{ transition: 'width 600ms ease, fill 600ms ease' }}
      />
    </Box>
  );
}

function Firewall({ drops }: { drops: number }) {
  return (
    <g
      className="animate-pop"
      style={{ transformBox: 'fill-box', transformOrigin: 'center bottom' }}
    >
      <rect
        x={-9}
        y={BOX_TOP - 6}
        width={18}
        height={BOX_H + 12}
        rx={3}
        fill="#122C4F"
        stroke="#5B88B2"
        strokeWidth={1.5}
      />
      {Array.from({ length: 8 }, (_, i) => (
        <line
          key={i}
          x1={-9}
          x2={9}
          y1={BOX_TOP - 6 + (i + 1) * ((BOX_H + 12) / 9)}
          y2={BOX_TOP - 6 + (i + 1) * ((BOX_H + 12) / 9)}
          stroke="#5B88B2"
          strokeWidth={0.8}
          opacity={0.6}
        />
      ))}
      <rect x={-34} y={BOX_TOP - 30} width={68} height={18} rx={9} fill="#5B88B2" />
      <text x={0} y={BOX_TOP - 18} textAnchor="middle" fontSize={9.5} fontWeight={700} fill="#000">
        FIREWALL
      </text>
      <text
        x={0}
        y={BOX_TOP + BOX_H + 22}
        textAnchor="middle"
        fontSize={10}
        fontWeight={700}
        fill="#E4572E"
        fontFamily="JetBrains Mono, monospace"
      >
        DROP ×{drops}
      </text>
    </g>
  );
}

function PacketCard({ p }: { p: Packet }) {
  const w = Math.max(70, p.label.length * 5.6 + 16);
  const dur = `${p.kind.dur}s`;
  return (
    <g opacity={0}>
      <g>
        <rect
          x={-w / 2}
          y={-10}
          width={w}
          height={20}
          rx={5}
          fill="#000"
          stroke={p.kind.color}
          strokeWidth={1.2}
        />
        <rect x={-w / 2} y={-10} width={4} height={20} rx={2} fill={p.kind.color} />
        <text
          x={-w / 2 + 9}
          y={3.5}
          fontSize={9}
          fill="#FBF9E4"
          fontFamily="JetBrains Mono, monospace"
          style={{ whiteSpace: 'pre' }}
        >
          {p.label}
        </text>
        {p.dropped && (
          <text x={w / 2 - 6} y={3.5} textAnchor="end" fontSize={9} fontWeight={700} fill="#E4572E">
            ✕
          </text>
        )}
      </g>
      <animateMotion
        begin={`${p.begin}s`}
        dur={dur}
        path={p.path}
        fill="freeze"
        calcMode="spline"
        keyPoints="0;1"
        keyTimes="0;1"
        keySplines="0.3 0 0.4 1"
      />
      <animate
        attributeName="opacity"
        begin={`${p.begin}s`}
        values="0;1;1;0"
        keyTimes={p.dropped ? '0;0.1;0.8;1' : '0;0.1;0.9;1'}
        dur={dur}
        fill="freeze"
      />
    </g>
  );
}

/* ----------------------------------------------------------------- stage */

export function Stage({
  state,
  reducedMotion = false,
}: {
  state: StageState;
  reducedMotion?: boolean;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [pos, setPos] = useState<Record<Who, Pos>>({
    attacker: { x: 175, y: FLOOR },
    victim: { x: 605, y: FLOOR },
  });
  const drag = useRef<{ who: Who; dx: number; dy: number } | null>(null);
  const [packets, setPackets] = useState<Packet[]>([]);
  const [drops, setDrops] = useState(0);
  const nextId = useRef(0);
  const posRef = useRef(pos);
  posRef.current = pos;

  const facing: 1 | -1 = pos.victim.x >= pos.attacker.x ? 1 : -1;
  const attacking = state.attacker === 'attacking' || state.attacker === 'sneaky';
  const focusPort = state.focus?.dst_port ?? null;

  useEffect(() => {
    if (!state.blocked) setDrops(0);
  }, [state.blocked]);

  // ----------------------------------------------------------------- packets
  // One steady clock reads the latest state from a ref. (Restarting a timer whenever the stage
  // state changes would reset it every 0.4 s, before a slow packet rate ever fires.)
  const live = useRef({ state, focusPort, attacking });
  live.current = { state, focusPort, attacking };
  useEffect(() => {
    if (reducedMotion) {
      setPackets([]);
      return;
    }
    const TICK = 100;
    let acc = 0;
    let n = 0;
    let lastKind: PacketKind | null = null;
    const timer = setInterval(() => {
      const { state: s, focusPort: port, attacking: hot } = live.current;
      const hostile = hot || s.blocked;
      const kind = hostile ? (KINDS[s.family ?? ''] ?? KINDS.unknown) : BENIGN;
      if (kind !== lastKind) {
        lastKind = kind;
        acc = 1; // send the first packet of a new kind immediately
      }
      const rate = hostile ? kind.perSecond * (0.7 + s.intensity * 0.12) : BENIGN.perSecond;
      acc += (rate * TICK) / 1000;
      if (acc < 1) return;
      acc -= 1;

      const { attacker: a, victim: v } = posRef.current;
      const dir = v.x >= a.x ? 1 : -1;
      // four fixed lanes across the box face, used in turn, so cards never stack on each other
      const lane = BOX_TOP + 34 + (n % 4) * 21;
      let sx: number, sy: number;
      if (kind === BENIGN) {
        // normal clients reach the victim from the internet, above the attacker
        sx = dir > 0 ? -60 : W + 60;
        sy = 26 + Math.random() * 18;
      } else {
        sx = a.x + dir * (BOX_W / 2 + DEPTH_X);
        sy = a.y + lane;
      }
      const dropped = s.blocked && kind !== BENIGN;
      // stop at the firewall when blocked, otherwise just short of the victim's face
      const ex = dropped ? v.x - dir * (BOX_W / 2 + 64) : v.x - dir * (BOX_W / 2 + 36);
      const ey = v.y + lane;
      const mx = (sx + ex) / 2;
      const my = Math.min(sy, ey) - 18 - Math.random() * 18;
      const p: Packet = {
        id: nextId.current++,
        kind,
        label: kind.label(port ?? 0, n++),
        path: `M${sx},${sy} Q${mx},${my} ${ex},${ey}`,
        dropped,
        // SMIL animations are timed from page load; without an explicit begin, a packet added
        // later would start "already finished" and never be seen.
        begin: svgRef.current?.getCurrentTime?.() ?? 0,
      };
      setPackets((ps) => [...ps.slice(-10), p]);
      setTimeout(
        () => {
          setPackets((ps) => ps.filter((q) => q.id !== p.id));
          if (dropped) setDrops((d) => d + 1);
        },
        kind.dur * 1000 + 60
      );
    }, TICK);
    return () => clearInterval(timer);
  }, [reducedMotion]);

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
  const charHead = -228 * CHAR_SCALE;

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
      {/* sandbox network */}
      <line
        x1={30}
        y1={FLOOR + 6}
        x2={W - 30}
        y2={FLOOR + 6}
        stroke="#122C4F"
        strokeWidth={2}
        strokeDasharray="2 8"
        strokeLinecap="round"
      />
      <text
        x={W / 2}
        y={FLOOR + 2}
        textAnchor="middle"
        fontSize={9}
        fill="#3f6285"
        letterSpacing={2}
      >
        SANDBOX NETWORK 172.28.0.0/16
      </text>

      {/* attacker unit */}
      <g
        transform={`translate(${a.x},${a.y})`}
        onPointerDown={onDown('attacker')}
        onKeyDown={onKey('attacker')}
        tabIndex={0}
        role="button"
        aria-label="Attacker (drag or use arrow keys to move)"
        className="cursor-grab outline-none active:cursor-grabbing"
      >
        <AttackerBox state={state} />
        <g transform={`scale(${facing * CHAR_SCALE},${CHAR_SCALE})`}>
          <g className={state.attacker === 'idle' && !reducedMotion ? 'animate-bob' : undefined}>
            <Attacker mood={state.attacker} facing={1} />
          </g>
        </g>
        {attackerLine && <Bubble x={-58 * facing} y={charHead + 18} text={attackerLine} />}
      </g>

      {/* victim unit */}
      <g
        transform={`translate(${v.x},${v.y})`}
        onPointerDown={onDown('victim')}
        onKeyDown={onKey('victim')}
        tabIndex={0}
        role="button"
        aria-label="Victim (drag or use arrow keys to move)"
        className="cursor-grab outline-none active:cursor-grabbing"
      >
        <VictimBox state={state} targetPort={focusPort} />
        <g transform={`scale(${CHAR_SCALE})`}>
          <g className={state.victim === 'calm' && !reducedMotion ? 'animate-bob' : undefined}>
            <Victim mood={state.victim} />
          </g>
        </g>
        {victimLine && <Bubble x={58 * facing} y={charHead + 18} text={victimLine} />}
      </g>

      {/* firewall in front of the victim */}
      {state.blocked && (
        <g transform={`translate(${v.x - facing * (BOX_W / 2 + 18)},${v.y})`}>
          <Firewall drops={drops} />
        </g>
      )}

      {/* packets, on top of everything */}
      {packets.map((p) => (
        <PacketCard key={p.id} p={p} />
      ))}
    </svg>
  );
}
