/**
 * Splash / progress window — shown during application startup.
 * Displays a frameless dark-themed window with a progress bar,
 * status message, and scrolling log of check results.
 */
import { BrowserWindow } from 'electron';

let splashWindow: BrowserWindow | null = null;

const splashHtml = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #111318;
    color: #e4e4e7;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100vh;
    -webkit-app-region: drag;
    user-select: none;
    overflow: hidden;
  }
  .logo { width: 72px; height: 72px; margin-bottom: 18px; border-radius: 16px; }
  .title { font-size: 22px; font-weight: 600; margin-bottom: 6px; letter-spacing: -0.3px; }
  .subtitle { font-size: 12px; color: #71717a; margin-bottom: 28px; }
  .progress-track {
    width: 260px; height: 4px; background: #27272a; border-radius: 2px;
    overflow: hidden; margin-bottom: 16px;
  }
  .progress-bar {
    height: 100%; width: 0%; border-radius: 2px;
    background: linear-gradient(90deg, #6366f1, #8b5cf6);
    transition: width 0.4s ease;
  }
  .message {
    font-size: 12px; color: #a1a1aa; min-height: 18px;
    transition: opacity 0.2s ease;
  }
  .log {
    margin-top: 12px; width: 320px; max-height: 60px;
    overflow: hidden; text-align: center;
  }
  .log-line {
    font-size: 10px; color: #52525b; line-height: 1.5;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .warning { color: #facc15; }
</style>
</head>
<body>
  <div class="title">Contelligence</div>
  <div class="subtitle">Starting up\u2026</div>
  <div class="progress-track"><div class="progress-bar" id="bar"></div></div>
  <div class="message" id="msg">Initializing</div>
  <div class="log" id="log"></div>
</body>
</html>`;

/** Create and show the splash window. */
export function createSplashWindow(): void {
  splashWindow = new BrowserWindow({
    width: 420,
    height: 300,
    frame: false,
    transparent: false,
    resizable: false,
    movable: true,
    center: true,
    backgroundColor: '#111318',
    show: false,
    alwaysOnTop: true,
    skipTaskbar: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  splashWindow.loadURL(
    `data:text/html;charset=utf-8,${encodeURIComponent(splashHtml)}`,
  );

  splashWindow.once('ready-to-show', () => {
    splashWindow?.show();
  });

  splashWindow.on('closed', () => {
    splashWindow = null;
  });
}

/** Update the splash window progress bar and message. */
export function splashProgress(percent: number, message: string): void {
  if (!splashWindow || splashWindow.isDestroyed()) return;
  const safeMsg = message.replace(/'/g, "\\'").replace(/\n/g, ' ');
  splashWindow.webContents.executeJavaScript(
    `document.getElementById('bar').style.width='${percent}%';` +
    `document.getElementById('msg').textContent='${safeMsg}';`,
  ).catch(() => {/* splash may be closing */});
}

/** Append a warning or info line to the splash log area. */
export function splashLog(text: string, isWarning = false): void {
  if (!splashWindow || splashWindow.isDestroyed()) return;
  const safeText = text.replace(/'/g, "\\'").replace(/\n/g, ' ');
  const cls = isWarning ? 'log-line warning' : 'log-line';
  splashWindow.webContents.executeJavaScript(
    `(function(){` +
    `var d=document.getElementById('log');` +
    `var p=document.createElement('div');` +
    `p.className='${cls}';p.textContent='${safeText}';` +
    `d.appendChild(p);` +
    `if(d.children.length>3) d.removeChild(d.firstChild);` +
    `})();`,
  ).catch(() => {});
}

/** Close the splash window if it's still open. */
export function closeSplash(): void {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.close();
  }
  splashWindow = null;
}
