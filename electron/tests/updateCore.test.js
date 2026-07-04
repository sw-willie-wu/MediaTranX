const test = require('node:test');
const assert = require('node:assert');
const {
  WEEK_MS,
  MONTH_MS,
  normalizeVersion,
  compareVersions,
  isUpdateAvailable,
  pickInstallerAsset,
  parseLatestRelease,
  isCheckDue,
} = require('../updateCore.cjs');

// ── normalizeVersion ─────────────────────────────────────────────────────────
test('normalizeVersion strips v prefix, suffix, whitespace', () => {
  assert.strictEqual(normalizeVersion('v1.5.2'), '1.5.2');
  assert.strictEqual(normalizeVersion(' 1.5.2 '), '1.5.2');
  assert.strictEqual(normalizeVersion('v1.6.0-dev.3'), '1.6.0');
  assert.strictEqual(normalizeVersion('V2.0.0'), '2.0.0');
  assert.strictEqual(normalizeVersion(''), null);
  assert.strictEqual(normalizeVersion(null), null);
  assert.strictEqual(normalizeVersion(undefined), null);
});

// ── compareVersions ──────────────────────────────────────────────────────────
test('compareVersions: equal', () => {
  assert.strictEqual(compareVersions('1.5.2', '1.5.2'), 0);
});
test('compareVersions: missing segments count as 0', () => {
  assert.strictEqual(compareVersions('1.5', '1.5.0'), 0);
});
test('compareVersions: numeric not lexical (1.5.2 < 1.10.0)', () => {
  assert.strictEqual(compareVersions('1.5.2', '1.10.0'), -1);
  assert.strictEqual(compareVersions('1.10.0', '1.5.2'), 1);
});
test('compareVersions: patch/minor/major ordering', () => {
  assert.strictEqual(compareVersions('1.5.3', '1.5.2'), 1);
  assert.strictEqual(compareVersions('2.0.0', '1.9.9'), 1);
});

// ── isUpdateAvailable ────────────────────────────────────────────────────────
test('isUpdateAvailable: newer latest → true', () => {
  assert.strictEqual(isUpdateAvailable('1.5.2', 'v1.6.0'), true);
});
test('isUpdateAvailable: equal → false', () => {
  assert.strictEqual(isUpdateAvailable('1.5.2', 'v1.5.2'), false);
});
test('isUpdateAvailable: older latest → false', () => {
  assert.strictEqual(isUpdateAvailable('1.5.2', 'v1.5.1'), false);
});
test('isUpdateAvailable: unparseable side → false', () => {
  assert.strictEqual(isUpdateAvailable(null, 'v1.6.0'), false);
  assert.strictEqual(isUpdateAvailable('1.5.2', ''), false);
});

// ── pickInstallerAsset ───────────────────────────────────────────────────────
test('pickInstallerAsset: prefers -full-win.exe', () => {
  const assets = [
    { name: 'MediaTranX-Setup-1.6.0-win.exe.blockmap', size: 1, browser_download_url: 'x' },
    { name: 'MediaTranX-Setup-1.6.0-full-win.exe', size: 111, browser_download_url: 'https://full' },
    { name: 'MediaTranX-Setup-1.6.0-win.exe', size: 100, browser_download_url: 'https://plain' },
  ];
  const got = pickInstallerAsset(assets);
  assert.strictEqual(got.name, 'MediaTranX-Setup-1.6.0-full-win.exe');
  assert.strictEqual(got.size, 111);
  assert.strictEqual(got.browser_download_url, 'https://full');
});
test('pickInstallerAsset: falls back to plain -win.exe', () => {
  const assets = [
    { name: 'latest.yml', size: 1, browser_download_url: 'x' },
    { name: 'MediaTranX-Setup-1.6.0-win.exe', size: 100, browser_download_url: 'https://plain' },
  ];
  assert.strictEqual(pickInstallerAsset(assets).name, 'MediaTranX-Setup-1.6.0-win.exe');
});
test('pickInstallerAsset: no installer → null', () => {
  assert.strictEqual(pickInstallerAsset([{ name: 'notes.txt' }]), null);
  assert.strictEqual(pickInstallerAsset([]), null);
  assert.strictEqual(pickInstallerAsset(null), null);
});

// ── parseLatestRelease ───────────────────────────────────────────────────────
test('parseLatestRelease: valid payload', () => {
  const r = parseLatestRelease({
    tag_name: 'v1.6.0',
    assets: [{ name: 'MediaTranX-Setup-1.6.0-full-win.exe', size: 5, browser_download_url: 'u' }],
  });
  assert.strictEqual(r.tag, 'v1.6.0');
  assert.strictEqual(r.version, '1.6.0');
  assert.strictEqual(r.asset.browser_download_url, 'u');
});
test('parseLatestRelease: missing tag_name throws', () => {
  assert.throws(() => parseLatestRelease({ assets: [] }));
  assert.throws(() => parseLatestRelease(null));
});

// ── isCheckDue ───────────────────────────────────────────────────────────────
test('isCheckDue: never → false', () => {
  assert.strictEqual(isCheckDue('never', 0, 1000), false);
  assert.strictEqual(isCheckDue('never', 1, Number.MAX_SAFE_INTEGER), false);
});
test('isCheckDue: startup → always true', () => {
  assert.strictEqual(isCheckDue('startup', Date.now?.() ?? 1, 1), true);
});
test('isCheckDue: never-checked (falsy lastCheck) → true', () => {
  assert.strictEqual(isCheckDue('weekly', 0, 1000), true);
  assert.strictEqual(isCheckDue('monthly', null, 1000), true);
});
test('isCheckDue: weekly boundary', () => {
  const now = 1_000_000_000_000;
  assert.strictEqual(isCheckDue('weekly', now - WEEK_MS + 1, now), false);
  assert.strictEqual(isCheckDue('weekly', now - WEEK_MS, now), true);
});
test('isCheckDue: monthly boundary', () => {
  const now = 1_000_000_000_000;
  assert.strictEqual(isCheckDue('monthly', now - MONTH_MS + 1, now), false);
  assert.strictEqual(isCheckDue('monthly', now - MONTH_MS, now), true);
});
test('isCheckDue: backward clock (negative delta) → due', () => {
  const now = 1_000_000;
  assert.strictEqual(isCheckDue('weekly', now + 999999, now), true);
  assert.strictEqual(isCheckDue('monthly', now + 999999, now), true);
});
