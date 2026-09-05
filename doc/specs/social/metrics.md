# Module Spec — `app/social/metrics.py`

## Responsibility

Deterministic statistical calculations and filtering functions for social post collections:
- Mention velocity
- Rolling baseline & Z-score
- Unique author diversity ratio
- Duplicate/repost detection
- High-signal representative post selection (adapted from donor `AfterScrapeFilter`)

## Mathematical Specifications

### 1. Unique Author Ratio
$$\text{ratio} = \frac{|\{p.\text{author} \mid p \in \text{posts}, p.\text{author} \neq \text{None}\}|}{|\text{posts}|}$$
- If $|\text{posts}| = 0$, returns $1.0$.
- A ratio $< 0.3$ flags high spam/bot concentration.

### 2. Z-Score Calculation
$$\text{z} = \frac{\text{current} - \mu}{\sigma}$$
- If $\sigma = 0$ or undefined (e.g. fewer than 2 baseline points), returns $0.0$ or $None$.
- Threshold: $\text{is\_spike} = \text{True}$ if $\text{z} \ge 2.0$.

### 3. Post Deduplication
Posts are deduplicated by:
- Normalizing title: lowercase, strip punctuation and whitespace.
- If normalized titles match exactly, keep the post with higher engagement (`score + num_comments`).

### 4. Representative Post Selection (`select_representative_posts`)
From a list of posts:
- Sort by `score` descending.
- Take top 1 post by score.
- From remaining posts in top 50% by score, select 1-2 representative posts deterministically (e.g., median score or highest comment count).
- Max total representative posts per search: configurable (default 3 to 5).
