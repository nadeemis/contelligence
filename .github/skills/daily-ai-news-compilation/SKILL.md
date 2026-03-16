---
name: daily-ai-news-compilation
description: 'Compile a daily AI news digest by fetching top stories from multiple tech news sources, extracting headlines and summaries, and producing a structured report. Use when asked to "get AI news", "compile AI news", "daily AI digest", "AI news roundup", "summarize today''s AI news", "fetch latest AI headlines", "AI news report", "what''s new in AI today", "AI news briefing", or when automating daily AI intelligence gathering from web sources.'
---

# Daily AI News Compilation

A skill for compiling daily AI news digests by fetching, extracting, and summarizing the latest artificial intelligence news from multiple curated sources across the web.

## When to Use This Skill

- User asks for a daily AI news summary or digest
- User wants to compile AI news from multiple sources
- User asks "what's happening in AI today"
- User wants an automated AI news roundup or briefing
- User needs to stay current on AI industry developments
- User wants top headlines from AI/tech news sites

## Prerequisites

- The `browse_web` tool, the `web_fetch` tool, or the `scrape_web` tool.
- Ability to parse and extract content from HTML/markdown

## Important Constraints

- **Use the exact tool specified in the Notes column** of each source table below. Each source row specifies which tool to use — follow it strictly. Do not substitute a different tool.
- **Fetch sources sequentially, one at a time.** Only one browser session can be open at a time — never issue parallel browse calls. Wait for each fetch to complete before starting the next.

## Step-by-Step Workflow

### Step 1: Fetch News from Curated Sources

Fetch AI news content from this prioritized list of sources. **Fetch each source sequentially** — only one browser session can be open at a time, so you must wait for each call to complete before starting the next. **Use the exact tool specified in the Notes column for each source** — do not substitute a different tool. **You MUST fetch ALL listed sources across all tiers** — do not skip any source. If a source fails or returns no usable content, note it in the final report and move on to the next.

**Tier 1 — High-yield sources (try these first):**

| Source | URL | Notes |
|--------|-----|-------|
| The Decoder | `https://the-decoder.com/` | Use `browse_web`; excellent plain-text rendering, detailed AI coverage |
| The Verge AI | `https://www.theverge.com/ai-artificial-intelligence` | Use `browse_web`; rich content, major industry coverage |
| Hacker News | `https://news.ycombinator.com/` | Use `browse_web`; filter for AI-related posts; community-curated |

**Tier 2 — Established tech press:**

| Source | URL | Notes |
|--------|-----|-------|
| TechCrunch AI | `https://techcrunch.com/category/artificial-intelligence/` | Always use the `browse_web` tool |
| Ars Technica AI | `https://arstechnica.com/ai/` | Always use the `browse_web` tool |
| VentureBeat AI | `https://venturebeat.com/category/ai/` | Always use the `browse_web` tool |
| WIRED AI | `https://www.wired.com/tag/artificial-intelligence/` | Always use the `browse_web` tool |
| MIT Technology Review | `https://www.technologyreview.com/topic/artificial-intelligence/` | Always use the `browse_web` tool |
| AI News | `https://www.artificialintelligence-news.com/` | Always use the `browse_web` tool |
| The Information AI | `https://www.theinformation.com/technology/artificial-intelligence` | Always use the `browse_web` tool |
| Bloomberg AI | `https://www.bloomberg.com/technology` | Always use the `browse_web` tool |
| Reuters Tech | `https://www.reuters.com/technology/artificial-intelligence/` | Always use the `browse_web` tool |
| IEEE Spectrum AI | `https://spectrum.ieee.org/topic/artificial-intelligence/` | Always use the `browse_web` tool |
| Hugging Face Blog | `https://huggingface.co/blog` | Always use the `browse_web` tool |
| OpenAI Blog | `https://openai.com/blog` | Always use the `browse_web` tool |
| Anthropic News | `https://www.anthropic.com/news` | Always use the `browse_web` tool |
| Google AI Blog | `https://blog.google/technology/ai/` | Always use the `browse_web` tool |
| Meta AI Blog | `https://ai.meta.com/blog/` | Always use the `browse_web` tool |

**Tier 3 — Reddit communities:**

Use `web_fetch` to fetch each subreddit page sequentially. Append `.json` to the URL for structured data when possible. Use the tool specified in each row's Notes column. **Fetch every subreddit listed below — do not skip any.**

| Subreddit | URL | Focus |
|-----------|-----|-------|
| r/artificial | `https://www.reddit.com/r/artificial/hot.json?limit=10` | Use `web_fetch`; general AI news and discussion |
| r/MachineLearning | `https://www.reddit.com/r/MachineLearning/hot.json?limit=10` | Use `web_fetch`; ML research, papers, industry news |
| r/LocalLLaMA | `https://www.reddit.com/r/LocalLLaMA/hot.json?limit=10` | Use `web_fetch`; open-source LLMs, local inference, quantization |
| r/OpenAI | `https://www.reddit.com/r/OpenAI/hot.json?limit=10` | Use `web_fetch`; OpenAI product news and discussion |
| r/ClaudeAI | `https://www.reddit.com/r/ClaudeAI/hot.json?limit=10` | Use `web_fetch`; Anthropic Claude news and usage tips |
| r/singularity | `https://www.reddit.com/r/singularity/hot.json?limit=10` | Use `web_fetch`; AGI progress, frontier model news |
| r/StableDiffusion | `https://www.reddit.com/r/StableDiffusion/hot.json?limit=10` | Use `web_fetch`; image generation models and tools |
| r/ChatGPT | `https://www.reddit.com/r/ChatGPT/hot.json?limit=10` | Use `web_fetch`; ChatGPT features, tips, and news |
| r/ArtificialIntelligence | `https://www.reddit.com/r/ArtificialIntelligence/hot.json?limit=10` | Use `web_fetch`; broad AI industry discussion |
| r/LLMDevs | `https://www.reddit.com/r/LLMDevs/hot.json?limit=10` | Use `web_fetch`; LLM development, tooling, frameworks |
| r/GitHub | `https://www.reddit.com/r/GitHub/hot.json?limit=10` | Use `web_fetch`; GitHub-related news and discussions |

### Step 2: Extract Top Stories

From each source that returns usable content, extract the **top 3 news items**. For each item, capture:

- **Headline** — the article title
- **Source** — which site it came from
- **Date** — publication date (if available)
- **Summary** — 2-3 sentence summary of the story
- **Key entities** — companies, people, products mentioned

### Step 3: Deduplicate Across Sources

The same story often appears on multiple sites. Group stories by topic and merge duplicates, noting which sources covered each story.

### Step 4: Categorize Stories

Assign each unique story to one or more categories:

| Category | Description |
|----------|-------------|
| **Models & Research** | New model releases, benchmarks, papers, architecture innovations |
| **Products & Features** | Product launches, feature updates, API changes |
| **Business & Funding** | Funding rounds, acquisitions, IPOs, partnerships, layoffs |
| **Policy & Ethics** | Regulation, safety, bias, legal proceedings, government action |
| **Open Source** | Open-source releases, community projects, frameworks |
| **Hardware & Infrastructure** | Chips, data centers, compute, energy |

### Step 5: Produce the Summary Report

Format the final report using this structure:

```markdown
# AI News Digest — [Date]

## Top Stories

### 1. [Headline]
**Category:** [category] | **Sources:** [source1, source2]
[2-3 sentence summary]

### 2. [Headline]
...

## By Category

### Models & Research
- [bullet summaries]

### Products & Features
- [bullet summaries]

### Business & Funding
- [bullet summaries]

(omit empty categories)

## Sources Consulted
- [list of sources successfully fetched with URLs]
- [note any sources that were unavailable]
```

### Step 6: Save or Output the Report
- Using the `local_files` tool, save the report to a file named `ai-news-YYYY-MM-DD.md` under the folder `workspace/reports/` for future reference.


## Troubleshooting

| Issue | Solution |
|-------|----------|
| Source returns minimal/boilerplate content | Note it as unavailable in the report and continue to the next source |
| 429 rate limit error | Note the source as rate-limited in the report; do not retry immediately, continue to the next source |
| Duplicate stories across sources | Merge into single entry, list all sources that covered it |
| No AI stories on Hacker News front page | Filter by keywords: AI, LLM, GPT, Claude, Gemini, OpenAI, Anthropic, model, training |
| Content truncated | Use `start_index` parameter to fetch remaining content if the tool supports pagination |

## Example Output

```markdown
# AI News Digest — March 14, 2026

## Top Stories

### 1. Anthropic Drops Surcharge for 1M Token Context Windows
**Category:** Models & Research | **Sources:** The Decoder, Hacker News
Opus 4.6 and Sonnet 4.6 now offer 1M token context at standard pricing,
removing the previous 100% surcharge for requests over 200K tokens.
Media limit increased from 100 to 600 items per request.

### 2. Meta Reportedly Planning Up to 20% Workforce Cuts
**Category:** Business & Funding | **Sources:** The Decoder, The Verge
Meta may cut ~16,000 employees to offset $600B in AI infrastructure costs.
CEO Zuckerberg continues aggressive AI investment through 2028.

### 3. xAI Undergoes Full Restructuring After Co-Founder Exodus
**Category:** Business & Funding | **Sources:** The Decoder
Musk admitted xAI "was not built right first time around."
Six of twelve co-founders have departed since January.
```

## Tips for Best Results

- Run this workflow daily at a consistent time for comparable coverage
- Tier 1 sources (The Decoder, The Verge, Hacker News) reliably produce the richest content
- When saving reports, use date-based filenames: `ai-news-YYYY-MM-DD.md`
- For Hacker News, focus on posts with 50+ points for signal quality
- For Reddit, use the `.json` endpoint — it returns structured data with titles, scores, URLs, and comment counts without HTML parsing
- Reddit posts with 100+ upvotes typically signal noteworthy stories
- First-party blogs (OpenAI, Anthropic, Google, Meta) are the most authoritative source for product announcements
- Cross-reference Reddit discussions with Tier 1 sources to confirm story significance
