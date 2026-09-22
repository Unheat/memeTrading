import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import mdx from '@astrojs/mdx';
import mermaid from 'astro-mermaid';

// https://astro.build/config
export default defineConfig({
  output: 'static',
  outDir: './dist',
  integrations: [
    mermaid({
      theme: 'neutral',
      autoTheme: true,
      mermaidConfig: {
        themeVariables: {
          fontFamily: 'Inter, system-ui, sans-serif',
          fontSize: '13px',
          primaryColor: '#ECE7DB',
          primaryBorderColor: '#DCD5C4',
          primaryTextColor: '#23211D',
          lineColor: '#635F57',
          secondaryColor: '#FAF9F5',
        },
      },
    }),
    tailwind({
      applyBaseStyles: true,
    }),
    mdx(),
  ],
});
