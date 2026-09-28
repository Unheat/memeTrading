import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const citationSchema = z.object({
  index: z.number(),
  sourceType: z.string().default('SEC Filing'),
  title: z.string(),
  url: z.string(),
  accession: z.string().nullable().optional(),
  filingDate: z.string().nullable().optional(),
  facts: z.array(z.string()).default([]),
  quotes: z.union([z.string(), z.array(z.string())]).optional(),
});

const videoSchema = z.object({
  provider: z.enum(['youtube', 'r2', 'local']).default('youtube'),
  id: z.string().optional(),
  url: z.string().optional(),
  aspectRatio: z.enum(['9:16', '16:9']).default('9:16'),
  title: z.string().optional(),
});

const articles = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/articles' }),
  schema: z.object({
    caseId: z.string(),
    title: z.string(),
    ticker: z.string(),
    company: z.string().optional(),
    publishedAt: z.string(),
    thesis: z.string(),
    verdict: z.enum(['Forensic Warning', 'Bullish Audit', 'Approved Long', 'Caution', 'Neutral', 'Validation Watch', 'Avoid']).default('Forensic Warning'),
    reverseDcfImpliedGrowth: z.string().optional(),
    targetValuation: z.string().optional(),
    beneishMScore: z.string().optional(),
    video: videoSchema.optional(),
    citations: z.array(citationSchema).default([]),
  }),
});

export const collections = { articles };
