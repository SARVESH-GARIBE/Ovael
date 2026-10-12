import type { AttackerMood } from '../lib/mood';

/**
 * The attacker: curly dark hair, big half-lidded eyes, red shirt, navy shorts, laptop in hand.
 * Drawn in local coordinates with the feet at (0, 0); the stage positions it.
 *
 *   idle      smug half-lidded smirk, taps the laptop now and then
 *   sneaky    eyes slide sideways, finger to the keys, tiny smile
 *   attacking evil grin, eyebrows in a V, typing fast, screen glow on the face
 *   blocked   frustrated: frown, raised brows, sweat drop, red screen
 *
 * Reactions play once per packet, on top of the mood:
 *   send   a packet leaves: leans in, laptop screen flashes, wide grin, little "zap" lines
 *   fail   Ovael stopped the packet: gritted teeth, angry brows, steam from the head
 */

export type AttackerReaction = 'send' | 'fail' | null;

const SKIN = '#f2b48a';
const LID = '#b9785a';
const HAIR = '#22262d';
const SHIRT = '#c4453d';
const SHORTS = '#1d2b4f';
const INK = '#0b0b0b';

const HAIR_BLOBS: Array<[number, number, number]> = [
  [-30, -192, 17],
  [-14, -206, 19],
  [6, -209, 19],
  [25, -200, 17],
  [38, -184, 14],
  [-40, -176, 14],
  [-42, -158, 12],
  [40, -165, 11],
  [-22, -214, 12],
  [16, -218, 12],
];

export function Attacker({
  mood,
  facing = 1,
  reaction = null,
  reactionKey = 0,
}: {
  mood: AttackerMood;
  facing?: 1 | -1;
  reaction?: AttackerReaction;
  reactionKey?: number;
}) {
  const send = reaction === 'send';
  const fail = reaction === 'fail';
  const lid =
    mood === 'attacking' ? 0.55 : mood === 'blocked' ? 0.15 : mood === 'sneaky' ? 0.5 : 0.42;
  const look = mood === 'blocked' ? 0 : 4 * facing;
  const typing = mood === 'attacking' || mood === 'sneaky';
  const screen = mood === 'blocked' ? '#E4572E' : mood === 'attacking' ? '#7CF29A' : '#5B88B2';

  return (
    <g aria-label={`attacker, ${mood}`}>
      {/* shadow */}
      <ellipse cx={0} cy={2} rx={34} ry={5} fill="#000" opacity={0.35} />

      <g
        key={`body-${reactionKey}`}
        className={send ? 'animate-lean' : fail ? 'animate-shake' : 'animate-breathe'}
        style={{ transformBox: 'fill-box', transformOrigin: 'center bottom' }}
      >
        {/* legs */}
        <g stroke={INK} strokeWidth={4} strokeLinecap="round">
          <line x1={-10} y1={-60} x2={-13} y2={-2} />
          <line x1={10} y1={-60} x2={13} y2={-2} />
          <line x1={-13} y1={-2} x2={-20} y2={-2} />
          <line x1={13} y1={-2} x2={20} y2={-2} />
        </g>

        {/* shorts + shirt */}
        <rect
          x={-25}
          y={-80}
          width={50}
          height={22}
          rx={6}
          fill={SHORTS}
          stroke={INK}
          strokeWidth={2.5}
        />
        <path
          d="M-24,-132 Q0,-140 24,-132 L28,-78 L-28,-78 Z"
          fill={SHIRT}
          stroke={INK}
          strokeWidth={2.5}
          strokeLinejoin="round"
        />

        {/* arms to the laptop */}
        <g stroke={INK} strokeWidth={4} strokeLinecap="round" fill="none">
          <path d="M-22,-126 Q-36,-110 -26,-96" />
          <path d="M22,-126 Q36,-110 26,-96" />
        </g>

        {/* laptop (we see the back of the lid) */}
        <g className={typing ? 'animate-type' : undefined} style={{ transformBox: 'fill-box' }}>
          <rect
            x={-30}
            y={-112}
            width={60}
            height={34}
            rx={4}
            fill="#2a2f3a"
            stroke={INK}
            strokeWidth={2.5}
          />
          <rect
            x={-34}
            y={-80}
            width={68}
            height={6}
            rx={2}
            fill="#3a4150"
            stroke={INK}
            strokeWidth={2}
          />
          <circle
            cx={0}
            cy={-95}
            r={5}
            fill={send ? '#d8ffe4' : fail ? '#E4572E' : screen}
            opacity={0.9}
            className={mood === 'attacking' ? 'animate-flicker' : undefined}
          />
          <circle cx={-26} cy={-92} r={5} fill={SKIN} stroke={INK} strokeWidth={2} />
          <circle cx={26} cy={-92} r={5} fill={SKIN} stroke={INK} strokeWidth={2} />
        </g>

        {/* hair behind the head */}
        <g fill={HAIR}>
          {HAIR_BLOBS.map(([x, y, r], i) => (
            <circle key={i} cx={x} cy={y} r={r} />
          ))}
        </g>

        {/* head */}
        <circle cx={-35} cy={-166} r={8} fill={SKIN} stroke={INK} strokeWidth={2.5} />
        <ellipse cx={2} cy={-168} rx={34} ry={32} fill={SKIN} stroke={INK} strokeWidth={2.5} />

        {/* screen glow while attacking */}
        {mood === 'attacking' && (
          <ellipse cx={2} cy={-150} rx={30} ry={16} fill="#7CF29A" opacity={0.18} />
        )}

        {/* fringe */}
        <path
          d="M-34,-178 q6,-16 16,-10 q4,-14 16,-8 q6,-12 16,-6 q8,-10 18,0 q8,-4 4,10 L36,-188 Q4,-214 -34,-188 Z"
          fill={HAIR}
        />

        {/* eyes */}
        {[-11, 15].map((ex, i) => (
          <g
            key={i}
            className="animate-blink"
            style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
          >
            <circle cx={ex} cy={-166} r={11} fill="#fff" stroke={INK} strokeWidth={2.5} />
            <circle cx={ex + look} cy={-163} r={3.2} fill={INK} />
            {/* eyelid: covers the top `lid` share of the eye */}
            <clipPath id={`lid-${i}`}>
              <circle cx={ex} cy={-166} r={11} />
            </clipPath>
            <rect
              x={ex - 12}
              y={-178}
              width={24}
              height={22 * lid + 1}
              fill={LID}
              clipPath={`url(#lid-${i})`}
              style={{ transition: 'height 200ms ease' }}
            />
            <line
              x1={ex - 11}
              y1={-178 + 22 * lid}
              x2={ex + 11}
              y2={-178 + 22 * lid}
              stroke={INK}
              strokeWidth={2}
              clipPath={`url(#lid-${i})`}
            />
          </g>
        ))}

        {/* eyebrows */}
        <g stroke={INK} strokeWidth={3} strokeLinecap="round">
          {mood === 'attacking' || send || fail ? (
            <>
              <line x1={-20} y1={-186} x2={-4} y2={-180} />
              <line x1={24} y1={-186} x2={8} y2={-180} />
            </>
          ) : mood === 'blocked' ? (
            <>
              <line x1={-20} y1={-182} x2={-4} y2={-188} />
              <line x1={24} y1={-182} x2={8} y2={-188} />
            </>
          ) : null}
        </g>

        {/* mouth */}
        {fail ? (
          <g>
            <rect
              x={-8}
              y={-152}
              width={24}
              height={9}
              rx={3}
              fill="#fff"
              stroke={INK}
              strokeWidth={2.2}
            />
            <path
              d="M-8,-147.5 L16,-147.5 M0,-152 L0,-143 M8,-152 L8,-143"
              stroke={INK}
              strokeWidth={1.4}
            />
          </g>
        ) : send || mood === 'attacking' ? (
          <g>
            <path
              d="M-8,-147 Q4,-132 18,-147 Z"
              fill="#5a1f1f"
              stroke={INK}
              strokeWidth={2.2}
              strokeLinejoin="round"
            />
            <path d="M-6,-147 L16,-147 L15,-144 L-5,-144 Z" fill="#fff" />
          </g>
        ) : mood === 'blocked' ? (
          <path
            d="M-6,-142 q5,-5 10,0 q5,5 10,0"
            fill="none"
            stroke={INK}
            strokeWidth={2.5}
            strokeLinecap="round"
          />
        ) : (
          <path
            d={mood === 'sneaky' ? 'M-2,-146 Q6,-142 14,-147' : 'M-4,-146 Q6,-140 16,-148'}
            fill="none"
            stroke={INK}
            strokeWidth={2.5}
            strokeLinecap="round"
          />
        )}
      </g>

      {/* send: zap lines from the laptop toward the victim */}
      {send && (
        <g
          key={`zap-${reactionKey}`}
          className="animate-burst"
          style={{ transformBox: 'fill-box', transformOrigin: 'left center' }}
        >
          <g stroke="#7CF29A" strokeWidth={3} strokeLinecap="round">
            <line x1={40} y1={-104} x2={56} y2={-112} />
            <line x1={42} y1={-94} x2={60} y2={-94} />
            <line x1={40} y1={-84} x2={56} y2={-76} />
          </g>
        </g>
      )}
      {/* fail: steam from the head */}
      {fail && (
        <g key={`steam-${reactionKey}`}>
          {[-18, 4, 24].map((x, i) => (
            <circle
              key={x}
              cx={x}
              cy={-226}
              r={7}
              fill="#9c9a88"
              className="animate-steam"
              style={{
                transformBox: 'fill-box',
                transformOrigin: 'center',
                animationDelay: `${i * 90}ms`,
              }}
            />
          ))}
        </g>
      )}

      {/* blocked: sweat drop */}
      {mood === 'blocked' && (
        <path
          d="M38,-190 q5,8 0,12 q-5,-4 0,-12 Z"
          fill="#9fd3ff"
          stroke={INK}
          strokeWidth={1.5}
          className="animate-pop"
        />
      )}
    </g>
  );
}
