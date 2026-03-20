/**
 * Backend lifecycle — spawn, health-check, and stop the Python backend.
 * The backend is either a packaged PyInstaller binary (production)
 * or uvicorn running from source (development).
 */
import { app } from 'electron';
import { execFile, ChildProcess, execSync } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileLog } from './logging';

let backendProcess: ChildProcess | null = null;
let backendPort: number | null = null;

/** Return the current backend port (for URL construction in main). */
export function getBackendPort(): number | null {
  return backendPort;
}

/** Base directory for all Contelligence user data (~/.contelligence). */
export function getContelligenceHome(): string {
  return path.join(app.getPath('home'), '.contelligence');
}

/** Locate the bundled Python backend (PyInstaller or source). */
function getBackendPath(): string {
  if (app.isPackaged) {
    const resourceDir = process.resourcesPath;
    const binaryName =
      process.platform === 'win32'
        ? 'contelligence-agent.exe'
        : 'contelligence-agent';
    return path.join(resourceDir, 'backend', binaryName);
  }
  // Development — run from source via uvicorn
  return '';
}

/** Find an available TCP port starting from *preferred*. */
function findAvailablePort(preferred = 8081): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', () => {
      resolve(findAvailablePort(preferred + 1));
    });
    server.listen(preferred, '127.0.0.1', () => {
      const addr = server.address();
      if (addr && typeof addr !== 'string') {
        const port = addr.port;
        server.close(() => resolve(port));
      } else {
        server.close(() => reject(new Error('Could not determine port')));
      }
    });
  });
}

/**
 * Resolve a usable PATH for child processes.
 * When the app is launched via Finder / double-click on macOS, process.env.PATH
 * is minimal (/usr/bin:/bin:/usr/sbin:/sbin). We recover the user's login
 * shell PATH so subprocesses work the same as from a terminal.
 */
function getShellPath(): string {
  const fallbackPath = process.env.PATH || '';

  if (process.platform === 'win32') return fallbackPath;

  try {
    const loginShell = process.env.SHELL || '/bin/zsh';
    const result = execSync(`${loginShell} -ilc 'echo $PATH'`, {
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 5_000,
      encoding: 'utf-8',
    }).trim();
    if (result) return result;
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
  return merged.filter(Boolean).join(path.delimiter);
}

/** Ensure a default .env exists in the Contelligence home directory. */
function ensureDefaultEnvFile(): string {
  const home = getContelligenceHome();
  const envPath = path.join(home, '.env');
  if (!fs.existsSync(envPath)) {
    const defaults = [
      '# Contelligence local-mode configuration',
      '# Generated on first launch — edit as needed',
      '',
      '# Server',
      'LOG_LEVEL=DEBUG',
      'SESSION_TIMEOUT_MINUTES=60',
      '',
      '# Storage',
      `LOCAL_DATA_DIR=${path.join(home, 'data')}`,
      '',
      '# Skills',
      `AGENT_SHARED_SKILLS_DIRECTORY=${path.join(home, 'skills')}`,
      '',
      '# Auth (disabled in local mode)',
      'AUTH_ENABLED=false',
      '',
      '# GitHub Copilot SDK',
      `CLI_WORKING_DIRECTORY=${path.join(home)}`,
      `CLI_SHARED_SKILLS_DIRECTORY=${path.join(home, 'skills')}`,
      '# GITHUB_COPILOT_TOKEN=ghp_...',
      '# COPILOT_CLI_PATH is auto-detected on startup',
      'COPILOT_MODEL=claude-opus-4.6',
      '',
    ].join('\n');
    fs.mkdirSync(path.dirname(envPath), { recursive: true });
    fs.writeFileSync(envPath, defaults, 'utf-8');
  }
  return envPath;
}

/** Start the Python backend process. */
export async function startBackend(copilotCliPath: string): Promise<void> {
  backendPort = await findAvailablePort(8081);
  const envFile = ensureDefaultEnvFile();
  const home = getContelligenceHome();
  const backendPath = getBackendPath();

  // Build child env — merge the .env file with current env
  const childEnv: Record<string, string> = { ...process.env } as Record<string, string>;

  childEnv['PATH'] = getShellPath();
  if (copilotCliPath) {
    const cliDir = path.dirname(copilotCliPath);
    if (!childEnv['PATH'].split(path.delimiter).includes(cliDir)) {
      childEnv['PATH'] = `${cliDir}${path.delimiter}${childEnv['PATH']}`;
    }
  }

  childEnv['API_VERSION'] = 'v1';
  childEnv['API_PORT'] = String(backendPort);
  childEnv['API_HOST'] = '127.0.0.1';
  childEnv['LOG_LEVEL'] = 'DEBUG';
  childEnv['SESSION_TIMEOUT_MINUTES'] = '60';
  childEnv['STORAGE_MODE'] = 'local';
  childEnv['LOCAL_DATA_DIR'] = path.join(home, 'data');
  childEnv['AGENT_SHARED_SKILLS_DIRECTORY'] = path.join(home, 'skills');
  childEnv['AUTH_ENABLED'] = 'false';
  childEnv['CLI_WORKING_DIRECTORY'] = path.join(home);
  childEnv['CLI_SHARED_SKILLS_DIRECTORY'] = path.join(home, 'skills');
  if (copilotCliPath) {
    childEnv['COPILOT_CLI_PATH'] = copilotCliPath;
  }
  childEnv['COPILOT_MODEL'] = 'claude-opus-4.6';

  // Parse .env file into child env (simple KEY=VALUE, skip comments)
  if (fs.existsSync(envFile)) {
    const lines = fs.readFileSync(envFile, 'utf-8').split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eqIdx = trimmed.indexOf('=');
      if (eqIdx > 0) {
        const key = trimmed.slice(0, eqIdx).trim();
        const value = trimmed.slice(eqIdx + 1).trim();
        childEnv[key] = value;
      }
    }
  }

  if (backendPath) {
    fileLog('INFO', `Launching packaged backend: ${backendPath}`);
    if (!fs.existsSync(backendPath)) {
      fileLog('ERROR', `Backend binary not found at: ${backendPath}`);
    }
    backendProcess = execFile(backendPath, [], {
      env: childEnv,
      cwd: path.dirname(backendPath),
    });
  } else {
    const agentDir = path.join(__dirname, '..', '..', '..', 'contelligence-agent');
    fileLog('INFO', `Launching uvicorn from ${agentDir} on port ${backendPort}`);
    backendProcess = execFile(
      'uvicorn',
      ['main:app', '--host', '127.0.0.1', '--port', String(backendPort)],
      { env: childEnv, cwd: agentDir },
    );
  }

  backendProcess.stdout?.on('data', (data: Buffer) => {
    const msg = data.toString().trim();
    console.log(`[backend] ${msg}`);
    fileLog('INFO', `[backend:stdout] ${msg}`);
  });
  backendProcess.stderr?.on('data', (data: Buffer) => {
    const msg = data.toString().trim();
    console.error(`[backend] ${msg}`);
    fileLog('ERROR', `[backend:stderr] ${msg}`);
  });
  backendProcess.on('error', (err) => {
    const msg = `Failed to start backend process: ${err.message}`;
    console.error(`[backend] ${msg}`);
    fileLog('ERROR', msg);
  });
  backendProcess.on('exit', (code, signal) => {
    const msg = `process exited with code ${code}, signal ${signal}`;
    console.log(`[backend] ${msg}`);
    fileLog('WARN', `[backend] ${msg}`);
    backendProcess = null;
  });
}

/** Wait for the backend /api/v1/health endpoint to respond. */
export async function waitForBackend(
  timeoutMs = 30_000,
  intervalMs = 500,
  onProgress?: (elapsed: number, total: number) => void,
): Promise<void> {
  const url = `http://127.0.0.1:${backendPort}/api/v1/health`;
  const start = Date.now();
  const deadline = start + timeoutMs;

  while (Date.now() < deadline) {
    try {
      const resp = await fetch(url);
      if (resp.ok) return;
    } catch {
      // Not ready yet
    }
    onProgress?.(Date.now() - start, timeoutMs);
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(`Backend did not start within ${timeoutMs}ms`);
}

/** Gracefully stop the backend. */
export function stopBackend(): void {
  if (backendProcess && !backendProcess.killed) {
    if (process.platform === 'win32') {
      try {
        execSync(`taskkill /pid ${backendProcess.pid} /T /F`, { stdio: 'ignore' });
      } catch {
        // Process may already be dead
      }
    } else {
      backendProcess.kill('SIGTERM');
      setTimeout(() => {
        if (backendProcess && !backendProcess.killed) {
          backendProcess.kill('SIGKILL');
        }
      }, 5_000);
    }
  }
  backendProcess = null;
}
