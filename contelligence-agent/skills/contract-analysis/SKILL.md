---
name: contract-analysis
description: >
  Extract clauses from legal contracts, compare against baseline templates or
  standard terms, flag deviations, score risk per clause, and produce structured
  risk reports with recommended redlines. Use when asked to "review a contract",
  "analyse contract risk", "compare against standard terms", "flag risky clauses",
  "contract redline review", "check contract deviations", or any legal document
  analysis task.
license: MIT
metadata:
  version: "1.0.0"
  tags: ["legal"]
---

# Contract Analysis & Risk Scoring
A skill to extract clauses from legal contracts, compare against baseline templates or standard terms, flag deviations, score risk per clause, and produce structured risk reports with recommended redlines. Use when asked to "review a contract", "analyse contract risk", "compare against standard terms", "flag risky clauses", "contract redline review", "check contract deviations", or any legal document analysis task.

## When to Use This Skill

Use this Skill when the user asks to:
- Review or analyse a legal contract
- Compare a contract against standard terms or a template
- Identify risky, missing, or non-standard clauses
- Score contract risk
- Produce a contract summary with key terms
- Flag clauses needing legal review
- Extract key commercial terms (value, duration, renewal, termination)

## Workflow

Contract Analysis Progress:
- [ ] Step 1: Extract contract text
- [ ] Step 2: Identify and classify clauses
- [ ] Step 3: Compare against baseline (if provided)
- [ ] Step 4: Score risk per clause
- [ ] Step 5: Extract commercial terms
- [ ] Step 6: Produce risk report
- [ ] Step 7: Persist output

### Step 1: Extract contract text

Route the document to the appropriate extraction tool:

PDF (text-based) → Tool: extract_pdf({ source })
PDF (scanned)    → Tool: call_doc_intelligence({ source, model: "prebuilt-layout" })
DOCX             → Tool: extract_docx({ source })

If the contract is multi-file (main agreement + schedules/annexes), extract all files and tag each with its role.

### Step 2: Identify and classify clauses

Parse the extracted text into individual clauses. Classify each clause into the standard taxonomy:

#### Clause Taxonomy

| Category | Clause Types |
|---|---|
| **Commercial** | Pricing, payment terms, currency, price escalation, volume commitments |
| **Duration** | Term, renewal (auto/manual), notice period, extension |
| **Termination** | Termination for cause, termination for convenience, material breach, cure period |
| **Liability** | Limitation of liability, liability cap, exclusions, consequential damages |
| **Indemnity** | Indemnification scope, mutual/one-way, carve-outs, defense obligations |
| **IP** | IP ownership, license grants, background IP, foreground IP, open-source |
| **Data & Privacy** | Data processing, data protection, DPA references, cross-border transfer, retention |
| **Confidentiality** | Definition of confidential information, exceptions, duration, return/destruction |
| **Warranties** | Representations, warranties, disclaimers, fitness for purpose |
| **Insurance** | Required coverages, minimum amounts, evidence requirements |
| **Compliance** | Regulatory compliance, anti-bribery, sanctions, export control |
| **Dispute** | Governing law, jurisdiction, arbitration, mediation, escalation |
| **Force Majeure** | Definition, notification, mitigation, termination right |
| **Assignment** | Assignment restrictions, change of control, novation |
| **Miscellaneous** | Entire agreement, amendments, severability, waiver, notices |

For each clause, extract:
- Clause number / section reference
- Clause category (from taxonomy)
- Key terms and values
- Obligations on each party

### Step 3: Compare against baseline (if provided)

If the user provides a standard template or reference terms:
- Match clauses by category between the contract and the baseline
- Identify **deviations** — clauses that differ from the standard
- Identify **missing clauses** — standard clauses absent from the contract
- Identify **additional clauses** — clauses in the contract not in the standard
- For each deviation, describe the specific difference

If no baseline is provided, assess against general market-standard positions.

### Step 4: Score risk per clause

Apply the risk scoring rubric:

| Risk Level | Score | Criteria |
|---|---|---|
| **Critical** | 9-10 | Unlimited liability, one-sided indemnity with no cap, no termination right, IP assignment without consideration, no data protection terms |
| **High** | 7-8 | Liability cap below market standard, broad indemnity scope, auto-renewal with no exit, restrictive non-compete, weak warranty disclaimer |
| **Medium** | 4-6 | Deviation from standard terms that increases exposure but is negotiable, missing insurance requirements, short cure periods |
| **Low** | 1-3 | Minor drafting issues, slightly non-standard notice periods, formatting inconsistencies |
| **Acceptable** | 0 | Clause aligns with standard terms or market practice |

**Aggregate risk score** = weighted average across all clauses, with commercial and liability clauses weighted 2×.

### Step 5: Extract commercial terms

Build a structured summary of key commercial terms:

| Term | Value | Notes |
|---|---|---|
| Contract value | | Total / annual / per-unit |
| Payment terms | | Net days, milestones, advance |
| Currency | | |
| Term | | Duration in months/years |
| Renewal | | Auto / manual / notice period |
| Termination for convenience | | Notice period, fees |
| Liability cap | | Amount or formula |
| Insurance requirements | | Types and minimums |
| SLA / performance standards | | Metrics and penalties |

### Step 6: Produce risk report

#### Contract Summary
| Field | Value |
|---|---|
| Document | |
| Parties | |
| Effective date | |
| Contract type | |
| Overall risk score | |
| Critical findings | |

#### Clause-by-Clause Analysis
| # | Clause | Category | Risk | Finding | Recommendation |
|---|---|---|---|---|---|

#### Deviations from Standard (if baseline provided)
| Clause | Standard Position | Contract Position | Risk Impact |
|---|---|---|---|

#### Missing Clauses
| Expected Clause | Risk of Omission | Recommendation |
|---|---|---|

#### Commercial Terms Summary
[Table from Step 5]

#### Recommended Redlines
Prioritised list of suggested changes, ordered by risk score:
1. [Clause reference] — [Change description] — Risk: [Critical/High/Medium]

### Step 7: Persist output

Tool: local_files({ action: "write", path: "~/contelligence-output/<contract-name>/<date>-risk-report.md", content: <report> })

## Edge Cases
- **Multi-language contracts**: Note the language and flag that risk scoring assumes English-language legal interpretation.
- **Framework agreements with order forms**: Analyse the master terms separately from individual orders; flag inconsistencies between levels.
- **Heavily redlined documents**: If the input contains tracked changes, analyse the final (accepted) version and note that tracked changes were present.
- **Incomplete contracts**: Flag missing signature blocks, blanks, or TBD placeholders as critical findings.

## Constraints
- This skill provides **risk analysis, not legal advice**. Always include a disclaimer that findings should be reviewed by qualified legal counsel.
- Do not fabricate clause text — only report what is present in the document.
- When a clause is ambiguous, flag the ambiguity rather than assuming interpretation.
- Respect confidentiality — contract content should only be stored in the user's designated storage.