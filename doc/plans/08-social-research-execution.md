# Execution Plan 08 — Social Research Tool (`search_social`)

## Purpose

Implement the social intelligence tool (`search_social`) defined in `doc/fullplan.md` and `doc/mvp-spec.md`. It provides the outer research agent with normalized social chatter and deterministic statistical signals (velocity, z-score spike detection, author diversity, engagement acceleration) from Reddit and ApeWisdom.

Social media creates hypotheses and attention signals for the outer market-research agent. It does not prove material company claims.

## Boundaries

- Social data is hypothesis evidence, never authoritative SEC proof.
- Outer agent receives statistical features and a compact set of representative posts; it does not receive thousands of raw posts or do raw math.
- The tool exposes a single normalized contract: `search_social(query: str | None = None, ticker: str | None = None, time_window: str | None = None) -> SocialSearchResult`.
- Providers stay hidden behind the tool implementation.
- Tests must be deterministic and offline (mocked API responses, no live network calls).

## Donor Code Provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.social.providers.reddit.RedditScraperAdapter` | adapted | `reference/reddit-stock-ai-agent-recommendation/stock_ai/reddit/reddit_scraper.py:22-74`, `RedditScraper.scrape` | Retain PRAW extraction and flair filtering; replace print statements with structured logging; map to frozen `SocialPost` record; gracefully handle absent credentials. |
| `app.social.metrics.select_representative_posts` | adapted | `reference/reddit-stock-ai-agent-recommendation/stock_ai/reddit/post_scrape_filter.py:15-48`, `AfterScrapeFilter._select_top_and_random_q2` | Pure deterministic quantile selection of top and representative posts without unseeded randomness in testable mode. |
| `app.social.providers.apewisdom.ApeWisdomClient` | adapted | `reference/reddit-trends/src/apewisdom.ts:75-100`, `fetchRanking` | Ported to Python `urllib.request`; strip crypto suffixes; parse mentions, 24h delta, rank, and upvotes into normalized mention metrics. |

## Required Behavior

1. **Schemas (`app/social/schemas.py`)**:
   - `SocialPost`: Frozen dataclass with `post_id`, `source`, `author`, `created_utc`, `title`, `text`, `score`, `num_comments`, `upvote_ratio`, `url`, `flair`.
   - `TrendMetrics`: Frozen dataclass with `total_mentions`, `mention_velocity_24h`, `baseline_mentions`, `z_score`, `unique_author_ratio`, `engagement_acceleration`, `is_spike`.
   - `SocialSearchResult`: Frozen dataclass with `query`, `ticker`, `time_window`, `metrics`, `representative_posts`, `source_summary`, `as_of`.
   - `SocialProviderError`: Structured recoverable error without leaking raw exceptions.

2. **Statistical Metrics (`app/social/metrics.py`)**:
   - Mention velocity: rate of change (e.g. mentions / day or 24h delta).
   - Rolling baseline & Z-score: `(current - baseline_mean) / baseline_std` to detect unusual hype spikes (threshold e.g. z >= 2.0).
   - Unique author ratio: `unique_authors / total_posts` (ratios < 0.3 signal bot spam/coordinated manipulation).
   - Duplicate filtering: Deduplicate posts by normalized title/text hash or similarity.
   - Representative posts: Select highest-signal posts (top score + representative median).

3. **Providers (`app/social/providers/`)**:
   - `ApeWisdomClient`: Queries public ApeWisdom filter API for aggregate ticker ranks/mentions/deltas.
   - `RedditProvider`: PRAW wrapper for subreddits (e.g. `wallstreetbets`, `stocks`, `investing`, `pennystocks`) with credential detection and fallback mock/empty handling.

4. **Tool Entry Point (`app/social/search.py`)**:
   - `search_social(query=None, ticker=None, time_window=None) -> SocialSearchResult`:
     Validates inputs (must supply at least `query` or `ticker`), queries available providers, calculates metrics, filters duplicates, selects representative posts, and returns immutable `SocialSearchResult`.

## Execution Steps

1. Create `doc/specs/social/schemas.md` and `doc/specs/social/metrics.md`.
2. Write red tests for schemas and metrics; implement until green.
3. Write red tests for ApeWisdom and Reddit providers; implement until green.
4. Write red tests for `search_social` tool orchestrator; implement until green.
5. Run full test suite and verify no regressions.
6. Commit the milestone.
