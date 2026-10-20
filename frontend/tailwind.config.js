/** Design tokens for the HMS interface: white / light-gray surfaces, navy accents. */
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        navy: {
          50: '#eef3fb',
          100: '#d9e3f5',
          200: '#b6c8ea',
          300: '#8aa6da',
          400: '#5d7fc6',
          500: '#3d5fae',
          600: '#2d4a91',
          700: '#253c76',
          800: '#1e3160',
          900: '#16244a',
          950: '#0d1730',
        },
        surface: {
          DEFAULT: '#ffffff',
          muted: '#f6f7f9',
          sunken: '#eef0f3',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(16, 24, 40, 0.04), 0 1px 3px rgba(16, 24, 40, 0.06)',
        raised: '0 4px 12px rgba(16, 24, 40, 0.08)',
      },
      borderRadius: {
        xl: '0.875rem',
      },
    },
  },
  plugins: [],
};
