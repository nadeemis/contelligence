/**
 * CLI detection — locate the GitHub Copilot CLI and check Azure login status.
 */
import { app } from 'electron';
import { execSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { getResolvedPath } from './shell-env';

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

  const isWindows = process.platform === 'win32';

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
    // npm global install — use .cmd wrapper on Windows
    path.join(home, 'AppData', 'Roaming', 'npm', isWindows ? 'copilot.cmd' : 'copilot'),
  ];

  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }

  // Fall back to PATH lookup (use resolved shell PATH for GUI launches)
  try {
    const env = { ...process.env, PATH: getResolvedPath() };
    const result = execSync(
      process.platform === 'win32' ? 'where copilot' : 'which copilot',
      { stdio: 'pipe', timeout: 5_000, env },
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
  available: boolean;
  loggedIn: boolean;
  error?: string;
}

/** Check if the Azure CLI binary is on the resolved PATH. */
function findAzCli(): boolean {
  const env = { ...process.env, PATH: getResolvedPath() };
  try {
    execSync(
      process.platform === 'win32' ? 'where az' : 'which az',
      { stdio: 'pipe', timeout: 5_000, env },
    );
    return true;
  } catch {
    return false;
  }
}

/**
 * Check Azure CLI availability and login status.
 * If `az` is not installed the check is skipped entirely — Azure features
 * are optional and the app works fine without them.
 */
export function checkAzureLogin(): AzureLoginResult {
  if (!findAzCli()) {
    return {
      available: false,
      loggedIn: false,
      error:
        'Azure CLI is not installed. Azure features are unavailable.\n' +
        'Install it from https://aka.ms/installazurecli if needed.',
    };
  }

  const env = { ...process.env, PATH: getResolvedPath() };
  try {
    execSync('az account show', { stdio: 'pipe', timeout: 10_000, env });
    return { available: true, loggedIn: true };
  } catch {
    return {
      available: true,
      loggedIn: false,
      error:
        'Not logged in to Azure CLI. Some features may be unavailable.\n' +
        'Run "az login" in a terminal to authenticate.',
    };
  }
}
