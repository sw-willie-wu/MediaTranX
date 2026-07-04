/**
 * Electron-side update service: wraps the pure updateCore logic with net.fetch
 * (GitHub API + asset download), shell.openPath (launch installer), and
 * preferences.json read/write. All the "check for updates" behaviour lives here;
 * main.js only registers IPC and does the final stop-backend + quit.
 *
 * Path injection: main injects `appDataPath` (= its getAppDataPath()) via
 * configure() so prefs/downloads target the SAME dir main already uses for
 * preferences.json — never app.getPath('userData') (which diverges in dev).
 */
const { app, net, shell } = require('electron');
const fs = require('fs');
const path = require('path');
const core = require('./updateCore.cjs');

const GITHUB_API_LATEST =
  'https://api.github.com/repos/sw-willie-wu/MediaTranX/releases/latest';
const GITHUB_API_LIST =
  'https://api.github.com/repos/sw-willie-wu/MediaTranX/releases?per_page=30';

let appDataPath = null;
let buildMode = 'prod';

/** Inject base data dir + build-time channel stamp. Call once at startup. */
function configure(opts) {
  appDataPath = opts.appDataPath;
  buildMode = opts.buildMode || 'prod';
}

function prefsPath() {
  return path.join(appDataPath, 'preferences.json');
}
function readPrefs() {
  try {
    return JSON.parse(fs.readFileSync(prefsPath(), 'utf-8'));
  } catch (_) {
    return {};
  }
}
function writePrefs(patch) {
  const prefs = readPrefs();
  Object.assign(prefs, patch);
  fs.mkdirSync(path.dirname(prefsPath()), { recursive: true });
  fs.writeFileSync(prefsPath(), JSON.stringify(prefs, null, 2), 'utf-8');
}

function getUpdatePrefs() {
  const p = readPrefs();
  let pending = p.pendingInstaller || null;
  if (pending && !fs.existsSync(pending)) pending = null; // stale → drop
  let frequency = p.updateFrequency || 'weekly';
  if (frequency === 'never') frequency = 'manual'; // legacy：舊「不檢查」併入「手動」
  return {
    frequency,
    lastUpdateCheck: p.lastUpdateCheck || 0,
    pendingInstaller: pending,
  };
}
const VALID_FREQUENCIES = new Set(['startup', 'weekly', 'monthly', 'manual']);
function setUpdateFrequency(f) {
  if (!VALID_FREQUENCIES.has(f)) return; // ignore out-of-enum values
  writePrefs({ updateFrequency: f });
}
function setLastCheck(ms) {
  writePrefs({ lastUpdateCheck: ms });
}
function setPendingInstaller(p) {
  writePrefs({ pendingInstaller: p });
}

/**
 * Check GitHub for updates on this build's channel:
 *   stable → /releases/latest (GitHub already excludes prereleases)
 *   dev    → /releases list, pick the highest version (incl. prereleases)
 * Returns {status:'up-to-date'|'update-available'|'error', channel, current,
 *          latest?, asset?, error?}. `latest` keeps the -dev.N suffix so a
 *          dev.3→dev.4 bump is visible in the UI.
 */
async function checkForUpdates() {
  const current = app.getVersion();
  const channel = core.resolveChannel(app.isPackaged, buildMode);
  let res;
  try {
    res = await net.fetch(channel === 'dev' ? GITHUB_API_LIST : GITHUB_API_LATEST, {
      headers: { 'User-Agent': 'MediaTranX', Accept: 'application/vnd.github+json' },
    });
  } catch (_) {
    return { status: 'error', channel, current, error: 'network' };
  }
  if (!res.ok) {
    return { status: 'error', channel, current, error: res.status === 403 ? 'rate_limit' : 'generic' };
  }
  try {
    const json = await res.json();
    const release = channel === 'dev' ? core.pickLatestFromList(json) : json;
    if (!release) return { status: 'error', channel, current, error: 'generic' };
    const { tag, displayVersion, asset } = core.parseLatestRelease(release);
    if (!core.isUpdateAvailable(current, tag)) {
      return { status: 'up-to-date', channel, current, latest: displayVersion };
    }
    if (!asset) return { status: 'error', channel, current, latest: displayVersion, error: 'no_asset' };
    return { status: 'update-available', channel, current, latest: displayVersion, asset };
  } catch (_) {
    return { status: 'error', channel, current, error: 'generic' };
  }
}

/**
 * Download the latest installer with progress. Re-checks internally (renderer
 * never supplies a URL). Streams to `<appData>/updates/<name>.part`, renames on
 * success, and persists pendingInstaller. onProgress({percent,received,total}).
 * total=0 → indeterminate (percent stays 0).
 */
async function downloadUpdate(onProgress) {
  const r = await checkForUpdates();
  if (r.status !== 'update-available') {
    return { error: r.status === 'error' ? r.error : 'no_update' };
  }
  const asset = r.asset;
  const dir = path.join(appDataPath, 'updates');
  fs.mkdirSync(dir, { recursive: true });
  const finalPath = path.join(dir, asset.name);
  const partPath = finalPath + '.part';
  let out;
  try {
    const res = await net.fetch(asset.browser_download_url);
    if (!res.ok || !res.body) return { error: 'network' };
    const total = Number(res.headers.get('content-length')) || 0;
    const reader = res.body.getReader();
    out = fs.createWriteStream(partPath);
    let received = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.length;
      // Honour backpressure so a ~111MB download doesn't buffer in memory.
      if (!out.write(Buffer.from(value))) {
        await new Promise((resolve) => out.once('drain', resolve));
      }
      onProgress({ percent: total ? Math.floor((received / total) * 100) : 0, received, total });
    }
    await new Promise((resolve, reject) => out.end((err) => (err ? reject(err) : resolve())));
    fs.renameSync(partPath, finalPath);
    setPendingInstaller(finalPath);
    return { path: finalPath };
  } catch (_) {
    try {
      if (out) out.destroy();
      if (fs.existsSync(partPath)) fs.unlinkSync(partPath);
    } catch (__) { /* best effort */ }
    return { error: 'network' };
  }
}

/**
 * Launch the pending installer (uses self-stored path; ignores any renderer
 * arg). Clears pendingInstaller on success. The caller (main) does the
 * stop-backend + app.quit() so files unlock for the installer.
 * @returns {ok:true} | {ok:false, error}
 */
async function prepareInstaller() {
  const { pendingInstaller } = getUpdatePrefs();
  if (!pendingInstaller) return { ok: false, error: 'no_installer' };
  const err = await shell.openPath(pendingInstaller); // '' = success
  if (err) return { ok: false, error: 'launch' };
  setPendingInstaller(null);
  return { ok: true };
}

/**
 * Startup auto-check. Silent unless an update is found. Writes lastCheck only on
 * a successful (non-error) check so a failed check doesn't burn the interval.
 * @param getWindow () => BrowserWindow|null
 */
async function maybeAutoCheck(getWindow) {
  if (!app.isPackaged) return;
  const prefs = getUpdatePrefs();
  if (!core.isCheckDue(prefs.frequency, prefs.lastUpdateCheck, Date.now())) return;
  const r = await checkForUpdates();
  if (r.status === 'error') return;
  setLastCheck(Date.now());
  if (r.status === 'update-available') {
    const w = getWindow();
    if (w && !w.isDestroyed()) w.webContents.send('update:available', r);
  }
}

module.exports = {
  configure,
  checkForUpdates,
  downloadUpdate,
  prepareInstaller,
  getUpdatePrefs,
  setUpdateFrequency,
  setLastCheck,
  setPendingInstaller,
  maybeAutoCheck,
};
