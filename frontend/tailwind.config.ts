import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#FBF8F3',
        ink: '#1A1A1A',
        mist: {
          DEFAULT: '#6B7280',
          light: '#9CA3AF',
          dark: '#4B5563',
        },
        line: '#E5E7EB',
        moss: {
          DEFAULT: '#1B4332',
          light: '#2D5A47',
          dark: '#0F2A1F',
          50: '#F0F4F1',
          100: '#DBE5DD',
          200: '#B6CDBA',
        },
        sienna: {
          DEFAULT: '#D97757',
          light: '#E8A085',
          dark: '#B85A3D',
        },
        agent: {
          assessment: '#3B82F6',
          tutor: '#10B981',
          curriculum: '#F59E0B',
          hint: '#8B5CF6',
          engagement: '#F43F5E',
          critic: '#1B4332',
          debate: '#D97757',
        },
      },
      fontFamily: {
        serif: ['Fraunces', '"Noto Serif SC"', 'Georgia', 'serif'],
        sans: ['Geist', '"Noto Sans SC"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"SF Mono"', 'Menlo', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(15, 42, 31, 0.04), 0 0 0 1px #E5E7EB',
        lift: '0 4px 16px rgba(15, 42, 31, 0.06), 0 0 0 1px #E5E7EB',
        focus: '0 0 0 3px rgba(27, 67, 50, 0.12)',
      },
      borderRadius: {
        xl2: '14px',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in': {
          '0%': { opacity: '0', transform: 'translateX(-8px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        'pulse-soft': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.6' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.3s ease-out',
        'slide-in': 'slide-in 0.3s ease-out',
        'pulse-soft': 'pulse-soft 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
} satisfies Config
