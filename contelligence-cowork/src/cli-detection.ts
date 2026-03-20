/**
 * CLI detection — locate the GitHub Copilot CLI and check Azure login status.
 */
import { app } from 'electron';
import { execSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

// ---------------------------------------------------------------------------
// Copilot CLI
// ---------------------------------------------------------------------------

export interface CopilotCliResult {
  found: boolean;
  path: string;
  error?: string;
}

/** Search well-known locations for the Copilot CLI binary. */
function findCopilotCliPath(): string {
  const home = app.getPath('home');

  const candidates: string[] = [
    // VS Code extension (macOS / Linux)
    path.join(home, 'Library', 'Application Support', 'Code', 'User',
      'globalStorage', 'github.copilot-chat', 'copilotCli', 'copilot'),
    // VS Code extension (Linux alternate)
    path.join(home, '.config', 'Code', 'User',
      'globalStorage', 'github.copilot-chat', 'copilotCli', 'copilot'),
    // VS Code extension (Windows)
    path.join(home, 'AppData', 'Roaming', 'Code', 'User',
      'globalStorage', 'github.copilot-chat', 'copilotCli', 'copilot.exe'),
    path.join(home, 'AppData', 'Roaming', 'npm', 'copilot'),
  ];

  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }

  // Fall back to PATH lookup
  try {
    const result = execSync(
      process.platform === 'win32' ? 'where copilot' : 'which copilot',
      { stdio: 'pipe', timeout: 5_000 },
    ).toString().trim().split('\n')[0];
    if (result && fs.existsSync(result)) return result;
  } catch {
    // not on PATH
  }

  return '';
}

/** Check whether the Copilot CLI is available. */
export function checkCopilotCli(): CopilotCliResult {
  const cliPath = findCopilotCliPath();
  if (cliPath) {
    return { found: true, path: cliPath };
  }
  return {
    found: false,
    path: '',
    error:
      'GitHub Copilot CLI was not found on this system.\n\n' +
      'AI agent features require the Copilot CLI.\n' +
      'Install it via the GitHub Copilot Chat extension in VS Code, ' +
      'then run "copilot" in a terminal to verify.',
  };
}

// ---------------------------------------------------------------------------
// Azure CLI
// ---------------------------------------------------------------------------

export interface AzureLoginResult {
  loggedIn: boolean;
  error?: string;
}

/** Check if the user is logged in to Azure CLI. */
export function checkAzureLogin(): AzureLoginResult {
  try {
    execSync('az account show', { stdio: 'pipe', timeout: 10_000 });
    return { loggedIn: true };
  } catch {
    return {
      loggedIn: false,
      error:
        'Not logged in to Azure CLI. Some features may be unavailable.\n' +
        'Run "az login" in a terminal to authenticate.',
    };
  }
}
