/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dark: {
          950: '#06080e',
          900: '#0a0d17',
          850: '#0f1423',
          800: '#141b2f',
          700: '#1e2844',
          600: '#2d3b63',
          500: '#42558b',
        },
        neon: {
          cyan: '#00f2fe',
          blue: '#4facfe',
          violet: '#b026ff',
          purple: '#9d4edd',
          amber: '#ffb703',
          red: '#ff0055',
          green: '#00f59b',
        },
      },
      fontFamily: {
        sans: [
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          '"Helvetica Neue"',
          'Arial',
          'sans-serif',
        ],
        mono: [
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Monaco',
          'Consolas',
          '"Liberation Mono"',
          '"Courier New"',
          'monospace',
        ],
      },
    },
  },
  plugins: [],
};
