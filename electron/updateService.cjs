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

const GITHUB_API =
  'https://api.github.com/repos/sw-willie-wu/MediaTranX/releases/latest';

let appDataPath = null;

/** Inject the base data dir (main's getAppDataPath()). Call once at startup. */
function configure(opts) {
  appDataPath = opts.appDataPath;
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
  return {
    frequency: p.updateFrequency || 'weekly',
    lastUpdateCheck: p.lastUpdateCheck || 0,
    pendingInstaller: pending,
  };
}
const VALID_FREQUENCIES = new Set(['startup', 'weekly', 'monthly', 'never']);
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
 * Check GitHub /releases/latest (full releases only). Returns:
 *   {status:'dev'|'up-to-date'|'update-available'|'error', current, latest?, asset?, error?}
 * dev is gated on !app.isPackaged (getVersion() returns the real version even
 * unpackaged, so it can't be used to detect dev).
 */
async function checkForUpdates() {
  const current = app.getVersion();
  if (!app.isPackaged) return { status: 'dev', current };
  // Split fetch (network errors) from parse (generic) so the error taxonomy
  // matches spec §3.2/§6: fetch-throw → 'network', bad payload → 'generic'.
  let res;
  try {
    res = await net.fetch(GITHUB_API, {
      headers: { 'User-Agent': 'MediaTranX', Accept: 'application/vnd.github+json' },
    });
  } catch (_) {
    return { status: 'error', current, error: 'network' };
  }
  if (!res.ok) {
    return { status: 'error', current, error: res.status === 403 ? 'rate_limit' : 'generic' };
  }
  try {
    const json = await res.json();
    const { tag, version, asset } = core.parseLatestRelease(json);
    if (!core.isUpdateAvailable(current, tag)) {
      return { status: 'up-to-date', current, latest: version };
    }
    if (!asset) return { status: 'error', current, latest: version, error: 'no_asset' };
    return { status: 'update-available', current, latest: version, asset };
  } catch (_) {
    return { status: 'error', current, error: 'generic' };
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
