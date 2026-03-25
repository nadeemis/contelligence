---
name: financial-analysis
description: >
  Extract and analyse financial statements (annual reports, balance sheets, P&L,
  cash flow) to calculate 30+ financial ratios, perform trend analysis, detect
  anomalies, and produce analyst-grade financial health reports. Use when asked to
  "analyse financial statements", "calculate financial ratios", "review annual
  report", "financial health check", "balance sheet analysis", "P&L analysis",
  "cash flow analysis", or any financial document analysis task.
license: MIT
metadata:
  version: "1.0.0"
  tags: ["finance"]
---

# Financial Statement Analyzer

## When to Use This Skill

Use this Skill when the user asks to:
- Analyse financial statements or annual reports
- Calculate financial ratios
- Assess company financial health
- Perform horizontal or vertical analysis
- Detect financial anomalies or red flags
- Compare financial performance across periods or peers
- Produce financial health reports

## Workflow

Financial Analysis Progress:
- [ ] Step 1: Extract financial data
- [ ] Step 2: Structure into standard format
- [ ] Step 3: Calculate financial ratios
- [ ] Step 4: Perform trend analysis
- [ ] Step 5: Detect anomalies
- [ ] Step 6: Produce report
- [ ] Step 7: Persist output

### Step 1: Extract financial data

Route documents to appropriate extraction:
- PDF annual reports → Tool: call_doc_intelligence({ source, model: "prebuilt-layout" })
- XLSX spreadsheets  → Tool: extract_xlsx({ source })
- PDF (text-based)   → Tool: extract_pdf({ source })

Use Doc Intelligence for complex table extraction from annual reports — tables with merged cells, multi-level headers, and footnotes.

### Step 2: Structure into standard format

Map extracted data into three standard statements:

**Balance Sheet** (point-in-time):
- Current Assets: Cash, Receivables, Inventory, Other
- Non-Current Assets: PP&E, Intangibles, Investments, Other
- Current Liabilities: Payables, Short-term Debt, Accruals, Other
- Non-Current Liabilities: Long-term Debt, Deferred Tax, Other
- Equity: Share Capital, Retained Earnings, Other

**Income Statement** (period):
- Revenue, COGS, Gross Profit
- Operating Expenses (SGA, R&D, D&A, Other)
- Operating Income (EBIT)
- Interest, Tax, Net Income

**Cash Flow Statement** (period):
- Operating Cash Flow
- Investing Cash Flow
- Financing Cash Flow
- Net Cash Change

### Step 3: Calculate financial ratios

#### Liquidity Ratios
| Ratio | Formula | Healthy Range |
|---|---|---|
| Current Ratio | Current Assets / Current Liabilities | 1.5 – 3.0 |
| Quick Ratio | (Current Assets − Inventory) / Current Liabilities | 1.0 – 2.0 |
| Cash Ratio | Cash / Current Liabilities | 0.5 – 1.0 |
| Working Capital | Current Assets − Current Liabilities | Positive |

#### Profitability Ratios
| Ratio | Formula | Notes |
|---|---|---|
| Gross Margin | Gross Profit / Revenue × 100% | Industry-dependent |
| Operating Margin | EBIT / Revenue × 100% | |
| Net Margin | Net Income / Revenue × 100% | |
| ROA | Net Income / Total Assets × 100% | |
| ROE | Net Income / Shareholders' Equity × 100% | |
| ROIC | NOPAT / Invested Capital × 100% | |

#### Leverage Ratios
| Ratio | Formula | Healthy Range |
|---|---|---|
| Debt-to-Equity | Total Debt / Total Equity | < 2.0 (industry-dependent) |
| Debt-to-Assets | Total Debt / Total Assets | < 0.6 |
| Interest Coverage | EBIT / Interest Expense | > 3.0 |
| Equity Multiplier | Total Assets / Total Equity | |

#### Efficiency Ratios
| Ratio | Formula | Notes |
|---|---|---|
| Asset Turnover | Revenue / Total Assets | |
| Inventory Turnover | COGS / Average Inventory | |
| Receivables Turnover | Revenue / Average Receivables | |
| Days Sales Outstanding | 365 / Receivables Turnover | |
| Days Inventory Outstanding | 365 / Inventory Turnover | |
| Days Payable Outstanding | 365 / (COGS / Average Payables) | |
| Cash Conversion Cycle | DSO + DIO − DPO | |

#### Valuation Indicators (if market data available)
| Ratio | Formula |
|---|---|
| EV/EBITDA | Enterprise Value / EBITDA |
| P/E | Price / Earnings per Share |
| P/B | Price / Book Value per Share |

### Step 4: Perform trend analysis

**Horizontal analysis** — Compare each line item across periods:
- YoY growth rate for each line item
- CAGR over the full period
- Flag items growing significantly faster or slower than revenue

**Vertical analysis** — Express each line item as % of revenue (income) or total assets (balance sheet):
- Compare composition across periods
- Flag structural shifts (e.g., COGS as % of revenue increasing)

### Step 5: Detect anomalies

Flag items matching these red flag patterns:

| Red Flag | Detection Rule |
|---|---|
| Revenue/receivables divergence | Revenue growing but receivables growing faster (>1.5× rate) |
| Cash flow/income divergence | Net income positive but operating cash flow negative |
| Inventory build-up | Inventory growing faster than COGS |
| Debt spike | Debt-to-equity increased >50% YoY |
| Margin compression | Gross or operating margin declining >300bps YoY |
| Working capital deterioration | Cash conversion cycle increasing >20% |
| Goodwill impairment risk | Goodwill > 50% of total assets |
| Going concern indicators | Current ratio <1.0 AND negative operating cash flow |

### Step 6: Produce report

#### Financial Health Summary
| Metric | Value | Assessment |
|---|---|---|
| Overall health rating | | Strong / Adequate / Concerning / Critical |
| Liquidity | | |
| Profitability | | |
| Leverage | | |
| Efficiency | | |

#### Key Financial Ratios
[Tables from Step 3 with calculated values]

#### Trend Analysis
| Line Item | Period 1 | Period 2 | Period 3 | YoY Change | Trend |
|---|---|---|---|---|---|

#### Anomalies & Red Flags
| Flag | Metric | Value | Threshold | Severity | Explanation |
|---|---|---|---|---|---|

#### Peer Comparison (if multiple companies provided)
| Ratio | Company A | Company B | Industry Avg |
|---|---|---|---|

#### Narrative Assessment
3-5 paragraph analysis covering financial health, key trends, risks, and outlook.

### Step 7: Persist output

Tool: local_files({ path: "~/contelligence-output/financial/<company>/<period>.md", content: <report> })

## Constraints
- This is financial analysis, not investment advice. Include disclaimer.
- Only calculate ratios from data present in the documents — never fabricate line items.
- When data is missing or unclear, note "not available" rather than estimating.
- Industry-dependent ratios should note the industry context for proper interpretation.