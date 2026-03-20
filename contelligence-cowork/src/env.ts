/**
 * .env.local loader — reads dev overrides from the project root.
 * Called before `app.on('ready')` so environment variables are available
 * to all modules during startup.
 */
import fs from 'node:fs';
import path from 'node:path';

export function loadEnvFile(): void {
  const candidates = [
    path.join(__dirname, '..', '..', '.env.local'),   // dev: contelligence-cowork/.env.local
    path.join(process.resourcesPath || '', '.env.local'), // packaged (unlikely but safe)
  ];
  for (const envPath of candidates) {
    if (fs.existsSync(envPath)) {
      const lines = fs.readFileSync(envPath, 'utf-8').split('\n');
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;
        const eqIdx = trimmed.indexOf('=');
        if (eqIdx > 0) {
          const key = trimmed.slice(0, eqIdx).trim();
          const value = trimmed.slice(eqIdx + 1).trim();
          if (!process.env[key]) process.env[key] = value; // don't override shell env
        }
      }
      break;
    }
  }
}
