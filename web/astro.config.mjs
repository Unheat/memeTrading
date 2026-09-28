import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import mdx from '@astrojs/mdx';
import mermaid from 'astro-mermaid';

// https://astro.build/config
export default defineConfig({
  output: 'static',
  outDir: './dist',
  markdown: {
    shikiConfig: {
      theme: 'css-variables',
    },
  },
  integrations: [
    mermaid({
      theme: 'base',
      autoTheme: false,
      mermaidConfig: {
        startOnLoad: true,
        flowchart: {
          htmlLabels: true,
          useMaxWidth: false,
          curve: 'basis',
          nodeSpacing: 45,
          rankSpacing: 45,
          padding: 18,
        },
        themeVariables: {
          fontFamily: 'Inter, system-ui, sans-serif',
          fontSize: '12px',
          primaryColor: '#FFFFFF',
          primaryBorderColor: '#C8C0AC',
          primaryTextColor: '#181714',
          lineColor: '#5A554C',
          secondaryColor: '#F5F2E9',
          tertiaryColor: '#FAF7F0',
          edgeLabelBackground: '#FAF7F0',
          nodeBorder: '#C8C0AC',
        },
      },
    }),
    tailwind({
      applyBaseStyles: true,
    }),
    mdx(),
  ],
});
