import typography from '@tailwindcss/typography';

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Luxury Warm Paper Palette (Zero pure #FFFFFF flash — gentle on the eyes, tactile vellum feel)
        journal: {
          bg: '#F5F2E9',        // Rich warm parchment / vellum book stock
          canvas: '#FAF7F0',    // Secondary soft warm tint
          card: '#ECE7DB',      // Card surface: muted warm stone-linen (never blinding white)
          cardSubtle: '#E4DECFA0',
          border: '#DCD5C4',    // Warm hairline rule
          borderHover: '#C8C0AC',
          ink: '#23211D',       // Warm espresso carbon ink (gentle, readable)
          lead: '#3D3933',
          secondary: '#635F57',
          muted: '#8E887E',
        },
        // Luxury Night Mode (Warm slate-noir, avoids harsh blue OLED glare)
        night: {
          bg: '#111317',
          canvas: '#161920',
          card: '#1A1E26',
          cardSubtle: '#222733',
          border: '#292F3D',
          borderHover: '#3C4559',
          ink: '#EAE7E1',       // Warm cream text on dark
          lead: '#D4D0C7',
          secondary: '#9EA3B0',
          muted: '#707584',
        },
        // Prestigious Editorial Accents
        editorial: {
          blue: '#2B579A',      // Oxford/FT corporate blue
          blueDark: '#72A1E5',
          emerald: '#1B6B4A',   // Subdued British racing/audited green
          emeraldDark: '#48BB78',
          crimson: '#A62639',   // Understated editorial red
          crimsonDark: '#F87171',
          amber: '#A16207',     // Warm brass/gold
          amberDark: '#FBBF24',
        },
      },
      fontFamily: {
        // Editorial Serif for Headlines, Decks, and Body Reading
        serif: [
          'Newsreader',
          'Charter',
          'Georgia',
          'Cambria',
          '"Times New Roman"',
          'serif',
        ],
        // Editorial Display
        display: [
          'Newsreader',
          'serif',
        ],
        // Clean Sans for UI elements & navigation
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Roboto',
          'sans-serif',
        ],
        // Tabular numbers for financial metrics & SEC accessions
        mono: [
          'JetBrains Mono',
          'SFMono-Regular',
          'Menlo',
          'monospace',
        ],
      },
      typography: () => ({
        journal: {
          css: {
            '--tw-prose-body': '#23211D',
            '--tw-prose-headings': '#181714',
            '--tw-prose-lead': '#3D3933',
            '--tw-prose-links': '#2B579A',
            '--tw-prose-bold': '#181714',
            '--tw-prose-counters': '#8E887E',
            '--tw-prose-bullets': '#8E887E',
            '--tw-prose-hr': '#DCD5C4',
            '--tw-prose-quotes': '#23211D',
            '--tw-prose-quote-borders': '#2B579A',
            '--tw-prose-captions': '#8E887E',
            '--tw-prose-code': '#23211D',
            '--tw-prose-pre-code': '#EAE7E1',
            '--tw-prose-pre-bg': '#1A1E26',
            '--tw-prose-th-borders': '#C8C0AC',
            '--tw-prose-td-borders': '#DCD5C4',
            // Dark overrides
            '--tw-prose-invert-body': '#EAE7E1',
            '--tw-prose-invert-headings': '#F5F2E9',
            '--tw-prose-invert-lead': '#D4D0C7',
            '--tw-prose-invert-links': '#72A1E5',
            '--tw-prose-invert-bold': '#FFFFFF',
            '--tw-prose-invert-counters': '#707584',
            '--tw-prose-invert-bullets': '#707584',
            '--tw-prose-invert-hr': '#292F3D',
            '--tw-prose-invert-quotes': '#EAE7E1',
            '--tw-prose-invert-quote-borders': '#72A1E5',
            '--tw-prose-invert-captions': '#9EA3B0',
            '--tw-prose-invert-code': '#EAE7E1',
            '--tw-prose-invert-pre-code': '#EAE7E1',
            '--tw-prose-invert-pre-bg': '#111317',
            '--tw-prose-invert-th-borders': '#3C4559',
            '--tw-prose-invert-td-borders': '#292F3D',
          },
        },
      }),
    },
  },
  plugins: [typography],
};
