---
name: research-synthesis
description: >
  Synthesise findings across multiple documents or web sources into a structured
  research report with inline citations, contradiction detection, and evidence
  grading. Use when asked to "research a topic across documents", "synthesise
  findings", "literature review", "compare sources", "cross-reference documents",
  "compile research report", "what do these documents say about X", or any
  multi-source analysis task.
license: MIT
metadata:
  version: "1.0.0"
  tags: ["research"]
---

# Multi-Document Research Synthesis

## When to Use This Skill

Use this Skill when the user asks to:
- Research a topic across multiple documents or sources
- Synthesise or reconcile findings from different sources
- Produce a literature review or research summary
- Detect contradictions between sources
- Grade evidence quality across a corpus
- Answer a question using multiple documents as evidence
- Compile a cross-referenced research report

## Workflow

Research Synthesis Progress:
- [ ] Step 1: Define research question and gather sources
- [ ] Step 2: Extract and chunk all sources
- [ ] Step 3: Retrieve relevant passages
- [ ] Step 4: Analyse and cross-reference
- [ ] Step 5: Detect contradictions
- [ ] Step 6: Grade evidence
- [ ] Step 7: Synthesise findings
- [ ] Step 8: Produce report
- [ ] Step 9: Persist output

### Step 1: Define research question and gather sources

Clarify:
- **Research question** — What specifically are we investigating?
- **Source corpus** — Documents in storage (local files), uploaded files, web URLs, or search index?
- **Scope constraints** — Date range, source types, specific authors/publications?

Gather sources:
Stored documents → Tool: local_files({ path })
Web sources      → Tool: browse_web({ url })
Search index     → Tool: query_search_index({ query, top_k: 50 })

### Step 2: Extract and chunk all sources

For each source:
- PDF  → Tool: extract_pdf({ source }) or call_doc_intelligence({ source })
- DOCX → Tool: extract_docx({ source })
- XLSX → Tool: extract_xlsx({ source })
- Web  → Already extracted via browse_web

Chunk each source into passages (~300-500 tokens) preserving:
- Source attribution (file name, URL, page number)
- Section context (heading hierarchy)
- Passage index within source

### Step 3: Retrieve relevant passages

For each aspect of the research question:
Build a **relevance matrix**: which passages from which sources address which aspects of the question.

### Step 4: Analyse and cross-reference

For each relevant passage:
- Extract the **claim** (what the source asserts)
- Identify **supporting evidence** (data, citations, reasoning)
- Note the **context** (methodology, assumptions, caveats)
- Tag the **stance** (supports, contradicts, neutral, or qualifies the research question)

Cross-reference claims across sources:
- **Corroboration** — Multiple sources support the same claim
- **Contradiction** — Sources make incompatible claims
- **Complementarity** — Sources address different aspects without conflict
- **Qualification** — One source adds conditions or nuance to another's claim

### Step 5: Detect contradictions

For each identified contradiction:

| Source A | Claim A | Source B | Claim B | Nature | Resolution |
|---|---|---|---|---|---|
| | | | | Direct / Partial / Contextual | Which is more credible and why |

Contradiction types:
- **Direct** — Factual claims that cannot both be true
- **Partial** — Claims that overlap but differ in scope or magnitude
- **Contextual** — Claims that appear contradictory but apply to different contexts

### Step 6: Grade evidence

Score each source and claim using the evidence grading rubric:

| Grade | Label | Criteria |
|---|---|---|
| **A** | Strong | Primary data, peer-reviewed, large sample, reproducible methodology |
| **B** | Moderate | Reputable secondary source, expert analysis, consistent with other evidence |
| **C** | Weak | Single source, opinion-based, small sample, potential bias, outdated |
| **D** | Very Weak | Anecdotal, unverified, known bias, contradicted by stronger evidence |
| **U** | Unknown | Insufficient information to assess credibility |

Factors:
- Source authority (expertise, publication venue, institutional backing)
- Methodology (if applicable — sample size, controls, replicability)
- Recency (newer data on fast-moving topics scores higher)
- Corroboration (claims supported by multiple independent sources score higher)
- Potential bias (funding source, advocacy position, commercial interest)

### Step 7: Synthesise findings

Construct a narrative synthesis that:
1. Opens with the **consensus view** — what most/strongest sources agree on
2. Addresses **key debates** — where sources disagree, with evidence for each side
3. Identifies **gaps** — aspects of the question no source adequately addresses
4. Draws **conclusions** — qualified by evidence strength
5. Uses **inline citations** — `[Source Name, p.X]` or `[URL, §Section]` for every claim

### Step 8: Produce report

#### Research Summary
| Field | Value |
|---|---|
| Research question | |
| Sources analysed | |
| Date range | |
| Evidence quality | (A/B/C distribution) |

#### Key Findings
1. **[Finding]** — [Evidence summary with citations] — Evidence grade: [A/B/C]

#### Contradictions & Debates
| Topic | Position A | Position B | Stronger Evidence | Resolution |
|---|---|---|---|---|

#### Evidence Gap Analysis
| Aspect | Coverage | Recommendation |
|---|---|---|

#### Source Assessment
| Source | Type | Recency | Authority | Relevance | Evidence Grade |
|---|---|---|---|---|---|

#### Narrative Synthesis
[Multi-paragraph synthesis with inline citations]

#### Bibliography
| # | Source | Type | Date | URL/Location |
|---|---|---|---|---|

### Step 9: Persist output

Tool: local_files({ path: "~/contelligence-output/research/<topic>/<date>.md", content: <report> })

## Edge Cases
- **Sources in different languages**: Note the language of each source; synthesise in the user's requested language.
- **Highly technical sources**: Flag domain-specific jargon and provide brief definitions.
- **Sources with different publication dates**: Weight recent sources higher for fast-evolving topics; note temporal context for each claim.
- **Very large corpus (>20 sources)**: Prioritise by relevance score; provide a tiered report (top findings from all sources, detailed analysis of top 10).

## Constraints
- Every claim in the synthesis must have at least one citation — never present unsourced assertions.
- Clearly distinguish between what sources say and your own analytical conclusions.
- When evidence is weak or conflicting, state the uncertainty explicitly.
- Do not cherry-pick — present the full range of perspectives found in the sources.