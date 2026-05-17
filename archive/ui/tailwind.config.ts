import type { Config } from 'tailwindcss'
import tailwindcssAnimate from 'tailwindcss-animate'

export default {
  darkMode: ['class'],
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}'
  ],
  theme: {
    extend: {
      colors: {
        primary: '#FFFFFF',
        primaryAccent: '#18181B',
        brand: '#FF4017',
        background: {
          DEFAULT: '#000000',
          secondary: '#0A0A0A'
        },
        surface: '#0A0A0A',
        secondary: '#f5f5f5',
        border: 'rgba(255,255,255,0.06)',
        accent: '#27272A',
        muted: '#6B6B6B',
        destructive: '#E53935',
        positive: '#22C55E',
        hover: 'rgba(255,255,255,0.04)',
        text: {
          primary: '#FFFFFF',
          secondary: '#6B6B6B'
        }
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'IBM Plex Sans', 'sans-serif'],
        mono: ['var(--font-mono)', 'IBM Plex Mono', 'monospace']
      },
      borderRadius: {
        xl: '10px'
      }
    }
  },
  plugins: [tailwindcssAnimate]
} satisfies Config
