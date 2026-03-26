/**
 * Re-export the shared type for use in the renderer.
 * The actual prompt data is loaded at runtime from
 * ~/.contelligence/sample-prompts.json via IPC.
 */
export type { SamplePromptCategory } from '../../default-sample-prompts';
