/**
 * Shell environment — resolve the user's full login-shell PATH once at startup.
 *
 * When the app is launched via Finder / Dock / Spotlight on macOS, process.env.PATH
 * is minimal (/usr/bin:/bin:/usr/sbin:/sbin). We recover the user's login-shell
 * PATH so that CLI tools (az, copilot, etc.) are found regardless of launch method.
 *
 * Call `resolveShellPath()` once early in the app lifecycle, then use
 * `getResolvedPath()` everywhere that needs the full PATH.
 */
import { app } from 'electron';
import { execSync } from 'node:child_process';
import path from 'node:path';
import { fileLog } from './logging';

let resolvedPath: string | null = null;

/** Resolve and cache the user's full shell PATH. Call once at startup. */
export function resolveShellPath(): string {
  if (resolvedPath !== null) return resolvedPath;

  const fallbackPath = process.env.PATH || '';

  if (process.platform === 'win32') {
    resolvedPath = fallbackPath;
    return resolvedPath;
  }

  try {
    const loginShell = process.env.SHELL || '/bin/zsh';
    const result = execSync(`${loginShell} -ilc 'echo $PATH'`, {
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 5_000,
      encoding: 'utf-8',
    }).trim();
    if (result) {
      resolvedPath = result;
      fileLog('INFO', 'Resolved full shell PATH from login shell');
      return resolvedPath;
    }
  } catch {
    // Shell extraction failed — fall through
  }

  const home = app.getPath('home');
  const extras = [
    '/usr/local/bin',
    '/opt/homebrew/bin',
    '/opt/homebrew/sbin',
    path.join(home, '.nvm/versions/node'),
    path.join(home, '.local/bin'),
    '/usr/local/sbin',
  ];
  const merged = [...new Set([...extras, ...fallbackPath.split(path.delimiter)])];
  resolvedPath = merged.filter(Boolean).join(path.delimiter);
  fileLog('INFO', 'Resolved PATH from well-known directories (login shell failed)');
  return resolvedPath;
}

/** Return the previously resolved PATH (or the process PATH if not yet resolved). */
export function getResolvedPath(): string {
  return resolvedPath ?? process.env.PATH ?? '';
}
