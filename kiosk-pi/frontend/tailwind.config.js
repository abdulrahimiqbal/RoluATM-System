/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
        },
        success: {
          50: '#f0fdf4',
          500: '#22c55e',
          600: '#16a34a',
        },
        error: {
          50: '#fef2f2',
          500: '#ef4444',
          600: '#dc2626',
        },
        warning: {
          50: '#fffbeb',
          500: '#f59e0b',
          600: '#d97706',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        'kiosk-xl': ['2rem', { lineHeight: '2.5rem' }],
        'kiosk-2xl': ['2.5rem', { lineHeight: '3rem' }],
        'kiosk-3xl': ['3rem', { lineHeight: '3.5rem' }],
      },
      spacing: {
        'kiosk': '1.5rem',
        'kiosk-lg': '2.5rem',
      }
    },
  },
  plugins: [],
} 