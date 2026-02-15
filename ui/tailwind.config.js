/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: '#0f1117',
        panel: '#1a1d27',
        border: '#2a2d3a',
        accent: '#6c63ff',
        'accent-hover': '#7b73ff',
        muted: '#8b8fa3',
      },
    },
  },
  plugins: [],
}
