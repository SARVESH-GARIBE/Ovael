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
      },
      animation: {
        bob: 'bob 2.4s ease-in-out infinite',
        shake: 'shake 0.25s linear infinite',
        type: 'type 0.18s ease-in-out infinite',
        pop: 'pop 0.25s ease-out both',
        fadein: 'fadein 0.3s ease-out both',
      },
    },
  },
  plugins: [],
};
