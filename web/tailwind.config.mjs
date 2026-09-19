/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        obsidian: {
          DEFAULT: '#0A0D12',
          card: '#121722',
          subtle: '#181F2E',
          border: '#1E2638',
          borderHover: '#2A3650',
        },
        emerald: {
          audit: '#10B981',
          glow: 'rgba(16, 185, 129, 0.15)',
        },
        amber: {
          warning: '#F59E0B',
          glow: 'rgba(245, 158, 11, 0.15)',
        },
        cyan: {
          consensus: '#06B6D4',
          glow: 'rgba(6, 182, 212, 0.15)',
        },
        text: {
          primary: '#F1F5F9',
          secondary: '#94A3B8',
          muted: '#64748B',
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Roboto',
          'sans-serif',
        ],
        display: [
          'Plus Jakarta Sans',
          'Syne',
          'Inter',
          'sans-serif',
        ],
        mono: [
          'JetBrains Mono',
          'Geist Mono',
          'SFMono-Regular',
          'Menlo',
          'monospace',
        ],
      },
      boxShadow: {
        glowEmerald: '0 0 25px rgba(16, 185, 129, 0.2)',
        glowAmber: '0 0 25px rgba(245, 158, 11, 0.2)',
        card: '0 4px 20px -2px rgba(0, 0, 0, 0.5)',
      },
    },
  },
  plugins: [],
};
