/**
 * Default sample prompts seeded into ~/.contelligence/sample-prompts.json
 * on first launch. Shared between the main process (file creation) and
 * the renderer (type definition).
 */

export interface SamplePromptCategory {
  category: string;
  prompts: string[];
}

export const defaultSamplePrompts: SamplePromptCategory[] = [
  {
    category: 'Teams & Communication',
    prompts: [
      'Pull the last 50 messages from the product-launches channel in Teams, summarize the key decisions, and list all action items with owners. Write the output at <file_path>',
      'Check my Teams chats from the past week — find any messages where I was @mentioned and create a prioritized to-do list. Send the message to myself on Teams.',
      "Read the Engineering team's General channel in Teams, identify all open questions that haven't been answered, and draft suggested responses. Write the output at <file_path>",
      "Get my calendar events for this week and cross-reference with the project-updates channel — flag any meetings where pre-read documents were shared but I haven't reviewed them.",
    ],
  },
  {
    category: 'Browser & Web Research',
    prompts: [
      "Navigate to our company's public status page, extract the current uptime percentages for each service, and produce a summary table. Write the output at <file_path>",
      'Go to the SEC EDGAR page for <company>, download the latest 10-K filing, and extract the risk factors section. Write the output at <file_path>',
      'Open our internal wiki at <url>, navigate to the onboarding checklist page, and extract every task into a structured JSON list.',
    ],
  },
  {
    category: 'Cross-Document Intelligence',
    prompts: [
      'Analyze all vendor contracts at <file_path> from the past 3 years — identify pricing trends, flag terms that have become more aggressive, and surface vendors whose SLAs have degraded over time.',
      'Compare the new draft regulation against our current policy library at <file_path> — identify every clause that creates a compliance gap, rank by risk severity, and generate remediation action items.',
      'Gather findings from these 30 research papers and 12 internal experiment reports at <file_path> — identify consensus conclusions, conflicting results, and knowledge gaps.',
    ],
  },
  {
    category: 'DevOps & Bug Triage',
    prompts: [
      'Query all active bugs in the <org>/<project> Azure DevOps project, search the web for known fixes or workarounds for each one, and produce a triage report with suggested resolutions and links to relevant Stack Overflow or GitHub issues.',
      'Fetch the top 10 highest-priority work items from <org>/<project> in Azure DevOps, browse the error messages on the web to find root-cause analysis patterns, and generate a recommended fix plan with references for each item.',
    ],
  },
  {
    category: 'Multi-Source Intelligence',
    prompts: [
      "Pull last week's messages from the #sales-deals channel in Teams, combine with the pipeline spreadsheet at <file_path>, and produce a deals-at-risk report with context from both sources.",
      "Scrape the competitor's pricing page at <url>, compare against our pricing sheet at <file_path>, and generate a competitive pricing analysis with recommendations.",
      "Read the RFP document at <file_path>, browse the client's website at <url> for background, then pull our past proposals from Teams — draft a tailored response outline.",
    ],
  },
  {
    category: 'Content Transformation',
    prompts: [
      'Take this customer feedback spreadsheet at <file_path> and categorize each entry by sentiment (positive/negative/neutral), topic, and urgency. Output a structured report with statistics.',
      'Convert this technical specification document at <file_path> into a non-technical executive briefing — keep the key decisions and risks, remove the implementation details.',
    ],
  },
  {
    category: 'Competitive & Market Analysis',
    prompts: [
      'Ingest the last 8 quarterly earnings transcripts from our top 5 competitors at <file_path>, extract strategic themes, compare R&D investment signals, and produce a competitive landscape report.',
      'Analyze these 20 product reviews and 15 support tickets at <file_path> — what are the top 3 issues customers are reporting? Are there any patterns the product team should act on?',
    ],
  },
];
