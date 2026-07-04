/**
 * Pure, dependency-free update logic (no electron imports) so it can be unit
 * tested under the existing `node --test` runner. The electron-facing service
 * (`updateService.cjs`) wraps these with net.fetch / shell / fs.
 */

const DAY_MS = 24 * 60 * 60 * 1000;
const WEEK_MS = 7 * DAY_MS;
const MONTH_MS = 30 * DAY_MS;

/**
 * Normalize a version-ish string to bare "major.minor.patch".
 * Strips a leading 'v'/'V', drops any pre-release/build suffix ("-dev.3"),
 * trims whitespace. Returns null for empty/nullish input.
 */
function normalizeVersion(v) {
  if (v === null || v === undefined) return null;
  let s = String(v).trim();
  if (s === '') return null;
  if (s[0] === 'v' || s[0] === 'V') s = s.slice(1);
  const dash = s.indexOf('-');
  if (dash !== -1) s = s.slice(0, dash);
  return s === '' ? null : s;
}

/**
 * Compare two normalized version strings numerically by major.minor.patch.
 * Missing segments count as 0 ("1.5" === "1.5.0"). Returns -1 | 0 | 1.
 * Non-numeric segments are treated as 0.
 */
function compareVersions(a, b) {
  const pa = String(a).split('.');
  const pb = String(b).split('.');
  const len = Math.max(pa.length, pb.length);
  for (let i = 0; i < len; i++) {
    const na = Number(pa[i]);
    const nb = Number(pb[i]);
    const va = Number.isFinite(na) ? na : 0;
    const vb = Number.isFinite(nb) ? nb : 0;
    if (va > vb) return 1;
    if (va < vb) return -1;
  }
  return 0;
}

/**
 * True iff `latestTag` is a strictly newer version than `current`.
 * Either side unparseable → false (never offer an update we can't reason about).
 */
function isUpdateAvailable(current, latestTag) {
  const c = normalizeVersion(current);
  const l = normalizeVersion(latestTag);
  if (!c || !l) return false;
  return compareVersions(l, c) > 0;
}

/**
 * Pick the Windows NSIS installer asset from a GitHub release's assets array.
 * Prefers the "-full-win.exe" build; falls back to a plain "...-win.exe"
 * (release.py only appends "-full" when built with --full). Returns
 * { name, size, browser_download_url } or null.
 */
function pickInstallerAsset(assets) {
  if (!Array.isArray(assets)) return null;
  const full = /MediaTranX-Setup-.*-full-win\.exe$/i;
  const any = /MediaTranX-Setup-.*-win\.exe$/i;
  const byName = (re) => assets.find((a) => a && typeof a.name === 'string' && re.test(a.name));
  const hit = byName(full) || byName(any);
  if (!hit) return null;
  return { name: hit.name, size: hit.size, browser_download_url: hit.browser_download_url };
}

/**
 * Parse a GitHub /releases/latest JSON payload into { tag, version, asset }.
 * Throws if tag_name is missing (treated as a parse error upstream).
 */
function parseLatestRelease(json) {
  if (!json || typeof json.tag_name !== 'string' || json.tag_name === '') {
    throw new Error('missing tag_name');
  }
  return {
    tag: json.tag_name,
    version: normalizeVersion(json.tag_name),
    asset: pickInstallerAsset(json.assets || []),
  };
}

/**
 * Whether an auto-check should run now, given the configured frequency and the
 * last-check timestamp (ms). A never-checked (falsy) or backward-clock (delta<0)
 * state is treated as due, so a bad clock never permanently disables checks.
 */
function isCheckDue(frequency, lastCheckMs, nowMs) {
  if (frequency === 'never') return false;
  if (frequency === 'startup') return true;
  if (!lastCheckMs) return true;
  const delta = nowMs - lastCheckMs;
  if (delta < 0) return true;
  if (frequency === 'weekly') return delta >= WEEK_MS;
  if (frequency === 'monthly') return delta >= MONTH_MS;
  return false;
}

module.exports = {
  WEEK_MS,
  MONTH_MS,
  normalizeVersion,
  compareVersions,
  isUpdateAvailable,
  pickInstallerAsset,
  parseLatestRelease,
  isCheckDue,
};
