/**
 * UpdateChecker — polls the GitHub Releases API for new versions of the
 * Cowork desktop app and emits status events for the renderer to display.
 *
 * v1 scope: check + notify only. The user is directed to GitHub Releases
 * to download the new version. Background auto-install is intentionally
 * out of scope (requires code signing).
 */
import { app } from 'electron';
import { EventEmitter } from 'node:events';
import fs from 'node:fs';
import path from 'node:path';

import { fileLog } from './logging';

// ─── Types ──────────────────────────────────────────────────────────────────

export type UpdateAssetPlatform = 'mac' | 'win' | 'linux';

export interface UpdateAsset {
  platform: UpdateAssetPlatform;
  url: string;
  name: string;
  size: number;
}

export type UpdateState = 'idle' | 'checking' | 'available' | 'up-to-date' | 'error';

export interface UpdateStatus {
  state: UpdateState;
  currentVersion: string;
  latestVersion?: string;
  releaseNotes?: string;
  releaseUrl?: string;
  publishedAt?: string;
  assets?: UpdateAsset[];
  checkedAt?: string;
  error?: string;
}

interface UpdateCache {
  etag?: string;
  lastCheckedAt?: string;
  latestVersion?: string;
  releaseUrl?: string;
  publishedAt?: string;
  releaseNotes?: string;
  assets?: UpdateAsset[];
}

interface UpdateCheckerOptions {
  owner: string;
  repo: string;
  currentVersion: string;
  intervalMs?: number;
  includePrereleases?: boolean;
  cacheDir?: string;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

/**
 * Minimal semver comparator. Returns:
 *   1  if a > b
 *   0  if a == b
 *  -1  if a < b
 *  null if either side is not parseable.
 *
 * Pre-release tags are compared lexically; a release without a pre-release
 * tag is considered greater than one with the same major.minor.patch.
 */
export function compareSemver(a: string, b: string): number | null {
  const parse = (raw: string) => {
    const m = raw.trim().replace(/^v/i, '').match(
      /^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$/,
    );
    if (!m) return null;
    return {
      major: Number(m[1]),
      minor: Number(m[2]),
      patch: Number(m[3]),
      pre: m[4] ?? '',
    };
  };
  const av = parse(a);
  const bv = parse(b);
  if (!av || !bv) return null;
  if (av.major !== bv.major) return av.major > bv.major ? 1 : -1;
  if (av.minor !== bv.minor) return av.minor > bv.minor ? 1 : -1;
  if (av.patch !== bv.patch) return av.patch > bv.patch ? 1 : -1;
  if (av.pre === bv.pre) return 0;
  if (av.pre === '') return 1; // a is full release, b is pre-release
  if (bv.pre === '') return -1;
  return av.pre > bv.pre ? 1 : -1;
}

function isPrerelease(tag: string): boolean {
  return /-/.test(tag.replace(/^v/i, ''));
}

function classifyAsset(name: string): UpdateAssetPlatform | null {
  const lower = name.toLowerCase();
  if (/darwin|\.dmg$|mac-/.test(lower)) return 'mac';
  if (/win32|win-|\.exe$|\.msi$/.test(lower)) return 'win';
  if (/linux|\.deb$|\.rpm$|\.AppImage$/i.test(name)) return 'linux';
  return null;
}

// ─── UpdateChecker ──────────────────────────────────────────────────────────

const DEFAULT_INTERVAL_MS = 6 * 60 * 60 * 1000; // 6 hours
const INITIAL_DELAY_MS = 30 * 1000; // 30 seconds after `start()`
const MAX_BACKOFF_MS = 24 * 60 * 60 * 1000; // 24 hours

export class UpdateChecker extends EventEmitter {
  private readonly owner: string;
  private readonly repo: string;
  private readonly currentVersion: string;
  private readonly intervalMs: number;
  private readonly includePrereleases: boolean;
  private readonly cachePath: string;

  private status: UpdateStatus;
  private cache: UpdateCache = {};
  private timer: NodeJS.Timeout | null = null;
  private initialTimer: NodeJS.Timeout | null = null;
  private inFlight: Promise<UpdateStatus> | null = null;
  private consecutiveErrors = 0;

  constructor(opts: UpdateCheckerOptions) {
    super();
    this.owner = opts.owner;
    this.repo = opts.repo;
    this.currentVersion = opts.currentVersion;
    this.intervalMs = opts.intervalMs ?? DEFAULT_INTERVAL_MS;
    this.includePrereleases = opts.includePrereleases ?? false;
    const dir = opts.cacheDir ?? path.join(app.getPath('home'), '.contelligence');
    this.cachePath = path.join(dir, 'update-cache.json');
    this.loadCache();

    this.status = {
      state: 'idle',
      currentVersion: this.currentVersion,
      latestVersion: this.cache.latestVersion,
      releaseUrl: this.cache.releaseUrl,
      publishedAt: this.cache.publishedAt,
      releaseNotes: this.cache.releaseNotes,
      assets: this.cache.assets,
      checkedAt: this.cache.lastCheckedAt,
    };

    // If the cache shows an update is still available, hydrate state.
    if (this.cache.latestVersion) {
      const cmp = compareSemver(this.cache.latestVersion, this.currentVersion);
      if (cmp !== null && cmp > 0) {
        this.status.state = 'available';
      } else if (cmp !== null && cmp <= 0) {
        this.status.state = 'up-to-date';
      }
    }
  }

  /** Schedule the first check (after a delay) and recurring checks. */
  start(): void {
    this.stop();
    this.initialTimer = setTimeout(() => {
      void this.checkNow().catch(() => {
        /* swallow — error is already in this.status */
      });
    }, INITIAL_DELAY_MS);
    this.timer = setInterval(() => {
      void this.checkNow().catch(() => {
        /* swallow */
      });
    }, this.intervalMs);
  }

  /** Cancel scheduled checks. Safe to call repeatedly. */
  stop(): void {
    if (this.initialTimer) {
      clearTimeout(this.initialTimer);
      this.initialTimer = null;
    }
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  getStatus(): UpdateStatus {
    return { ...this.status };
  }

  /** Manually trigger a check. Reuses an in-flight request if one exists. */
  async checkNow(): Promise<UpdateStatus> {
    if (this.inFlight) return this.inFlight;
    this.inFlight = this.doCheck().finally(() => {
      this.inFlight = null;
    });
    return this.inFlight;
  }

  // ── internals ─────────────────────────────────────────────────────────────

  private async doCheck(): Promise<UpdateStatus> {
    this.setStatus({ ...this.status, state: 'checking', error: undefined });
    const url = `https://api.github.com/repos/${this.owner}/${this.repo}/releases/latest`;
    try {
      const headers: Record<string, string> = {
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': `Contelligence-Cowork/${this.currentVersion}`,
      };
      if (this.cache.etag) headers['If-None-Match'] = this.cache.etag;

      const res = await fetch(url, { headers });

      if (res.status === 304) {
        // Nothing changed since last check — keep existing status, just stamp it.
        this.consecutiveErrors = 0;
        const checkedAt = new Date().toISOString();
        this.cache.lastCheckedAt = checkedAt;
        this.saveCache();
        const next: UpdateStatus = { ...this.status, checkedAt };
        // State already reflects whether an update is available from cache.
        if (next.state === 'checking') {
          next.state = next.latestVersion ? this.compareToCurrent(next.latestVersion) : 'up-to-date';
        }
        this.setStatus(next);
        fileLog('INFO', `Update check: 304 not modified (latest known: ${next.latestVersion ?? 'none'})`);
        return next;
      }

      if (!res.ok) {
        throw new Error(`GitHub API ${res.status} ${res.statusText}`);
      }

      const etag = res.headers.get('etag') ?? undefined;
      const release = (await res.json()) as {
        tag_name: string;
        name?: string;
        body?: string;
        html_url: string;
        published_at?: string;
        prerelease?: boolean;
        draft?: boolean;
        assets?: Array<{ name: string; browser_download_url: string; size: number }>;
      };

      if (release.draft) {
        throw new Error('Latest release is a draft');
      }
      if (release.prerelease && !this.includePrereleases) {
        // Treat as up-to-date — we ignore prereleases unless opted in.
        return this.markUpToDate(etag);
      }

      const tag = release.tag_name;
      if (isPrerelease(tag) && !this.includePrereleases) {
        return this.markUpToDate(etag);
      }

      const cmp = compareSemver(tag, this.currentVersion);
      if (cmp === null) {
        fileLog('WARN', `Update check: non-semver tag "${tag}" — skipping`);
        return this.markUpToDate(etag);
      }

      const assets: UpdateAsset[] = (release.assets ?? [])
        .map((a) => {
          const platform = classifyAsset(a.name);
          if (!platform) return null;
          return {
            platform,
            name: a.name,
            url: a.browser_download_url,
            size: a.size,
          } satisfies UpdateAsset;
        })
        .filter((a): a is UpdateAsset => a !== null);

      const checkedAt = new Date().toISOString();
      const next: UpdateStatus = {
        state: cmp > 0 ? 'available' : 'up-to-date',
        currentVersion: this.currentVersion,
        latestVersion: tag.replace(/^v/i, ''),
        releaseNotes: release.body ?? '',
        releaseUrl: release.html_url,
        publishedAt: release.published_at,
        assets,
        checkedAt,
      };

      this.cache = {
        etag,
        lastCheckedAt: checkedAt,
        latestVersion: next.latestVersion,
        releaseUrl: next.releaseUrl,
        publishedAt: next.publishedAt,
        releaseNotes: next.releaseNotes,
        assets,
      };
      this.saveCache();
      this.consecutiveErrors = 0;
      this.setStatus(next);
      fileLog(
        'INFO',
        `Update check: latest=${next.latestVersion} current=${this.currentVersion} state=${next.state}`,
      );
      return next;
    } catch (err) {
      this.consecutiveErrors += 1;
      const message = err instanceof Error ? err.message : String(err);
      const next: UpdateStatus = {
        ...this.status,
        state: 'error',
        error: message,
        checkedAt: new Date().toISOString(),
      };
      this.setStatus(next);
      fileLog('WARN', `Update check failed (${this.consecutiveErrors}): ${message}`);
      this.scheduleBackoff();
      return next;
    }
  }

  private compareToCurrent(latest: string): UpdateState {
    const cmp = compareSemver(latest, this.currentVersion);
    if (cmp === null) return 'up-to-date';
    return cmp > 0 ? 'available' : 'up-to-date';
  }

  private markUpToDate(etag?: string): UpdateStatus {
    const checkedAt = new Date().toISOString();
    this.cache.etag = etag ?? this.cache.etag;
    this.cache.lastCheckedAt = checkedAt;
    // Clear any stale "latest > current" memory so the indicator goes away.
    this.cache.latestVersion = this.currentVersion;
    this.cache.releaseUrl = undefined;
    this.cache.publishedAt = undefined;
    this.cache.releaseNotes = undefined;
    this.cache.assets = undefined;
    this.saveCache();
    this.consecutiveErrors = 0;
    const next: UpdateStatus = {
      state: 'up-to-date',
      currentVersion: this.currentVersion,
      latestVersion: this.currentVersion,
      checkedAt,
    };
    this.setStatus(next);
    return next;
  }

  private setStatus(next: UpdateStatus): void {
    this.status = next;
    this.emit('status', { ...next });
  }

  /**
   * After a failure, wait progressively longer before the next attempt.
   * The recurring interval still runs underneath, but we replace its next
   * tick with this backoff timer so we don't hammer GitHub on outage.
   */
  private scheduleBackoff(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    const backoff = Math.min(
      this.intervalMs * Math.pow(2, this.consecutiveErrors - 1),
      MAX_BACKOFF_MS,
    );
    this.timer = setTimeout(() => {
      // Resume normal cadence.
      this.timer = setInterval(() => {
        void this.checkNow().catch(() => {
          /* swallow */
        });
      }, this.intervalMs);
      void this.checkNow().catch(() => {
        /* swallow */
      });
    }, backoff);
  }

  private loadCache(): void {
    try {
      if (fs.existsSync(this.cachePath)) {
        const raw = fs.readFileSync(this.cachePath, 'utf-8');
        this.cache = JSON.parse(raw) as UpdateCache;
      }
    } catch (err) {
      fileLog('WARN', `Failed to read update cache: ${err}`);
      this.cache = {};
    }
  }

  private saveCache(): void {
    try {
      fs.mkdirSync(path.dirname(this.cachePath), { recursive: true });
      fs.writeFileSync(this.cachePath, JSON.stringify(this.cache, null, 2), 'utf-8');
    } catch (err) {
      fileLog('WARN', `Failed to write update cache: ${err}`);
    }
  }
}
