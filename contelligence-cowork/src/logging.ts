/**
 * File-based logging — writes to ~/.contelligence/logs/
 * Captures both Electron main-process messages and backend stdout/stderr
 * so that issues are diagnosable even when DevTools isn't open.
 */
import { app } from 'electron';
import fs from 'node:fs';
import path from 'node:path';

let logStream: fs.WriteStream | null = null;

/** Open (or reopen) the daily log file under ~/.contelligence/logs/. */
export function initLogFile(): void {
  const logsDir = path.join(app.getPath('home'), '.contelligence', 'logs');
  fs.mkdirSync(logsDir, { recursive: true });
  const logPath = path.join(logsDir, `main-${new Date().toISOString().slice(0, 10)}.log`);
  logStream = fs.createWriteStream(logPath, { flags: 'a' });
}

/** Append a timestamped line to the log file. */
export function fileLog(level: string, msg: string): void {
  const line = `${new Date().toISOString()} [${level}] ${msg}\n`;
  logStream?.write(line);
}

/** Flush and close the log stream (call on quit). */
export function closeLogFile(): void {
  logStream?.end();
  logStream = null;
}
