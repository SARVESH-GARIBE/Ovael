/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Brand palette: Noir, Midnight, Ocean, Pearl Perfect
        noir: '#000000',
        midnight: {
          DEFAULT: '#122C4F',
          950: '#050c17',
          900: '#091629',
          850: '#0e203c',
          800: '#122C4F',
          700: '#1b3e6e',
          600: '#255494',
        },
        ocean: {
          DEFAULT: '#5B88B2',
          light: '#7ea4cb',
          dark: '#3f6285',
        },
        pearl: {
          DEFAULT: '#FBF9E4',
          muted: '#d8d5be',
          dim: '#9c9a88',
        },
        // Risk levels: the only colours outside the brand palette, reserved for severity.
        risk: {
          low: '#5B88B2',
          suspicious: '#B9A9E8',
          medium: '#E8B04B',
          high: '#E4572E',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', '"Segoe UI"', 'Roboto', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      keyframes: {
        bob: { '0%,100%': { transform: 'translateY(0)' }, '50%': { transform: 'translateY(-4px)' } },
        shake: {
          '0%,100%': { transform: 'translateX(0)' },
          '25%': { transform: 'translateX(-3px)' },
          '75%': { transform: 'translateX(3px)' },
        },
        type: { '0%,100%': { transform: 'translateY(0)' }, '50%': { transform: 'translateY(2px)' } },
        pop: { '0%': { transform: 'scale(0.6)', opacity: '0' }, '100%': { transform: 'scale(1)', opacity: '1' } },
        fadein: { '0%': { opacity: '0', transform: 'translateY(4px)' }, '100%': { opacity: '1', transform: 'none' } },
        blink: { '0%,94%,100%': { transform: 'scaleY(1)' }, '97%': { transform: 'scaleY(0.1)' } },
        breathe: { '0%,100%': { transform: 'scale(1,1)' }, '50%': { transform: 'scale(1.015,0.985)' } },
        flicker: { '0%,100%': { opacity: '0.9' }, '40%': { opacity: '0.5' }, '60%': { opacity: '1' } },
        slidein: { '0%': { opacity: '0', transform: 'translateX(-14px)' }, '100%': { opacity: '1', transform: 'none' } },
        rise: { '0%': { opacity: '0', transform: 'translateY(10px) scale(0.97)' }, '100%': { opacity: '1', transform: 'none' } },
        grow: { '0%': { transform: 'scaleX(0)' }, '100%': { transform: 'scaleX(1)' } },
        ping2: { '0%': { transform: 'scale(1)', opacity: '0.6' }, '100%': { transform: 'scale(2.2)', opacity: '0' } },
        flinch: {
          '0%': { transform: 'translateX(0) rotate(0)' },
          '25%': { transform: 'translateX(5px) rotate(7deg)' },
          '60%': { transform: 'translateX(-2px) rotate(-3deg)' },
          '100%': { transform: 'translateX(0) rotate(0)' },
        },
        lean: {
          '0%,100%': { transform: 'rotate(0) translateX(0)' },
          '40%': { transform: 'rotate(5deg) translateX(3px)' },
        },
        hop: { '0%,100%': { transform: 'translateY(0)' }, '40%': { transform: 'translateY(-7px)' } },
        burst: {
          '0%': { transform: 'scale(0.3)', opacity: '0' },
          '30%': { transform: 'scale(1.15)', opacity: '1' },
          '100%': { transform: 'scale(1)', opacity: '0' },
        },
        steam: {
          '0%': { transform: 'translateY(0) scale(0.6)', opacity: '0' },
          '30%': { opacity: '0.9' },
          '100%': { transform: 'translateY(-26px) scale(1.2)', opacity: '0' },
        },
      },
      animation: {
        bob: 'bob 2.4s ease-in-out infinite',
        shake: 'shake 0.25s linear infinite',
        type: 'type 0.18s ease-in-out infinite',
        pop: 'pop 0.25s ease-out both',
        fadein: 'fadein 0.3s ease-out both',
        blink: 'blink 4.5s ease-in-out infinite',
        breathe: 'breathe 3.2s ease-in-out infinite',
        flicker: 'flicker 0.6s steps(3) infinite',
        slidein: 'slidein 0.35s ease-out both',
        rise: 'rise 0.45s cubic-bezier(.2,.8,.2,1) both',
        grow: 'grow 0.7s cubic-bezier(.2,.8,.2,1) both',
        ping2: 'ping2 1.4s ease-out infinite',
        flinch: 'flinch 0.42s ease-out both',
        lean: 'lean 0.38s ease-out both',
        hop: 'hop 0.4s ease-out both',
        burst: 'burst 0.45s ease-out both',
        steam: 'steam 0.7s ease-out both',
      },
    },
  },
  plugins: [],
};
