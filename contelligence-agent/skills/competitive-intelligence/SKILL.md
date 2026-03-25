---
name: competitive-intelligence
description: >
  Build structured competitive intelligence dashboards by scraping company
  websites, press releases, job postings, and news to extract product features,
  pricing signals, hiring trends, and strategic moves. Use when asked to
  "competitive analysis", "competitor research", "market landscape",
  "compare competitors", "competitive dashboard", "track competitor activity",
  "competitive briefing", or any competitive intelligence task.
license: MIT
metadata:
  version: "1.0.0"
  tags: ["strategy"]
---

# Competitive Intelligence Dashboard

## When to Use This Skill

Use this Skill when the user asks to:
- Research or analyse competitors
- Build a competitive comparison matrix
- Track competitor product launches, pricing, or hiring
- Produce a competitive briefing or market landscape
- Identify competitive threats or opportunities
- Monitor industry trends and competitor positioning

## Workflow

Competitive Intelligence Progress:
- [ ] Step 1: Define competitive scope
- [ ] Step 2: Gather intelligence from web sources
- [ ] Step 3: Extract structured signals
- [ ] Step 4: Build comparison matrix
- [ ] Step 5: Identify strategic moves and trends
- [ ] Step 6: Produce competitive briefing
- [ ] Step 7: Persist output

### Step 1: Define competitive scope

Clarify:
- **Target company** — The user's company or product
- **Competitors** — Named competitors, or discover via market research
- **Dimensions** — Product features, pricing, market segments, technology, hiring, partnerships
- **Time horizon** — Current snapshot or trend over time

### Step 2: Gather intelligence from web sources

For each competitor, scrape:
Company website    → Tool: browse_web({ url: "<homepage>" })
Product/pricing    → Tool: browse_web({ url: "<pricing-page>" })
Press releases     → Tool: browse_web({ url: "<press-or-blog>" })
Job postings       → Tool: browse_web({ url: "<careers-page>" })
News coverage      → Tool: browse_web({ url: "https://news.google.com/search?q=<company>" })

For each scraped page, extract structured data.

### Step 3: Extract structured signals

From scraped content, extract:

| Signal Category | What to Extract |
|---|---|
| **Product** | Features, capabilities, integrations, platforms, recent launches |
| **Pricing** | Pricing model (per-seat, usage, tier), price points, free tier, enterprise |
| **Technology** | Tech stack indicators (job postings), cloud providers, AI/ML capabilities |
| **Hiring** | Open roles by department, growth signals, geographic expansion |
| **Partnerships** | Announced partnerships, integrations, channel relationships |
| **Funding/M&A** | Recent funding rounds, acquisitions, investor signals |
| **Market position** | Target segments, messaging, value propositions, customer logos |
| **Sentiment** | News tone, analyst mentions, customer review trends |

### Step 4: Build comparison matrix

#### Feature Comparison
| Feature / Capability | Target | Competitor A | Competitor B | Competitor C |
|---|---|---|---|---|

#### Pricing Comparison
| Dimension | Target | Competitor A | Competitor B | Competitor C |
|---|---|---|---|---|
| Model | | | | |
| Entry price | | | | |
| Enterprise price | | | | |
| Free tier | | | | |

#### Technology Comparison
| Dimension | Target | Competitor A | Competitor B | Competitor C |
|---|---|---|---|---|

### Step 5: Identify strategic moves and trends

Analyse extracted signals for:
- **New market entries** — Competitors targeting new segments or geographies
- **Product pivots** — Significant feature additions or direction changes
- **Hiring surges** — Departments growing fast (signals investment areas)
- **Partnership patterns** — Ecosystem strategy and alliance formation
- **Pricing moves** — Price increases, new tiers, free-to-paid conversions
- **Acquisition signals** — Acqui-hires, tuck-ins, strategic acquisitions

### Step 6: Produce competitive briefing

#### Market Landscape Summary
- Total addressable market signals
- Key players and positioning map
- Market trends and dynamics

#### Competitor Profiles
For each competitor:
| Field | Value |
|---|---|
| Company | |
| Positioning | |
| Key strengths | |
| Key weaknesses | |
| Recent moves | |
| Threat level | Low / Medium / High |

#### Competitive Matrix
[Tables from Step 4]

#### Strategic Signals
| Signal | Competitor | Implication | Urgency |
|---|---|---|---|

#### Opportunities & Threats
| Type | Description | Evidence | Recommended Action |
|---|---|---|---|

#### Narrative Briefing
3-5 paragraph executive summary of the competitive landscape.

### Step 7: Persist output

Tool: local_files({ path: "~/contelligence-output/competitive/<industry>/<date>.md", content: <report> })

## Constraints
- Only use publicly available information — do not attempt to access private or gated content.
- Clearly label the date of each data point — competitive intelligence ages quickly.
- Distinguish between confirmed facts and inferred signals.
- When pricing is not publicly available, note "pricing not disclosed" rather than guessing.