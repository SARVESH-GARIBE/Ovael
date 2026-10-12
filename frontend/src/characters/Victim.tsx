import type { VictimMood } from '../lib/mood';

/**
 * The victim: big round head, dot eyes, light-blue shirt, stick limbs.
 * Feet at (0, 0).
 *
 *   calm      small smile, arms relaxed
 *   confused  the shrug: hands up, squiggly mouth (something is off but nobody knows what)
 *   worried   slanted brows, wobbly mouth, one sweat drop
 *   scared    wide eyes, open mouth, arms up, shaking
 *   relieved  happy closed eyes, big smile, thumbs up behind the shield
 *
 * Reactions are short (under half a second) and play on top of the mood, once per packet:
 *   hit    an attack packet lands: flinch away, eyes squeezed shut, grimace, impact burst
 *   smile  a normal packet arrives, or an attack packet is dropped at the firewall: happy hop
 */

export type VictimReaction = 'hit' | 'smile' | null;

const SKIN = '#fcc89b';
const SHIRT = '#8fb8d6';
const INK = '#0b0b0b';

const ARMS: Record<VictimMood, string[]> = {
  calm: ['M-24,-96 L-34,-62', 'M24,-96 L34,-62'],
  confused: ['M-24,-94 L-44,-86 L-48,-108', 'M24,-94 L44,-86 L48,-108'],
  worried: ['M-24,-96 L-30,-70 L-14,-74', 'M24,-96 L30,-70 L14,-74'],
  scared: ['M-24,-98 L-44,-124 L-50,-146', 'M24,-98 L44,-124 L50,-146'],
  relieved: ['M-24,-96 L-34,-62', 'M24,-96 L42,-106 L44,-124'],
};

export function Victim({
  mood,
  reaction = null,
  reactionKey = 0,
}: {
  mood: VictimMood;
  reaction?: VictimReaction;
  reactionKey?: number;
}) {
  const shaking = mood === 'scared' && !reaction;
  const hit = reaction === 'hit';
  const smile = reaction === 'smile';
  return (
    <g aria-label={`victim, ${mood}`}>
      <ellipse cx={0} cy={2} rx={34} ry={5} fill="#000" opacity={0.35} />
      {/* impact burst on the side the packet came from */}
      {hit && (
        <g key={`burst-${reactionKey}`} transform="translate(-58,-170)">
          <g
            className="animate-burst"
            style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
          >
            <path
              d="M0,-18 L5,-6 L18,-8 L8,1 L14,13 L1,6 L-9,16 L-6,3 L-18,-2 L-5,-6 Z"
              fill="#E4572E"
              stroke={INK}
              strokeWidth={2}
              strokeLinejoin="round"
            />
            <text x={0} y={4} textAnchor="middle" fontSize={12} fontWeight={800} fill="#FBF9E4">
              !
            </text>
          </g>
        </g>
      )}
      <g
        key={`body-${reactionKey}`}
        className={
          hit
            ? 'animate-flinch'
            : smile
              ? 'animate-hop'
              : shaking
                ? 'animate-shake'
                : 'animate-breathe'
        }
        style={{ transformBox: 'fill-box', transformOrigin: 'center bottom' }}
      >
        {/* legs */}
        <g stroke={INK} strokeWidth={4} strokeLinecap="round">
          <line x1={-11} y1={-48} x2={-13} y2={-2} />
          <line x1={11} y1={-48} x2={13} y2={-2} />
        </g>

        {/* shirt */}
        <path
          d="M-24,-104 L24,-104 L27,-46 L-27,-46 Z"
          fill={SHIRT}
          stroke={INK}
          strokeWidth={3}
          strokeLinejoin="round"
        />

        {/* arms */}
        <g stroke={INK} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round" fill="none">
          {ARMS[mood].map((d, i) => (
            <path key={i} d={d} style={{ transition: 'd 250ms ease' }} />
          ))}
        </g>
        {!reaction && mood === 'confused' && (
          <g stroke={INK} strokeWidth={3} strokeLinecap="round" fill="none">
            <path d="M-48,-108 q-4,-4 -2,-8" />
            <path d="M48,-108 q4,-4 2,-8" />
          </g>
        )}
        {!reaction && mood === 'relieved' && (
          <path d="M44,-124 l0,-8" stroke={INK} strokeWidth={4} strokeLinecap="round" />
        )}

        {/* head */}
        <circle cx={0} cy={-148} r={42} fill={SKIN} stroke={INK} strokeWidth={3} />

        {/* eyes */}
        {hit ? (
          <g
            stroke={INK}
            strokeWidth={3.2}
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          >
            <path d="M-22,-162 L-10,-156 L-22,-150" />
            <path d="M24,-162 L12,-156 L24,-150" />
          </g>
        ) : smile ? (
          <g stroke={INK} strokeWidth={3} strokeLinecap="round" fill="none">
            <path d="M-20,-153 q6,-8 12,0" />
            <path d="M10,-153 q6,-8 12,0" />
          </g>
        ) : mood === 'scared' ? (
          <g
            className="animate-blink"
            style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
          >
            <circle cx={-14} cy={-156} r={9} fill="#fff" stroke={INK} strokeWidth={2.5} />
            <circle cx={16} cy={-156} r={9} fill="#fff" stroke={INK} strokeWidth={2.5} />
            <circle cx={-15} cy={-155} r={2.5} fill={INK} />
            <circle cx={15} cy={-155} r={2.5} fill={INK} />
          </g>
        ) : mood === 'relieved' ? (
          <g stroke={INK} strokeWidth={3} strokeLinecap="round" fill="none">
            <path d="M-20,-154 q6,-7 12,0" />
            <path d="M10,-154 q6,-7 12,0" />
          </g>
        ) : (
          <g
            fill={INK}
            className="animate-blink"
            style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
          >
            <circle cx={-14} cy={-156} r={5} />
            <circle cx={16} cy={-156} r={5} />
          </g>
        )}

        {/* brows */}
        {(hit || ((mood === 'worried' || mood === 'scared') && !smile)) && (
          <g stroke={INK} strokeWidth={3} strokeLinecap="round">
            <line x1={-22} y1={-168} x2={-8} y2={-174} />
            <line x1={24} y1={-168} x2={10} y2={-174} />
          </g>
        )}

        {/* mouth */}
        {hit && (
          <g>
            <rect
              x={-11}
              y={-133}
              width={24}
              height={10}
              rx={4}
              fill="#fff"
              stroke={INK}
              strokeWidth={2.5}
            />
            <path
              d="M-11,-128 L13,-128 M-3,-133 L-3,-123 M5,-133 L5,-123"
              stroke={INK}
              strokeWidth={1.5}
            />
          </g>
        )}
        {smile && (
          <path
            d="M-12,-133 Q1,-116 14,-133 Z"
            fill="#5a1f1f"
            stroke={INK}
            strokeWidth={2.5}
            strokeLinejoin="round"
          />
        )}
        {!reaction && mood === 'calm' && (
          <path
            d="M-8,-130 Q2,-123 12,-130"
            fill="none"
            stroke={INK}
            strokeWidth={3}
            strokeLinecap="round"
          />
        )}
        {!reaction && mood === 'confused' && (
          <path
            d="M-10,-128 q5,-5 10,0 q5,4 10,-2"
            fill="none"
            stroke={INK}
            strokeWidth={3}
            strokeLinecap="round"
          />
        )}
        {!reaction && mood === 'worried' && (
          <path
            d="M-9,-126 q3,-4 6,0 q3,4 6,0 q3,-4 6,0"
            fill="none"
            stroke={INK}
            strokeWidth={2.5}
            strokeLinecap="round"
          />
        )}
        {!reaction && mood === 'scared' && (
          <ellipse cx={1} cy={-126} rx={7} ry={9} fill="#5a1f1f" stroke={INK} strokeWidth={2.5} />
        )}
        {!reaction && mood === 'relieved' && (
          <path
            d="M-14,-132 Q1,-114 16,-132 Z"
            fill="#5a1f1f"
            stroke={INK}
            strokeWidth={2.5}
            strokeLinejoin="round"
          />
        )}

        {/* sweat */}
        {(mood === 'worried' || mood === 'scared') && (
          <path
            d="M34,-176 q6,9 0,14 q-6,-5 0,-14 Z"
            fill="#9fd3ff"
            stroke={INK}
            strokeWidth={1.5}
            className="animate-pop"
          />
        )}
      </g>
    </g>
  );
}
